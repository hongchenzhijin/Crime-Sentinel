"""Human review workflow. Reviewer decisions are stored alongside (never over)
the original model output so they can be used for evaluation. They are not
used to silently retrain anything."""

from __future__ import annotations

import sqlite3

from app.db import repository as repo
from app.schemas.models import Category, PostWithClassification, ReviewAction, ReviewRequest

_STATUS = {
    ReviewAction.CONFIRM: "confirmed",
    ReviewAction.CHANGE: "corrected",
    ReviewAction.MARK_UNCERTAIN: "marked_uncertain",
}


class PostNotFound(Exception):
    pass


def apply_review(conn: sqlite3.Connection, post_id: str, req: ReviewRequest) -> PostWithClassification:
    current = repo.get_post(conn, post_id)
    if current is None:
        raise PostNotFound(post_id)
    before = current.classification

    if req.action == ReviewAction.CONFIRM:
        reviewer_category = before.category
    elif req.action == ReviewAction.CHANGE:
        reviewer_category = req.reviewer_category
    else:
        reviewer_category = Category.UNCERTAIN_REQUIRES_REVIEW

    status = _STATUS[req.action]
    if req.action == ReviewAction.CHANGE and reviewer_category == before.category:
        status = "confirmed"

    conn.execute(
        """UPDATE classifications SET review_status = ?, reviewer_category = ?, reviewer_note = ?, reviewed_at = ?
           WHERE post_id = ?""",
        (status, reviewer_category.value, req.note, repo.utcnow().isoformat(), post_id),
    )
    repo.write_audit(conn, req.reviewer, f"review_{req.action.value}", post_id, {
        "model_category": before.category.value,
        "model_confidence": before.confidence,
        "model": f"{before.model_name}@{before.model_version}",
        "previous_review_status": before.review_status,
        "previous_reviewer_category": before.reviewer_category.value if before.reviewer_category else None,
        "new_review_status": status,
        "reviewer_category": reviewer_category.value,
        "note": req.note,
    })
    conn.commit()
    updated = repo.get_post(conn, post_id)
    assert updated is not None
    return updated
