"""Scripted behaviour of the sandbox's simulated community members.

The NPCs are deliberately deterministic so the demo is reproducible: the
gatekeeper of the private group screens join answers, then DMs new members
and eventually offers an invite to the secret group.
"""

from __future__ import annotations

import json
import re
import sqlite3

from app.sandbox.store import utcnow

GATEKEEPER = "u_nightlight"
SCREENED_GROUP = "g_rip"
SECRET_GROUP = "g_ann"

_OUTSIDER = re.compile(r"\b(journalist|reporter|press|police|cop|officer|research(er)?|study|studying|academic|report)\b", re.I)
_HOSTILE = re.compile(r"\b(sick|disgusting|monster|evil|victims|shame)\b", re.I)


def _get(conn: sqlite3.Connection, key: str) -> str | None:
    r = conn.execute("SELECT value FROM sb_npc_state WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else None


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO sb_npc_state VALUES (?, ?)", (key, value))


def _dm(conn: sqlite3.Connection, sender: str, recipient: str, text: str) -> None:
    conn.execute("INSERT INTO sb_messages (sender, recipient, created_at, text) VALUES (?, ?, ?, ?)",
                 (sender, recipient, utcnow().isoformat(), text))


def review_join_request(conn: sqlite3.Connection, request_id: int) -> dict:
    req = conn.execute("SELECT * FROM sb_join_requests WHERE id = ?", (request_id,)).fetchone()
    group = conn.execute("SELECT * FROM sb_groups WHERE id = ?", (req["group_id"],)).fetchone()
    answers = json.loads(req["answers"])
    questions = json.loads(group["join_questions"])
    joined = " ".join(answers)

    if len(answers) < len(questions) or any(len(a.strip()) < 2 for a in answers):
        status, note = "declined", "answer all questions"
    elif req["group_id"] == SCREENED_GROUP and (
        _OUTSIDER.search(" ".join(answers[:2])) or _HOSTILE.search(joined)
        or re.match(r"\s*(yes|yeah|yep|i am)\b", answers[2], re.I)
    ):
        status, note = "declined", "no press, no cops, no tourists"
    elif req["group_id"] == SCREENED_GROUP and len(answers[1].strip()) < 15:
        status, note = "declined", "low effort answer"
    else:
        status, note = "approved", None

    conn.execute("UPDATE sb_join_requests SET status = ?, decided_at = ?, decision_note = ? WHERE id = ?",
                 (status, utcnow().isoformat(), note, request_id))
    if status == "approved":
        conn.execute("INSERT OR IGNORE INTO sb_members VALUES (?, ?, ?)", (req["group_id"], req["user_id"], utcnow().isoformat()))
        if req["group_id"] == SCREENED_GROUP:
            _dm(conn, GATEKEEPER, req["user_id"], "welcome. you seem real. read the pinned post. we don't do tourists here.")
    conn.commit()
    return {"status": status, "note": note}


def on_feed_read(conn: sqlite3.Connection, group_id: str, viewer: str) -> None:
    """After a new member has read the screened group's feed, the gatekeeper makes contact."""
    if group_id != SCREENED_GROUP or viewer == GATEKEEPER:
        return
    if not conn.execute("SELECT 1 FROM sb_members WHERE group_id = ? AND user_id = ?", (group_id, viewer)).fetchone():
        return
    key = f"invite_question:{viewer}"
    if _get(conn, key):
        return
    _set(conn, key, "sent")
    _dm(conn, GATEKEEPER, viewer, "saw you lurking. there's a chat for friday. only for the serious ones. you want in?")
    conn.commit()


def on_message(conn: sqlite3.Connection, sender: str, recipient: str, text: str) -> None:
    """The gatekeeper replies to the invite question: hostile or outsider replies end contact, others get the link."""
    if recipient != GATEKEEPER or _get(conn, f"invite_question:{sender}") != "sent":
        return
    if _OUTSIDER.search(text) or _HOSTILE.search(text):
        _set(conn, f"invite_question:{sender}", "refused")
        _dm(conn, GATEKEEPER, sender, "nah. you're not one of us.")
    else:
        code = conn.execute("SELECT invite_code FROM sb_groups WHERE id = ?", (SECRET_GROUP,)).fetchone()["invite_code"]
        _set(conn, f"invite_question:{sender}", "invited")
        _set(conn, f"invite:{code}:{sender}", "issued")
        _dm(conn, GATEKEEPER, sender, f"fine. don't make me regret it. sandbox://invite/{code}")
    conn.commit()


def invite_issued_to(conn: sqlite3.Connection, code: str, uid: str) -> bool:
    return _get(conn, f"invite:{code}:{uid}") == "issued"
