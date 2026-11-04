"""HTTP API. Read-only analysis endpoints plus human review.

There are deliberately no endpoints for contacting, messaging, following, or
profiling anyone.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import config
from app.db import database
from app.db import repository as repo
from app.schemas.models import (
    AuditEntry,
    Category,
    DatasetInfo,
    Graph,
    PostPage,
    PostWithClassification,
    ReviewRequest,
)
from app.services import embeddings, evaluation, graph, graphrag, learning, media, redteam, report, trends
from app.services.review import PostNotFound, apply_review

router = APIRouter(prefix="/api")


def get_db() -> Iterator[sqlite3.Connection]:
    conn = database.connect()
    try:
        yield conn
    finally:
        conn.close()


DB = Annotated[sqlite3.Connection, Depends(get_db)]


def post_filters(
    category: Category | None = None,
    review_status: Literal["pending", "confirmed", "corrected", "marked_uncertain"] | None = None,
    priority: Literal["urgent", "high", "normal", "low"] | None = None,
    topic_id: str | None = Query(None, max_length=64),
    hashtag: str | None = Query(None, max_length=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    max_confidence: float | None = Query(None, ge=0, le=1),
    language: str | None = Query(None, max_length=8),
    search: str | None = Query(None, max_length=200),
) -> repo.PostFilters:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be before date_to")
    return repo.PostFilters(category, review_status, priority, topic_id, hashtag, date_from, date_to,
                            min_confidence, max_confidence, language, search)


Filters = Annotated[repo.PostFilters, Depends(post_filters)]


@router.get("/health")
def health(conn: DB) -> dict:
    posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    return {"status": "ok", "app": config.APP_NAME, "version": config.APP_VERSION, "posts_loaded": posts}


@router.get("/dataset", response_model=DatasetInfo)
def dataset(conn: DB) -> DatasetInfo:
    return report.dataset_info(conn)


@router.get("/topics")
def topics(conn: DB) -> list[dict]:
    return [t.model_dump() for t in repo.get_topics(conn).values()]


@router.get("/dashboard/summary")
def dashboard_summary(conn: DB, f: Filters) -> dict:
    summary = trends.dashboard_summary(repo.all_posts(conn, f), repo.get_topics(conn))
    ev = evaluation.run_evaluation()
    summary["evaluation_false_positive_rate"] = ev["contextual"]["harm_binary"]["false_positive_rate"]
    summary["baseline_false_positive_rate"] = ev["baseline"]["harm_binary"]["false_positive_rate"]
    summary["evaluation_set_size"] = ev["dataset"]["size"]
    summary["dataset"] = report.dataset_info(conn).model_dump(mode="json")
    return summary


@router.get("/posts", response_model=PostPage)
def list_posts(
    conn: DB,
    f: Filters,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: Literal["priority", "newest", "oldest", "confidence_asc", "confidence_desc"] = "priority",
) -> PostPage:
    items, total = repo.query_posts(conn, f, page, page_size, sort)
    return PostPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/posts/{post_id}", response_model=PostWithClassification)
def get_post(post_id: str, conn: DB) -> PostWithClassification:
    item = repo.get_post(conn, post_id)
    if item is None:
        raise HTTPException(404, f"Post '{post_id}' not found")
    return item


@router.post("/posts/{post_id}/review", response_model=PostWithClassification)
def review_post(post_id: str, req: ReviewRequest, conn: DB) -> PostWithClassification:
    try:
        return apply_review(conn, post_id, req)
    except PostNotFound:
        raise HTTPException(404, f"Post '{post_id}' not found") from None


@router.get("/posts/{post_id}/audit", response_model=list[AuditEntry])
def post_audit(post_id: str, conn: DB) -> list[AuditEntry]:
    return repo.list_audit(conn, post_id)


@router.get("/audit", response_model=list[AuditEntry])
def audit(conn: DB, limit: int = Query(100, ge=1, le=1000)) -> list[AuditEntry]:
    return repo.list_audit(conn, limit=limit)


@router.get("/network", response_model=Graph)
def network(
    conn: DB,
    f: Filters,
    edge_types: Annotated[list[Literal["USES_HASHTAG", "MENTIONS_TOPIC", "SIMILAR_CONTENT", "PUBLICLY_LINKED_TO",
                                       "SHARES_IMAGE"]] | None, Query()] = None,
    max_posts: int = Query(200, ge=1, le=500),
) -> Graph:
    ids, matrix, model = embeddings.load_embeddings(conn)
    return graph.build_graph(
        repo.all_posts(conn, f), repo.get_topics(conn), set(edge_types) if edge_types else None, max_posts,
        vectors=dict(zip(ids, matrix)) if model else None, vector_model=model,
        similarity_threshold=embeddings.threshold_for(model) if model else graph.SIMILARITY_THRESHOLD,
        image_hashes=media.all_hashes(conn), communities=graphrag.membership(conn),
    )


@router.get("/trends")
def get_trends(conn: DB, f: Filters, granularity: Literal["day", "week"] = "week") -> dict:
    return trends.compute_trends(repo.all_posts(conn, f), repo.get_topics(conn), granularity)


@router.get("/evaluation")
def get_evaluation(conn: DB) -> dict:
    return {**evaluation.run_evaluation(), "reviewer_feedback": evaluation.reviewer_feedback(conn),
            "red_team": redteam.load_results(), "learning": learning.status(conn)}


@router.get("/posts/{post_id}/media")
def post_media(post_id: str, conn: DB) -> list[dict]:
    if repo.get_post(conn, post_id) is None:
        raise HTTPException(404, f"Post '{post_id}' not found")
    return media.post_media(conn, post_id)


@router.get("/media/{file}")
def media_file(file: str) -> FileResponse:
    try:
        path = media.media_path(file)
    except ValueError:
        raise HTTPException(404, "Not found") from None
    if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(404, "Not found")
    return FileResponse(path)


@router.get("/search/semantic")
def semantic_search(conn: DB, q: str = Query(..., min_length=2, max_length=300), k: int = Query(10, ge=1, le=50)) -> dict:
    _, _, model = embeddings.load_embeddings(conn)
    results = []
    for pid, score in embeddings.semantic_search(conn, q, k):
        item = repo.get_post(conn, pid)
        if item:
            results.append({"score": score, "item": item.model_dump(mode="json")})
    return {"query": q, "model": model, "results": results}


@router.get("/graphrag/communities")
def communities(conn: DB) -> list[dict]:
    return graphrag.list_communities(conn)


class Actor(BaseModel):
    reviewer: str = Field(default="demo_reviewer", min_length=1, max_length=64)


class Question(Actor):
    question: str = Field(min_length=3, max_length=500)


@router.post("/graphrag/build")
def build_communities(body: Actor, conn: DB) -> dict:
    return graphrag.build_communities(conn, actor=body.reviewer)


@router.post("/graphrag/ask")
def ask(body: Question, conn: DB) -> dict:
    return graphrag.ask(conn, body.question, actor=body.reviewer)


@router.post("/learning/reclassify")
def reclassify(body: Actor, conn: DB) -> dict:
    return learning.reclassify(conn, actor=body.reviewer)


@router.get("/export/report")
def export_report(conn: DB, reviewer: str = Query("demo_reviewer", max_length=64)) -> dict:
    return report.build_report(conn, reviewer)
