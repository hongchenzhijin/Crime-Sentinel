"""Learning loop: reviewer decisions become few-shot examples for the Muse classifier.

Nothing is retrained. Confirmed and corrected reviews are retrieved by similarity and shown to Muse as examples,
so a correction applies to similar posts on the next classification run. Reclassifying replaces only the model
output: reviewer decisions are never touched, and the before/after change is recorded in the audit log.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from app.db import repository as repo
from app.services.classification import Classifier, get_classifier


def reviewer_examples(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Human-reviewed posts as few-shot examples, corrections first."""
    rows = conn.execute(
        """SELECT p.id, p.text, c.category, c.reviewer_category, c.reviewer_note, c.review_status
           FROM posts p JOIN classifications c ON c.post_id = p.id
           WHERE c.review_status IN ('confirmed', 'corrected') AND c.reviewer_category IS NOT NULL
           ORDER BY c.review_status = 'corrected' DESC, c.reviewed_at DESC LIMIT ?""", (limit,)).fetchall()
    return [{"post_id": r["id"], "text": r["text"], "label": r["reviewer_category"], "model_label": r["category"],
             "note": r["reviewer_note"] or "", "corrected": r["review_status"] == "corrected"} for r in rows]


def status(conn: sqlite3.Connection) -> dict:
    ex = reviewer_examples(conn)
    last = conn.execute("SELECT timestamp, details FROM audit_log WHERE action = 'reclassify_with_feedback' "
                        "ORDER BY id DESC LIMIT 1").fetchone()
    return {"examples": len(ex), "corrections": sum(e["corrected"] for e in ex),
            "last_run": {"timestamp": last["timestamp"], "details": json.loads(last["details"])} if last else None}


def reclassify(conn: sqlite3.Connection, actor: str = "demo_reviewer", classifier: Classifier | None = None) -> dict:
    """Re-run the classifier over every post with reviewer examples, keeping all review decisions."""
    from app.services.ingestion import classify_posts

    examples = reviewer_examples(conn)
    classifier = classifier or get_classifier(examples)
    items = repo.all_posts(conn)
    before = {i.post.id: i.classification for i in items}
    now = repo.utcnow()
    results = classify_posts(conn, [i.post for i in items], classifier)
    transitions: Counter = Counter()
    for item, (result, priority) in zip(items, results):
        old = before[item.post.id].category.value
        if result.category.value != old:
            transitions[(old, result.category.value)] += 1
        repo.update_model_output(conn, item.post.id, result, priority, now)

    reviewed = [i for i in items if i.classification.reviewer_category]
    # Agreement on reviewed posts. Each post's own decision is excluded from its examples (by identical text),
    # but templated near-duplicates may still be present, so treat this as optimistic.
    after = {i.post.id: r.category for i, (r, _) in zip(items, results)}
    agree_before = sum(before[i.post.id].category == i.classification.reviewer_category for i in reviewed)
    agree_after = sum(after[i.post.id] == i.classification.reviewer_category for i in reviewed)
    summary = {
        "model": f"{classifier.name}@{classifier.version}",
        "reviewer_examples": len(examples),
        "posts": len(items),
        "changed": sum(transitions.values()),
        "transitions": [{"from": a, "to": b, "count": n} for (a, b), n in transitions.most_common()],
        "reviewed_posts": len(reviewed),
        "agreement_before": round(agree_before / len(reviewed), 3) if reviewed else None,
        "agreement_after": round(agree_after / len(reviewed), 3) if reviewed else None,
        "note": "Reviewer decisions were kept unchanged; only model outputs were replaced. Agreement is measured on "
                "the reviewed posts themselves and is optimistic.",
    }
    usage = getattr(getattr(classifier, "muse", None), "ledger", None)
    if usage:
        summary["usage"] = usage.as_dict()
    repo.write_audit(conn, actor, "reclassify_with_feedback", None, summary)
    conn.commit()
    return summary
