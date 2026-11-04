"""Mission orchestrator for the Sentinel agent.

The mission runs as a deterministic state machine:
PLAN -> DISCOVER -> TRIAGE -> APPROACH -> OBSERVE -> INBOX -> ESCALATE -> HANDOFF.
Muse makes the judgement calls: search planning, in-character drafts, safety
judging, post and community analysis, and report summaries. Code enforces the
policy: which spaces may be entered, when a human must approve, and what counts
as an escalation. Every step is written to an event log that the Mission
Control UI streams.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import time
import traceback
from typing import Any

from app.agent.analyst import TIERS, Analyst
from app.agent.governor import SafetyGovernor, Verdict
from app.agent.muse import FAST_MODEL, MuseClient, MuseError, UsageLedger
from app.agent.persona import Persona
from app.agent.reporter import build_report
from app.db import database
from app.db import repository as repo
from app.sandbox import platform as sb
from app.sandbox import store
from app.services.classification import ContextualRuleClassifier
from app.services.ingestion import ingest_records, load_topics

PERSONA_ID = "u_persona"
INVITE_RE = re.compile(r"sandbox://invite/([\w-]+)")
DEFAULT_QUERIES = ["ridgeview", "rest in power", "true crime"]
ESCALATE_FROM = TIERS.index("glorification_community")

SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, mode TEXT NOT NULL, brief TEXT NOT NULL,
    auto_approve TEXT NOT NULL, pace REAL NOT NULL, summary TEXT NOT NULL DEFAULT '{}', usage TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS mission_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL, ts TEXT NOT NULL, phase TEXT NOT NULL,
    actor TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL, engine TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mission_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL, created_at TEXT NOT NULL, kind TEXT NOT NULL,
    title TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, decided_at TEXT, decided_by TEXT, note TEXT
);
"""

_running: dict[str, "MissionRunner"] = {}


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    store.init(conn)
    conn.commit()


class MissionStopped(Exception):
    pass


class MissionRunner:
    def __init__(self, mission_id: str, brief: str, auto_approve: str, pace: float, force_offline: bool):
        self.id = mission_id
        self.brief = brief
        self.auto_approve = auto_approve  # none | messages | all
        self.pace = pace
        self.ledger = UsageLedger()
        self.muse = MuseClient(ledger=self.ledger, force_offline=force_offline)
        self.persona = Persona(self.muse)
        self.governor = SafetyGovernor(self.muse)
        self.analyst = Analyst(self.muse)
        self.stop_flag = threading.Event()
        self.phase = "plan"
        self.conn: sqlite3.Connection | None = None
        self.observed: dict[str, dict] = {}       # group_id -> {"group", "posts", "analyses", "assessment"}
        self.access_paths: dict[str, list] = {}
        self.reported: set[str] = set()
        self.handled_messages: set[int] = set()

    # ---- infrastructure ----------------------------------------------------
    def emit(self, actor: str, kind: str, title: str, detail: dict | None = None, engine: str = "code") -> int:
        assert self.conn
        cur = self.conn.execute(
            "INSERT INTO mission_events (mission_id, ts, phase, actor, kind, title, detail, engine) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.id, store.utcnow().isoformat(), self.phase, actor, kind, title, json.dumps(detail or {}, default=str), engine),
        )
        self.conn.execute("UPDATE missions SET usage = ? WHERE id = ?", (json.dumps(self.ledger.as_dict()), self.id))
        self.conn.commit()
        if self.pace:
            time.sleep(self.pace)
        if self.stop_flag.is_set():
            raise MissionStopped()
        return cur.lastrowid

    def set_status(self, status: str, summary: dict | None = None) -> None:
        assert self.conn
        self.conn.execute("UPDATE missions SET status = ?, summary = COALESCE(?, summary), usage = ? WHERE id = ?",
                          (status, json.dumps(summary) if summary else None, json.dumps(self.ledger.as_dict()), self.id))
        self.conn.commit()

    def approval(self, kind: str, title: str, payload: dict) -> tuple[bool, dict]:
        """Ask a human. Blocks until decided (or auto-approves according to the mission setting)."""
        assert self.conn
        auto = self.auto_approve == "all" or (self.auto_approve == "messages" and kind in ("message", "join", "action"))
        now = store.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT INTO mission_approvals (mission_id, created_at, kind, title, payload, status, decided_at, decided_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.id, now, kind, title, json.dumps(payload, default=str), "approved" if auto else "pending",
             now if auto else None, "auto-approve setting" if auto else None),
        )
        self.conn.commit()
        aid = cur.lastrowid
        if auto:
            self.emit("human", "approval", f"Auto-approved: {title}", {"approval_id": aid, "kind": kind}, "auto-approve")
            return True, payload
        self.set_status("awaiting_approval")
        self.emit("human", "approval_requested", f"Waiting for human approval: {title}", {"approval_id": aid, "kind": kind})
        while not self.stop_flag.is_set():
            row = self.conn.execute("SELECT * FROM mission_approvals WHERE id = ?", (aid,)).fetchone()
            if row["status"] != "pending":
                self.set_status("running")
                ok = row["status"] == "approved"
                self.emit("human", "approval", f"{'Approved' if ok else 'Rejected'} by {row['decided_by']}: {title}",
                          {"approval_id": aid, "note": row["note"]}, "human")
                return ok, json.loads(row["payload"])
            time.sleep(0.4)
        raise MissionStopped()

    # ---- run ---------------------------------------------------------------
    def run(self) -> None:
        self.conn = database.connect()
        init(self.conn)
        try:
            self.set_status("running")
            engine = f"Muse ({FAST_MODEL})" if self.muse.enabled else "OFFLINE - scripted fallback (set MODEL_API_KEY for Muse)"
            self.emit("system", "start", f"Mission started. Intelligence engine: {engine}",
                      {"brief": self.brief, "persona": self.persona.name, "auto_approve": self.auto_approve})
            queries = self.plan()
            groups = self.discover(queries)
            for g in groups:
                self.triage(g)
            self.inbox_loop()
            self.handoff()
            self.set_status("completed", self.summary())
            self.emit("system", "done", "Mission complete. Evidence handed to the human review queue.", self.summary())
        except MissionStopped:
            self.set_status("stopped", self.summary())
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            self.set_status("failed", {"error": str(exc)})
            try:
                self.emit("system", "error", f"Mission failed: {exc}", {"traceback": traceback.format_exc()[-2000:]})
            except MissionStopped:
                pass
        finally:
            _running.pop(self.id, None)
            self.conn.close()

    # ---- phases --------------------------------------------------------------
    def plan(self) -> list[str]:
        self.phase = "plan"
        if self.muse.enabled:
            try:
                r = self.muse.chat(
                    "planner",
                    "You plan discovery searches for an authorised trust-and-safety investigation on a social platform. "
                    "Given an intelligence brief, propose 2-4 short group-search queries likely to surface the "
                    "communities described, plus nearby benign communities for contrast. "
                    'Respond with JSON only: {"queries": [str], "rationale": str}',
                    self.brief, max_tokens=300)
                queries = [q for q in r.data.get("queries", []) if isinstance(q, str) and q.strip()][:4] or DEFAULT_QUERIES
                self.emit("planner", "plan", f"Search plan: {', '.join(queries)}",
                          {"queries": queries, "rationale": r.data.get("rationale")}, f"muse:{r.model}")
                return queries
            except (MuseError, AttributeError) as exc:
                self.emit("planner", "warning", f"Muse planning failed, using default queries ({exc})")
        self.emit("planner", "plan", f"Search plan: {', '.join(DEFAULT_QUERIES)}", {"queries": DEFAULT_QUERIES}, "scripted")
        return DEFAULT_QUERIES

    def discover(self, queries: list[str]) -> list[dict]:
        self.phase = "discover"
        found: dict[str, dict] = {}
        for q in queries:
            results = sb.search_groups(self.conn, q, PERSONA_ID)
            for g in results:
                found.setdefault(g["id"], g)
            self.emit("persona", "search", f"Searched groups for \"{q}\": {len(results)} result(s)",
                      {"query": q, "results": [{"id": g["id"], "name": g["name"], "privacy": g["privacy"]} for g in results]},
                      "platform")
        self.emit("planner", "discovered", f"{len(found)} candidate communities discovered",
                  {"groups": [g["name"] for g in found.values()]})
        return list(found.values())

    def triage(self, g: dict) -> None:
        self.phase = "triage"
        protected = SafetyGovernor.check_join(g)
        if g["protected_space"] or (not g["can_read_feed"] and not protected.allowed):
            self.emit("governor", "blocked", f"Skipped \"{g['name']}\": protected support space (R6)",
                      protected.as_dict(), "rules")
            return
        if g["can_read_feed"]:
            self.emit("planner", "triage", f"\"{g['name']}\" is public - observing without joining", {"group_id": g["id"]})
            self.observe(g)
            return
        listing = self.analyst.assess_listing(g)
        self.emit("analyst", "listing", f"Listing assessment for private group \"{g['name']}\": "
                  f"{'approach' if listing['approach'] else 'do not approach'}", listing, listing["engine"])
        if listing["approach"] and self.approach(g):
            self.observe(sb.group_view(self.conn, g["id"], PERSONA_ID))

    def approach(self, g: dict) -> bool:
        self.phase = "approach"
        path = self.access_paths.setdefault(g["id"], [])
        feedback = ""
        for attempt in range(3):
            draft = self.persona.draft_join_answers(g, attempt, feedback)
            if draft.abort or not draft.content:
                self.emit("persona", "abort", f"Persona declined to approach \"{g['name']}\"", {"rationale": draft.rationale}, draft.engine)
                return False
            qa = list(zip(g["join_questions"], draft.content))
            self.emit("persona", "draft", f"Drafted admission answers for \"{g['name']}\" (attempt {attempt + 1})",
                      {"answers": [{"q": q, "a": a} for q, a in qa], "rationale": draft.rationale}, draft.engine)
            verdict = self._check_all(draft.content, f"Answers to admission questions of group '{g['name']}'")
            vid = self.emit("governor", "verdict", self._verdict_title(verdict), verdict.as_dict(), verdict.engine)
            path.append({"step": "join_answers_reviewed", "attempt": attempt + 1, "verdict": verdict.decision, "event_id": vid})
            if verdict.allowed:
                break
            feedback = verdict.feedback() or "; ".join(verdict.reasons)
        else:
            self.emit("persona", "abort", f"Could not draft compliant answers for \"{g['name']}\" - aborting approach")
            return False

        ok, payload = self.approval("join", f"Request to join \"{g['name']}\"",
                                    {"group_id": g["id"], "answers": [{"q": q, "a": a} for q, a in qa]})
        if not ok:
            return False
        result = sb.request_join(self.conn, g["id"], PERSONA_ID, [x["a"] for x in payload["answers"]])
        path.append({"step": "join_requested", "result": result["status"]})
        self.emit("platform", "join_result", f"Admin decision for \"{g['name']}\": {result['status']}", result, "platform")
        return result["status"] in ("approved", "already_member")

    def observe(self, g: dict) -> None:
        self.phase = "observe"
        posts = sb.feed(self.conn, g["id"], PERSONA_ID)
        self.emit("persona", "read", f"Read {len(posts)} posts in \"{g['name']}\" (read-only)", {"group_id": g["id"]}, "platform")
        analyses = []
        for p in posts:
            a = self.analyst.analyze_post(p, g["name"])
            analyses.append(a)
            engine = (a.get("muse") or {}).get("engine") or "rules"
            if a.get("image"):
                engine += f" + {a['image']['engine']}"
            self.emit("analyst", "post", f"{p['id']}: {a['final_category']}",
                      {"post_id": p["id"], "text": p["text"], "author": p["author"]["name"], "analysis": a}, engine)
        assessment = self.analyst.assess_group(g, posts, analyses)
        self.observed[g["id"]] = {"group": g, "posts": posts, "analyses": analyses, "assessment": assessment}
        self.emit("analyst", "assessment", f"Community assessment - \"{g['name']}\": {assessment['tier'].replace('_', ' ').upper()}",
                  {"group_id": g["id"], **assessment}, assessment["engine"])
        if TIERS.index(assessment["tier"]) >= ESCALATE_FROM:
            self.escalate(g["id"])

    def inbox_loop(self) -> None:
        self.phase = "inbox"
        for _ in range(5):
            acted = False
            for thread in sb.threads(self.conn, PERSONA_ID):
                msgs = thread["messages"]
                new_incoming = [m for m in msgs if not m["outgoing"] and m["id"] not in self.handled_messages]
                if not new_incoming:
                    continue
                for m in new_incoming:
                    self.handled_messages.add(m["id"])
                    self.emit("platform", "dm_received", f"DM from {thread['with']['name']}: \"{m['text']}\"",
                              {"from": thread["with"]["id"]}, "platform")
                last = new_incoming[-1]
                invite = INVITE_RE.search(last["text"])
                if invite:
                    acted |= self.accept_invite(invite.group(1), thread["with"])
                elif last["text"].strip().endswith("?"):
                    acted |= self.reply(thread["with"], msgs)
                else:
                    self.emit("planner", "no_reply", "No reply needed - observation first (R8)")
            if not acted:
                break

    def reply(self, other: dict, history: list[dict]) -> bool:
        feedback = ""
        for attempt in range(3):
            draft = self.persona.draft_reply(other["name"], history, attempt, feedback)
            if draft.abort or not draft.content:
                self.emit("persona", "abort", f"Persona chose not to reply to {other['name']}", {"rationale": draft.rationale}, draft.engine)
                return False
            self.emit("persona", "draft", f"Drafted reply to {other['name']} (attempt {attempt + 1}): \"{draft.content}\"",
                      {"reply": draft.content, "rationale": draft.rationale}, draft.engine)
            verdict = self.governor.check_message(draft.content, f"DM reply to {other['name']}; last message: {history[-1]['text']}")
            self.emit("governor", "verdict", self._verdict_title(verdict), verdict.as_dict(), verdict.engine)
            if verdict.allowed:
                break
            feedback = verdict.feedback() or "; ".join(verdict.reasons)
        else:
            self.emit("persona", "abort", "No compliant reply found - staying silent")
            return False
        ok, payload = self.approval("message", f"Send DM to {other['name']}", {"to": other["id"], "text": draft.content})
        if not ok:
            return False
        sb.send_message(self.conn, PERSONA_ID, payload["to"], payload["text"])
        self.emit("persona", "dm_sent", f"Sent DM to {other['name']}: \"{payload['text']}\"", payload, "platform")
        return True

    def accept_invite(self, code: str, sender: dict) -> bool:
        self.emit("planner", "invite", f"Invite link to a closed space received from {sender['name']}", {"code": code})
        ok, _ = self.approval("action", "Accept invite to closed group (observe only, no posting)", {"code": code})
        if not ok:
            return False
        try:
            g = sb.accept_invite(self.conn, code, PERSONA_ID)
        except sb.PlatformError as exc:
            self.emit("platform", "error", f"Invite failed: {exc}")
            return False
        self.access_paths.setdefault(g["id"], []).append({"step": "invite_accepted", "from": sender["id"]})
        self.emit("platform", "joined", f"Joined secret group \"{g['name']}\" via invite", {"group_id": g["id"]}, "platform")
        self.phase = "observe"
        self.observe(g)
        return True

    def escalate(self, group_id: str) -> None:
        if group_id in self.reported:
            return
        o = self.observed[group_id]
        prev_phase, self.phase = self.phase, "escalate"
        report = build_report(self.muse, self.id, o["group"], o["assessment"], o["analyses"], o["posts"],
                              self.access_paths.get(group_id, []))
        self.emit("reporter", "report_draft", f"Drafted {report['severity'].upper()} report: \"{o['group']['name']}\"",
                  report, report["summary_engine"])
        ok, _ = self.approval("report", f"Send {report['severity']} report on \"{o['group']['name']}\" to Meta Integrity", report)
        if ok:
            rid = sb.submit_report(self.conn, self.id, group_id, report["severity"],
                                   f"[{report['severity'].upper()}] {o['group']['name']}: {report['risk_tier'].replace('_', ' ')}", report)
            self.reported.add(group_id)
            self.emit("reporter", "report_sent", f"Report #{rid} delivered to Meta Integrity inbox", {"report_id": rid}, "platform")
        self.phase = prev_phase

    def handoff(self) -> None:
        """Copy observed posts into the Crime Sentinel review queue so humans can confirm or correct them."""
        self.phase = "handoff"
        records, topics = [], []
        for gid, o in self.observed.items():
            topics.append({"id": f"sbx_{gid}", "label": f"Sandbox: {o['group']['name']}",
                           "description": f"Community observed in mission {self.id}", "is_synthetic": True})
            for p in o["posts"]:
                records.append({
                    "id": f"{self.id}_{p['id']}", "source_type": "synthetic", "source_name": f"Sandbox mission {self.id}",
                    "published_at": p["created_at"], "text": p["text"], "language": "en", "hashtags": [],
                    "public_topic_ids": [f"sbx_{gid}"], "author_reference": p["author"]["id"],
                    "interaction_reference_ids": [], "is_synthetic": True,
                })
        load_topics(self.conn, topics)
        rep = ingest_records(self.conn, records, ContextualRuleClassifier(), actor=f"mission:{self.id}")
        self.emit("system", "handoff", f"{rep.accepted} observed posts added to the human review queue",
                  {"accepted": rep.accepted, "rejected": len(rep.rejected)})

    # ---- helpers ----------------------------------------------------------------
    def _check_all(self, answers: list[str], context: str) -> Verdict:
        worst = Verdict("allow")
        for a in answers:
            v = self.governor.check_message(a, context)
            v.reasons = [f"\"{a}\": {r}" for r in v.reasons] if v.reasons else v.reasons
            if not v.allowed and (worst.allowed or v.decision == "block"):
                worst = v
            elif v.allowed and worst.allowed:
                worst.engine = v.engine
        return worst

    @staticmethod
    def _verdict_title(v: Verdict) -> str:
        if v.allowed:
            return "Safety Governor: ALLOWED"
        return f"Safety Governor: {v.decision.upper()} ({', '.join(dict.fromkeys(v.violations)) or 'needs review'})"

    def summary(self) -> dict:
        return {
            "communities_observed": len(self.observed),
            "assessments": {o["group"]["name"]: o["assessment"]["tier"] for o in self.observed.values()},
            "reports_sent": len(self.reported),
            "muse_usage": self.ledger.as_dict(),
        }


# ---- public API used by routes ------------------------------------------------------
def start_mission(brief: str, auto_approve: str = "messages", pace: float = 0.8, force_offline: bool = False,
                  reset_sandbox: bool = True, background: bool = True) -> str:
    conn = database.connect()
    init(conn)
    if reset_sandbox:
        store.reset(conn)
    mid = "m_" + secrets.token_hex(3)
    conn.execute("INSERT INTO missions (id, created_at, status, mode, brief, auto_approve, pace) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (mid, store.utcnow().isoformat(), "starting", "offline" if force_offline or not MuseClient().enabled else "muse",
                  brief, auto_approve, pace))
    conn.commit()
    conn.close()
    runner = MissionRunner(mid, brief, auto_approve, pace, force_offline)
    _running[mid] = runner
    if background:
        threading.Thread(target=runner.run, daemon=True, name=f"mission-{mid}").start()
    else:
        runner.run()
    return mid


def stop_mission(mid: str) -> bool:
    r = _running.get(mid)
    if r:
        r.stop_flag.set()
    return bool(r)


def get_mission(conn: sqlite3.Connection, mid: str, after: int = 0) -> dict[str, Any] | None:
    init(conn)
    m = conn.execute("SELECT * FROM missions WHERE id = ?", (mid,)).fetchone()
    if not m:
        return None
    events = [
        {"id": e["id"], "ts": e["ts"], "phase": e["phase"], "actor": e["actor"], "kind": e["kind"], "title": e["title"],
         "detail": json.loads(e["detail"]), "engine": e["engine"]}
        for e in conn.execute("SELECT * FROM mission_events WHERE mission_id = ? AND id > ? ORDER BY id", (mid, after))
    ]
    approvals = [
        {"id": a["id"], "created_at": a["created_at"], "kind": a["kind"], "title": a["title"],
         "payload": json.loads(a["payload"]), "status": a["status"], "decided_by": a["decided_by"]}
        for a in conn.execute("SELECT * FROM mission_approvals WHERE mission_id = ? ORDER BY id", (mid,))
    ]
    return {"id": m["id"], "created_at": m["created_at"], "status": m["status"], "mode": m["mode"], "brief": m["brief"],
            "auto_approve": m["auto_approve"], "summary": json.loads(m["summary"]), "usage": json.loads(m["usage"]),
            "events": events, "approvals": approvals}


def list_missions(conn: sqlite3.Connection) -> list[dict]:
    init(conn)
    return [{"id": m["id"], "created_at": m["created_at"], "status": m["status"], "mode": m["mode"]}
            for m in conn.execute("SELECT id, created_at, status, mode FROM missions ORDER BY created_at DESC LIMIT 20")]


def decide_approval(conn: sqlite3.Connection, approval_id: int, approve: bool, reviewer: str, note: str | None,
                    edited_text: str | None = None) -> bool:
    init(conn)
    row = conn.execute("SELECT * FROM mission_approvals WHERE id = ?", (approval_id,)).fetchone()
    if not row or row["status"] != "pending":
        return False
    payload = json.loads(row["payload"])
    if edited_text is not None and row["kind"] == "message":
        from app.agent.governor import rule_check
        if not rule_check(edited_text).allowed:
            raise ValueError("edited message fails the Safety Governor rules")
        payload["text"] = edited_text
    conn.execute("UPDATE mission_approvals SET status = ?, decided_at = ?, decided_by = ?, note = ?, payload = ? WHERE id = ?",
                 ("approved" if approve else "rejected", store.utcnow().isoformat(), reviewer, note, json.dumps(payload), approval_id))
    repo.write_audit(conn, reviewer, f"mission_approval_{'approve' if approve else 'reject'}", None,
                     {"approval_id": approval_id, "kind": row["kind"], "mission_id": row["mission_id"], "note": note})
    conn.commit()
    return True
