"""SQLite storage. Lists and dicts are stored as JSON text for simplicity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    published_at TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    public_topic_ids TEXT NOT NULL,
    author_reference TEXT,
    interaction_reference_ids TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS classifications (
    post_id TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_spans TEXT NOT NULL,
    explanation TEXT NOT NULL,
    signals TEXT NOT NULL,
    category_scores TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    classified_at TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending',
    review_priority TEXT NOT NULL DEFAULT 'normal',
    reviewer_category TEXT,
    reviewer_note TEXT,
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    post_id TEXT,
    details TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
    post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    file TEXT NOT NULL,
    pdq TEXT,
    quality INTEGER,
    hash_match TEXT,
    PRIMARY KEY (post_id, idx)
);

CREATE TABLE IF NOT EXISTS embeddings (
    post_id TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    vector BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS communities (
    id TEXT PRIMARY KEY,
    built_at TEXT NOT NULL,
    engine TEXT NOT NULL,
    size INTEGER NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS community_members (
    community_id TEXT NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    PRIMARY KEY (community_id, post_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at);
CREATE INDEX IF NOT EXISTS idx_cls_category ON classifications(category);
CREATE INDEX IF NOT EXISTS idx_cls_status ON classifications(review_status);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else config.DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


# Columns added after the first release; added in place to databases created earlier.
_MIGRATIONS = [
    ("posts", "media", "TEXT NOT NULL DEFAULT '[]'"),
    ("classifications", "media_observations", "TEXT NOT NULL DEFAULT '[]'"),
]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, column, decl in _MIGRATIONS:
        if column not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    """Delete all stored data (posts, classifications, media hashes, embeddings, communities, topics, audit log)."""
    conn.executescript(
        "DELETE FROM community_members; DELETE FROM communities; DELETE FROM media; DELETE FROM embeddings; "
        "DELETE FROM classifications; DELETE FROM posts; DELETE FROM topics; DELETE FROM audit_log;"
    )
    conn.commit()
