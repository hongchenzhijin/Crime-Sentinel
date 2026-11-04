"""The sandbox platform's behaviour: what a given user can see and do.

Both the simulated Facebook UI and the Sentinel agent go through these
functions, so the agent sees exactly what a real account would see: private
group feeds only after admission, secret groups only via an invite.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.sandbox import npc
from app.sandbox.store import utcnow


class PlatformError(Exception):
    """An action the platform would refuse (e.g. reading a private feed as a non-member)."""


def _user(conn: sqlite3.Connection, uid: str) -> dict:
    r = conn.execute("SELECT * FROM sb_users WHERE id = ?", (uid,)).fetchone()
    if not r:
        raise PlatformError(f"unknown user {uid}")
    return {"id": r["id"], "name": r["name"], "bio": r["bio"], "avatar_color": r["avatar_color"]}


def users(conn: sqlite3.Connection) -> dict[str, dict]:
    return {r["id"]: {"id": r["id"], "name": r["name"], "bio": r["bio"], "avatar_color": r["avatar_color"],
                      "is_persona": bool(r["is_persona"])}
            for r in conn.execute("SELECT * FROM sb_users")}


def is_member(conn: sqlite3.Connection, group_id: str, uid: str) -> bool:
    return conn.execute("SELECT 1 FROM sb_members WHERE group_id = ? AND user_id = ?", (group_id, uid)).fetchone() is not None


def _group_row(conn: sqlite3.Connection, group_id: str) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM sb_groups WHERE id = ?", (group_id,)).fetchone()
    if not r:
        raise PlatformError(f"group {group_id} not found")
    return r


def group_view(conn: sqlite3.Connection, group_id: str, viewer: str) -> dict:
    g = _group_row(conn, group_id)
    member = is_member(conn, group_id, viewer)
    if g["privacy"] == "secret" and not member:
        raise PlatformError("group not found")  # secret groups are invisible to non-members
    pending = conn.execute(
        "SELECT status FROM sb_join_requests WHERE group_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
        (group_id, viewer),
    ).fetchone()
    return {
        "id": g["id"], "name": g["name"], "privacy": g["privacy"], "member_count": g["member_count"],
        "description": g["description"], "cover_color": g["cover_color"], "admin": _user(conn, g["admin"]),
        "protected_space": bool(g["protected_space"]),
        "join_questions": json.loads(g["join_questions"]),
        "viewer_is_member": member,
        "viewer_request_status": pending["status"] if pending else None,
        "can_read_feed": g["privacy"] == "public" or member,
    }


def search_groups(conn: sqlite3.Connection, query: str, viewer: str) -> list[dict]:
    """Platform search: public and private groups are discoverable; secret groups are not."""
    q = f"%{query.strip().lower()}%"
    rows = conn.execute(
        "SELECT id FROM sb_groups WHERE privacy != 'secret' AND (lower(name) LIKE ? OR lower(description) LIKE ?)",
        (q, q),
    ).fetchall()
    return [group_view(conn, r["id"], viewer) for r in rows]


def my_groups(conn: sqlite3.Connection, viewer: str) -> list[dict]:
    rows = conn.execute("SELECT group_id FROM sb_members WHERE user_id = ?", (viewer,)).fetchall()
    return [group_view(conn, r["group_id"], viewer) for r in rows]


def feed(conn: sqlite3.Connection, group_id: str, viewer: str, trigger_npc: bool = True) -> list[dict]:
    g = group_view(conn, group_id, viewer)
    if not g["can_read_feed"]:
        raise PlatformError("join this group to see its posts")
    us = users(conn)
    posts = []
    for p in conn.execute("SELECT * FROM sb_posts WHERE group_id = ? ORDER BY pinned DESC, created_at DESC", (group_id,)):
        comments = [
            {"id": c["id"], "author": us[c["author"]], "created_at": c["created_at"], "text": c["text"]}
            for c in conn.execute("SELECT * FROM sb_comments WHERE post_id = ? ORDER BY created_at", (p["id"],))
        ]
        posts.append({
            "id": p["id"], "group_id": group_id, "author": us[p["author"]], "created_at": p["created_at"],
            "text": p["text"], "likes": p["likes"], "image": p["image"], "image_alt": p["image_alt"],
            "pinned": bool(p["pinned"]), "comments": comments,
        })
    if trigger_npc:
        npc.on_feed_read(conn, group_id, viewer)
    return posts


def request_join(conn: sqlite3.Connection, group_id: str, viewer: str, answers: list[str]) -> dict:
    g = group_view(conn, group_id, viewer)
    if g["viewer_is_member"]:
        return {"status": "already_member"}
    if g["privacy"] == "public":
        conn.execute("INSERT OR IGNORE INTO sb_members VALUES (?, ?, ?)", (group_id, viewer, utcnow().isoformat()))
        conn.commit()
        return {"status": "approved"}
    cur = conn.execute(
        "INSERT INTO sb_join_requests (group_id, user_id, answers, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (group_id, viewer, json.dumps(answers), utcnow().isoformat()),
    )
    conn.commit()
    decision = npc.review_join_request(conn, cur.lastrowid)
    return {"status": decision["status"], "note": decision.get("note")}


def accept_invite(conn: sqlite3.Connection, code: str, viewer: str) -> dict:
    g = conn.execute("SELECT id FROM sb_groups WHERE invite_code = ?", (code.strip(),)).fetchone()
    if not g:
        raise PlatformError("invite link is invalid or expired")
    if not npc.invite_issued_to(conn, code, viewer):
        raise PlatformError("this invite was not issued to you")
    conn.execute("INSERT OR IGNORE INTO sb_members VALUES (?, ?, ?)", (g["id"], viewer, utcnow().isoformat()))
    conn.commit()
    return group_view(conn, g["id"], viewer)


def send_message(conn: sqlite3.Connection, sender: str, recipient: str, text: str) -> dict:
    _user(conn, recipient)
    now = utcnow().isoformat()
    cur = conn.execute("INSERT INTO sb_messages (sender, recipient, created_at, text) VALUES (?, ?, ?, ?)",
                       (sender, recipient, now, text))
    conn.commit()
    npc.on_message(conn, sender, recipient, text)
    return {"id": cur.lastrowid, "created_at": now}


def threads(conn: sqlite3.Connection, viewer: str) -> list[dict]:
    us = users(conn)
    rows = conn.execute(
        "SELECT * FROM sb_messages WHERE sender = ? OR recipient = ? ORDER BY created_at, id", (viewer, viewer)
    ).fetchall()
    by_other: dict[str, list[dict]] = {}
    for m in rows:
        other = m["recipient"] if m["sender"] == viewer else m["sender"]
        by_other.setdefault(other, []).append(
            {"id": m["id"], "from": us[m["sender"]], "created_at": m["created_at"], "text": m["text"],
             "outgoing": m["sender"] == viewer}
        )
    return [{"with": us[o], "messages": msgs} for o, msgs in by_other.items()]


def submit_report(conn: sqlite3.Connection, mission_id: str | None, group_id: str | None, severity: str,
                  title: str, body: dict[str, Any]) -> int:
    cur = conn.execute(
        "INSERT INTO sb_reports (created_at, mission_id, group_id, severity, title, body) VALUES (?, ?, ?, ?, ?, ?)",
        (utcnow().isoformat(), mission_id, group_id, severity, title, json.dumps(body)),
    )
    conn.commit()
    return cur.lastrowid


def reports(conn: sqlite3.Connection) -> list[dict]:
    return [
        {"id": r["id"], "created_at": r["created_at"], "mission_id": r["mission_id"], "group_id": r["group_id"],
         "severity": r["severity"], "title": r["title"], "body": json.loads(r["body"]), "status": r["status"]}
        for r in conn.execute("SELECT * FROM sb_reports ORDER BY id DESC")
    ]
