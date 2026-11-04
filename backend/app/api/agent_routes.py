"""Routes for the sandbox platform (the simulated Facebook UI) and Sentinel missions."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent import mission as missions
from app.agent import muse
from app.api.routes import DB
from app.sandbox import platform as sb
from app.sandbox import store

router = APIRouter(prefix="/api")

DEFAULT_BRIEF = (
    "Tip-off from the platform's integrity team: ahead of the anniversary of the Ridgeview attack (fictional), "
    "fans of the attacker are reported to gather in closed groups. Find out which communities glorify the "
    "attacker or plan anything around the anniversary, and report them with evidence. Do not enter support spaces."
)


def _ensure(conn) -> None:
    missions.init(conn)
    if not store.is_seeded(conn):
        store.reset(conn)


# ---- sandbox platform -------------------------------------------------------------
@router.get("/sandbox/users")
def sandbox_users(conn: DB) -> list[dict]:
    _ensure(conn)
    return list(sb.users(conn).values())


@router.get("/sandbox/groups")
def sandbox_groups(conn: DB, viewer: str = Query("u_viewer", max_length=32), q: str = Query("", max_length=100)) -> list[dict]:
    _ensure(conn)
    found = {g["id"]: g for g in sb.search_groups(conn, q, viewer)}
    for g in sb.my_groups(conn, viewer):
        found.setdefault(g["id"], g)
    return list(found.values())


@router.get("/sandbox/groups/{group_id}")
def sandbox_group(group_id: str, conn: DB, viewer: str = Query("u_viewer", max_length=32)) -> dict:
    _ensure(conn)
    try:
        return sb.group_view(conn, group_id, viewer)
    except sb.PlatformError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/sandbox/groups/{group_id}/feed")
def sandbox_feed(group_id: str, conn: DB, viewer: str = Query("u_viewer", max_length=32)) -> list[dict]:
    _ensure(conn)
    try:
        return sb.feed(conn, group_id, viewer, trigger_npc=False)
    except sb.PlatformError as exc:
        raise HTTPException(403, str(exc)) from None


class JoinRequest(BaseModel):
    viewer: str = Field(max_length=32)
    answers: list[str] = Field(default_factory=list, max_length=10)


@router.post("/sandbox/groups/{group_id}/join")
def sandbox_join(group_id: str, body: JoinRequest, conn: DB) -> dict:
    """Lets a human demo user try the admission flow. The persona can only act through a governed mission."""
    _ensure(conn)
    if body.viewer == "u_persona":
        raise HTTPException(403, "the Sentinel persona acts only through a governed mission")
    try:
        return sb.request_join(conn, group_id, body.viewer, body.answers)
    except sb.PlatformError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/sandbox/messages")
def sandbox_messages(conn: DB, viewer: str = Query("u_persona", max_length=32)) -> list[dict]:
    _ensure(conn)
    return sb.threads(conn, viewer)


@router.get("/sandbox/reports")
def sandbox_reports(conn: DB) -> list[dict]:
    _ensure(conn)
    return sb.reports(conn)


@router.post("/sandbox/reset")
def sandbox_reset(conn: DB) -> dict:
    missions.init(conn)
    store.reset(conn)
    return {"status": "reset"}


# ---- missions -----------------------------------------------------------------------
class MissionRequest(BaseModel):
    brief: str = Field(DEFAULT_BRIEF, min_length=10, max_length=2000)
    auto_approve: Literal["none", "messages", "all"] = "messages"
    pace: float = Field(0.8, ge=0, le=5)
    offline: bool = False


class ApprovalDecision(BaseModel):
    approve: bool
    reviewer: str = Field("demo_reviewer", min_length=1, max_length=64)
    note: str | None = Field(None, max_length=500)
    edited_text: str | None = Field(None, max_length=400)


@router.get("/muse/status")
def muse_status() -> dict:
    return {"enabled": bool(muse.API_KEY), "base_url": muse.BASE_URL, "fast_model": muse.FAST_MODEL,
            "deep_model": muse.DEEP_MODEL, "image_model": muse.IMAGE_MODEL, "default_brief": DEFAULT_BRIEF}


@router.post("/missions")
def create_mission(req: MissionRequest) -> dict:
    mid = missions.start_mission(req.brief, req.auto_approve, req.pace, req.offline)
    return {"id": mid}


@router.get("/missions")
def get_missions(conn: DB) -> list[dict]:
    return missions.list_missions(conn)


@router.get("/missions/{mission_id}")
def get_mission(mission_id: str, conn: DB, after: int = Query(0, ge=0)) -> dict:
    m = missions.get_mission(conn, mission_id, after)
    if m is None:
        raise HTTPException(404, "mission not found")
    return m


@router.post("/missions/{mission_id}/stop")
def stop(mission_id: str) -> dict:
    return {"stopped": missions.stop_mission(mission_id)}


@router.post("/approvals/{approval_id}")
def decide(approval_id: int, body: ApprovalDecision, conn: DB) -> dict:
    try:
        ok = missions.decide_approval(conn, approval_id, body.approve, body.reviewer, body.note, body.edited_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if not ok:
        raise HTTPException(409, "approval not found or already decided")
    return {"status": "approved" if body.approve else "rejected"}
