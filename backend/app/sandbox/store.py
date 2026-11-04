"""Storage and seeding for the sandbox social network (a simulated Facebook).

Everything here is fictional. The sandbox exists so the Sentinel agent can be
demonstrated end to end without touching a real platform.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app import config

SANDBOX_WORLD_PATH = config.DATA_DIR / "sandbox" / "world.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sb_users (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, bio TEXT NOT NULL, avatar_color TEXT NOT NULL,
    is_persona INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sb_groups (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, privacy TEXT NOT NULL, member_count INTEGER NOT NULL,
    admin TEXT NOT NULL, description TEXT NOT NULL, cover_color TEXT NOT NULL,
    protected_space INTEGER NOT NULL DEFAULT 0, invite_code TEXT, join_questions TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sb_members (
    group_id TEXT NOT NULL, user_id TEXT NOT NULL, joined_at TEXT NOT NULL, PRIMARY KEY (group_id, user_id)
);
CREATE TABLE IF NOT EXISTS sb_join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT NOT NULL, user_id TEXT NOT NULL,
    answers TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, decided_at TEXT, decision_note TEXT
);
CREATE TABLE IF NOT EXISTS sb_posts (
    id TEXT PRIMARY KEY, group_id TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL, text TEXT NOT NULL,
    likes INTEGER NOT NULL DEFAULT 0, image TEXT, image_alt TEXT, pinned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sb_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sb_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, recipient TEXT NOT NULL, created_at TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sb_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, mission_id TEXT, group_id TEXT,
    severity TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'received'
);
CREATE TABLE IF NOT EXISTS sb_npc_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

TABLES = ["sb_users", "sb_groups", "sb_members", "sb_join_requests", "sb_posts", "sb_comments",
          "sb_messages", "sb_reports", "sb_npc_state"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_seeded(conn: sqlite3.Connection) -> bool:
    init(conn)
    return conn.execute("SELECT COUNT(*) FROM sb_users").fetchone()[0] > 0


def reset(conn: sqlite3.Connection, world: dict | None = None) -> None:
    """Re-create the sandbox world. Post times are relative to now so the feed always looks fresh."""
    init(conn)
    for t in TABLES:
        conn.execute(f"DELETE FROM {t}")
    world = world or json.loads(SANDBOX_WORLD_PATH.read_text(encoding="utf-8"))
    now = utcnow()
    for u in world["users"]:
        conn.execute("INSERT INTO sb_users VALUES (?, ?, ?, ?, ?)",
                     (u["id"], u["name"], u["bio"], u["avatar_color"], int(u.get("is_sentinel_persona", False))))
    for g in world["groups"]:
        conn.execute(
            "INSERT INTO sb_groups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (g["id"], g["name"], g["privacy"], g["member_count"], g["admin"], g["description"], g["cover_color"],
             int(g.get("protected_space", False)), g.get("invite_code"), json.dumps(g.get("join_questions", []))),
        )
        for m in g["members"]:
            conn.execute("INSERT INTO sb_members VALUES (?, ?, ?)", (g["id"], m, (now - timedelta(days=60)).isoformat()))
    for p in world["posts"]:
        created = now - timedelta(hours=p["hours_ago"])
        conn.execute(
            "INSERT INTO sb_posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (p["id"], p["group"], p["author"], created.isoformat(), p["text"], p.get("likes", 0), p.get("image"),
             p.get("image_alt"), int(p.get("pinned", False))),
        )
        for i, (author, text) in enumerate(p.get("comments", [])):
            conn.execute("INSERT INTO sb_comments (post_id, author, created_at, text) VALUES (?, ?, ?, ?)",
                         (p["id"], author, (created + timedelta(minutes=20 + i * 7)).isoformat(), text))
    conn.commit()
