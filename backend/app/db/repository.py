"""Row <-> model conversion and the queries shared by several services."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.models import (
    AuditEntry,
    Category,
    Classification,
    ClassificationResult,
    MediaRef,
    Post,
    PostWithClassification,
    Topic,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def row_to_post(row: sqlite3.Row) -> Post:
    return Post(
        id=row["id"],
        source_type=row["source_type"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        published_at=row["published_at"],
        text=row["text"],
        language=row["language"],
        hashtags=json.loads(row["hashtags"]),
        public_topic_ids=json.loads(row["public_topic_ids"]),
        author_reference=row["author_reference"],
        interaction_reference_ids=json.loads(row["interaction_reference_ids"]),
        is_synthetic=bool(row["is_synthetic"]),
        media=[MediaRef(**m) for m in json.loads(row["media"] or "[]")],
    )


def row_to_classification(row: sqlite3.Row) -> Classification:
    return Classification(
        post_id=row["post_id"],
        category=row["category"],
        confidence=row["confidence"],
        evidence_spans=json.loads(row["evidence_spans"]),
        explanation=row["explanation"],
        signals=json.loads(row["signals"]),
        category_scores=json.loads(row["category_scores"]),
        media_observations=json.loads(row["media_observations"] or "[]"),
        model_name=row["model_name"],
        model_version=row["model_version"],
        classified_at=row["classified_at"],
        review_status=row["review_status"],
        review_priority=row["review_priority"],
        reviewer_category=row["reviewer_category"],
        reviewer_note=row["reviewer_note"],
        reviewed_at=row["reviewed_at"],
    )


def insert_post(conn: sqlite3.Connection, post: Post, ingested_at: datetime) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO posts (id, source_type, source_name, source_url, published_at, text, language,
               hashtags, public_topic_ids, author_reference, interaction_reference_ids, is_synthetic, ingested_at, media)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            post.id,
            post.source_type,
            post.source_name,
            post.source_url,
            post.published_at.isoformat(),
            post.text,
            post.language,
            json.dumps(post.hashtags),
            json.dumps(post.public_topic_ids),
            post.author_reference,
            json.dumps(post.interaction_reference_ids),
            int(post.is_synthetic),
            ingested_at.isoformat(),
            json.dumps([m.model_dump() for m in post.media]),
        ),
    )


def upsert_classification(
    conn: sqlite3.Connection, post_id: str, result: ClassificationResult, priority: str, classified_at: datetime
) -> None:
    """Store a fresh model output. Resets any prior review for this post."""
    conn.execute(
        """INSERT OR REPLACE INTO classifications (post_id, category, confidence, evidence_spans, explanation, signals,
               category_scores, model_name, model_version, classified_at, review_status, review_priority,
               media_observations)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            post_id,
            result.category.value,
            result.confidence,
            json.dumps([s.model_dump(mode="json") for s in result.evidence_spans]),
            result.explanation,
            json.dumps(result.signals),
            json.dumps(result.category_scores),
            result.model_name,
            result.model_version,
            classified_at.isoformat(),
            priority,
            json.dumps([o.model_dump() for o in result.media_observations]),
        ),
    )


def update_model_output(
    conn: sqlite3.Connection, post_id: str, result: ClassificationResult, priority: str, classified_at: datetime
) -> None:
    """Replace the model output for a post, keeping any human review decision intact."""
    conn.execute(
        """UPDATE classifications SET category = ?, confidence = ?, evidence_spans = ?, explanation = ?, signals = ?,
               category_scores = ?, model_name = ?, model_version = ?, classified_at = ?, review_priority = ?,
               media_observations = ?
           WHERE post_id = ?""",
        (
            result.category.value,
            result.confidence,
            json.dumps([s.model_dump(mode="json") for s in result.evidence_spans]),
            result.explanation,
            json.dumps(result.signals),
            json.dumps(result.category_scores),
            result.model_name,
            result.model_version,
            classified_at.isoformat(),
            priority,
            json.dumps([o.model_dump() for o in result.media_observations]),
            post_id,
        ),
    )


def write_audit(conn: sqlite3.Connection, actor: str, action: str, post_id: str | None, details: dict) -> None:
    conn.execute(
        "INSERT INTO audit_log (timestamp, actor, action, post_id, details) VALUES (?, ?, ?, ?, ?)",
        (utcnow().isoformat(), actor, action, post_id, json.dumps(details)),
    )


def list_audit(conn: sqlite3.Connection, post_id: str | None = None, limit: int = 200) -> list[AuditEntry]:
    if post_id:
        rows = conn.execute("SELECT * FROM audit_log WHERE post_id = ? ORDER BY id DESC LIMIT ?", (post_id, limit))
    else:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    return [
        AuditEntry(
            id=r["id"], timestamp=r["timestamp"], actor=r["actor"], action=r["action"], post_id=r["post_id"],
            details=json.loads(r["details"]),
        )
        for r in rows
    ]


def get_topics(conn: sqlite3.Connection) -> dict[str, Topic]:
    return {
        r["id"]: Topic(id=r["id"], label=r["label"], description=r["description"], is_synthetic=bool(r["is_synthetic"]))
        for r in conn.execute("SELECT * FROM topics ORDER BY id")
    }


@dataclass
class PostFilters:
    category: Category | None = None  # matches the effective (reviewer-or-model) category
    review_status: str | None = None
    priority: str | None = None
    topic_id: str | None = None
    hashtag: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    language: str | None = None
    search: str | None = None


_PRIORITY_ORDER = "CASE c.review_priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END"
_SORTS = {
    "priority": f"{_PRIORITY_ORDER}, p.published_at DESC",
    "newest": "p.published_at DESC",
    "oldest": "p.published_at ASC",
    "confidence_asc": "c.confidence ASC",
    "confidence_desc": "c.confidence DESC",
}


def _where(f: PostFilters) -> tuple[str, list]:
    clauses, params = ["1=1"], []
    if f.category:
        clauses.append("COALESCE(c.reviewer_category, c.category) = ?")
        params.append(f.category.value)
    if f.review_status:
        clauses.append("c.review_status = ?")
        params.append(f.review_status)
    if f.priority:
        clauses.append("c.review_priority = ?")
        params.append(f.priority)
    if f.topic_id:
        clauses.append("EXISTS (SELECT 1 FROM json_each(p.public_topic_ids) WHERE value = ?)")
        params.append(f.topic_id)
    if f.hashtag:
        clauses.append("EXISTS (SELECT 1 FROM json_each(p.hashtags) WHERE value = ?)")
        params.append(f.hashtag.lstrip("#").lower())
    if f.date_from:
        clauses.append("p.published_at >= ?")
        params.append(f.date_from.isoformat())
    if f.date_to:
        clauses.append("p.published_at <= ?")
        params.append(f.date_to.isoformat())
    if f.min_confidence is not None:
        clauses.append("c.confidence >= ?")
        params.append(f.min_confidence)
    if f.max_confidence is not None:
        clauses.append("c.confidence <= ?")
        params.append(f.max_confidence)
    if f.language:
        clauses.append("p.language = ?")
        params.append(f.language)
    if f.search:
        clauses.append("p.text LIKE ?")
        params.append(f"%{f.search}%")
    return " AND ".join(clauses), params


def query_posts(
    conn: sqlite3.Connection, f: PostFilters, page: int = 1, page_size: int = 25, sort: str = "priority"
) -> tuple[list[PostWithClassification], int]:
    where, params = _where(f)
    base = f"FROM posts p JOIN classifications c ON c.post_id = p.id WHERE {where}"
    total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT p.*, c.* {base} ORDER BY {_SORTS.get(sort, _SORTS['priority'])} LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    topics = get_topics(conn)
    items = [
        PostWithClassification(
            post=row_to_post(r),
            classification=row_to_classification(r),
            topics=[topics[t] for t in json.loads(r["public_topic_ids"]) if t in topics],
        )
        for r in rows
    ]
    return items, total


def all_posts(conn: sqlite3.Connection, f: PostFilters | None = None) -> list[PostWithClassification]:
    items, _ = query_posts(conn, f or PostFilters(), page=1, page_size=1_000_000, sort="oldest")
    return items


def get_post(conn: sqlite3.Connection, post_id: str) -> PostWithClassification | None:
    row = conn.execute(
        "SELECT p.*, c.* FROM posts p JOIN classifications c ON c.post_id = p.id WHERE p.id = ?", (post_id,)
    ).fetchone()
    if row is None:
        return None
    topics = get_topics(conn)
    return PostWithClassification(
        post=row_to_post(row),
        classification=row_to_classification(row),
        topics=[topics[t] for t in json.loads(row["public_topic_ids"]) if t in topics],
    )
