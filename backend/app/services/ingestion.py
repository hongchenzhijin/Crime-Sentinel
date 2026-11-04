"""Dataset ingestion, validation, and privacy minimisation.

Records are validated with Pydantic, minimised (contact details and handles
redacted, author references replaced with non-reversible pseudonyms), stored,
and classified. No identity mapping is kept.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from app import config
from app.db import repository as repo
from app.schemas.models import ClassificationResult, MediaRef, Post, PostIn, Topic
from app.services import embeddings, media
from app.services.classification import Classifier, classify_all, get_classifier, review_priority

_REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email removed]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[link removed]"),
    (re.compile(r"(?<!\w)@\w{2,}"), "[handle removed]"),
    (re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d"), "[number removed]"),
]


_POST_REF = re.compile(r"^post_[A-Za-z0-9_-]+$")


def redact_text(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class Pseudonymiser:
    """Salted one-way hashing. The salt lives only in memory for one ingestion
    run, so pseudonyms are stable within a dataset but cannot be reversed or
    linked across runs."""

    def __init__(self) -> None:
        self._salt = secrets.token_bytes(16)

    def __call__(self, value: str | None) -> str | None:
        if not value:
            return None
        return "anon_" + hashlib.sha256(self._salt + value.encode()).hexdigest()[:10]


def minimise(record: PostIn, pseudonymise: Pseudonymiser) -> Post:
    return Post(
        id=record.id,
        source_type=record.source_type,
        source_name=record.source_name,
        source_url=None if record.is_synthetic else record.source_url,
        published_at=record.published_at,
        text=redact_text(record.text),
        language=record.language.lower(),
        hashtags=record.hashtags,
        public_topic_ids=record.public_topic_ids,
        author_reference=pseudonymise(record.author_reference),
        # Interaction references are content-level links to other public posts.
        # Anything that is not a post id (e.g. an account id) is dropped.
        interaction_reference_ids=[r for r in record.interaction_reference_ids if _POST_REF.match(r)],
        is_synthetic=record.is_synthetic,
        media=[MediaRef(file=m.file, alt_text=redact_text(m.alt_text)) for m in record.media],
    )


@dataclass
class IngestReport:
    accepted: int = 0
    rejected: list[dict] = field(default_factory=list)


def load_topics(conn: sqlite3.Connection, topics: list[dict]) -> int:
    for raw in topics:
        t = Topic.model_validate(raw)
        conn.execute(
            "INSERT OR REPLACE INTO topics (id, label, description, is_synthetic) VALUES (?, ?, ?, ?)",
            (t.id, t.label, t.description, int(t.is_synthetic)),
        )
    conn.commit()
    return len(topics)


def ingest_records(
    conn: sqlite3.Connection, records: list[dict], classifier: Classifier | None = None, actor: str = "system"
) -> IngestReport:
    classifier = classifier or get_classifier()
    pseudonymise = Pseudonymiser()
    report = IngestReport()
    now = repo.utcnow()
    posts = []
    for index, raw in enumerate(records):
        try:
            record = PostIn.model_validate(raw)
        except ValidationError as exc:
            report.rejected.append({"index": index, "id": raw.get("id") if isinstance(raw, dict) else None,
                                    "errors": [e["msg"] for e in exc.errors()]})
            continue
        posts.append(minimise(record, pseudonymise))
    for post in posts:
        repo.insert_post(conn, post, now)
    embedding_model = embeddings.store_embeddings(conn, [p.id for p in posts], [p.text for p in posts])
    for post, (result, priority) in zip(posts, classify_posts(conn, posts, classifier)):
        repo.upsert_classification(conn, post.id, result, priority, now)
        report.accepted += 1
    repo.write_audit(conn, actor, "ingest_dataset", None, {
        "accepted": report.accepted,
        "rejected": len(report.rejected),
        "model": f"{classifier.name}@{classifier.version}",
        "embedding_model": embedding_model,
        "images": sum(len(p.media) for p in posts),
    })
    conn.commit()
    return report


_PRIORITY = ["low", "normal", "high", "urgent"]


def classify_posts(conn: sqlite3.Connection, posts: list[Post], classifier: Classifier) -> list[tuple[ClassificationResult, str]]:
    """Hash each post's images, classify text + images, and apply the hash-list policy. Returns (result, priority)."""
    hash_matches = {p.id: [m["hash_match"] for m in media.store_media(conn, p) if m["hash_match"]] for p in posts}
    items = [(p.text, p.language, [media.media_path(m.file) for m in p.media]) for p in posts]
    out = []
    for post, result in zip(posts, classify_all(classifier, items)):
        result, needs_review = media.apply_hash_matches(result, hash_matches[post.id])
        priority = review_priority(result.category, result.confidence, result.category_scores)
        if needs_review and _PRIORITY.index(priority) < _PRIORITY.index("high"):
            priority = "high"
        out.append((result, priority))
    return out


def ingest_file(conn: sqlite3.Connection, posts_path: Path, topics_path: Path | None = None,
                classifier: Classifier | None = None) -> IngestReport:
    if topics_path and topics_path.exists():
        load_topics(conn, json.loads(topics_path.read_text(encoding="utf-8")))
    records = json.loads(posts_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Dataset file must contain a JSON array of post records")
    if config.MEDIA_MANIFEST_PATH.exists():  # images are kept in a separate manifest (see generate_dataset_media.py)
        manifest = json.loads(config.MEDIA_MANIFEST_PATH.read_text(encoding="utf-8"))
        for r in records:
            if isinstance(r, dict) and r.get("id") in manifest:
                r["media"] = manifest[r["id"]]
    return ingest_records(conn, records, classifier)


def purge_expired(conn: sqlite3.Connection, retention_days: int = config.RETENTION_DAYS) -> int:
    """Delete posts (and their classifications) ingested before the retention cut-off."""
    cutoff = (repo.utcnow() - timedelta(days=retention_days)).isoformat()
    deleted = conn.execute("DELETE FROM posts WHERE ingested_at < ?", (cutoff,)).rowcount
    repo.write_audit(conn, "system", "purge_expired", None, {"deleted": deleted, "retention_days": retention_days})
    conn.commit()
    return deleted
