"""Exportable research report: aggregate statistics plus reviewed, redacted examples."""

from __future__ import annotations

import sqlite3

from app import config
from app.db import repository as repo
from app.schemas.models import DatasetInfo, HARMFUL_CATEGORIES
from app.services import evaluation, trends

EXCERPT_CHARS = 90


def dataset_info(conn: sqlite3.Connection) -> DatasetInfo:
    row = conn.execute(
        "SELECT COUNT(*) AS n, SUM(is_synthetic) AS syn, MIN(published_at) AS start, MAX(published_at) AS end, "
        "MAX(ingested_at) AS ingested FROM posts"
    ).fetchone()
    names = [r[0] for r in conn.execute("SELECT DISTINCT source_name FROM posts ORDER BY source_name")]
    n, syn = row["n"] or 0, row["syn"] or 0
    return DatasetInfo(
        source_names=names,
        is_synthetic=n > 0 and syn == n,
        synthetic_count=syn,
        total_posts=n,
        period_start=row["start"],
        period_end=row["end"],
        ingested_at=row["ingested"],
        retention_days=config.RETENTION_DAYS,
    )


def redacted_excerpt(text: str, harmful: bool) -> str:
    if harmful:
        return "[content withheld from export - harmful category; view in the review tool]"
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " ..."


def build_report(conn: sqlite3.Connection, actor: str = "demo_reviewer") -> dict:
    items = repo.all_posts(conn)
    topics = repo.get_topics(conn)
    summary = trends.dashboard_summary(items, topics)
    trend = trends.compute_trends(items, topics)
    reviewed = [i for i in items if i.classification.review_status != "pending"]
    eval_result = evaluation.run_evaluation()

    report = {
        "title": f"{config.APP_NAME} - aggregate research report",
        "generated_at": repo.utcnow().isoformat(),
        "dataset": dataset_info(conn).model_dump(mode="json"),
        "synthetic_notice": "All records and trends in this report come from a SYNTHETIC demonstration dataset."
        if all(i.post.is_synthetic for i in items) else "Contains non-synthetic permitted research data.",
        "summary": summary,
        "emerging_topics": trend["emerging_topics"],
        "evaluation": {
            "test_set_size": eval_result["dataset"]["size"],
            "contextual_macro_f1": eval_result["contextual"]["macro_f1"],
            "contextual_false_positive_rate": eval_result["contextual"]["harm_binary"]["false_positive_rate"],
            "baseline_false_positive_rate": eval_result["baseline"]["harm_binary"]["false_positive_rate"],
        },
        "reviewed_examples": [
            {
                "post_id": i.post.id,
                "published_at": i.post.published_at.isoformat(),
                "model_category": i.classification.category.value,
                "reviewer_category": i.classification.reviewer_category.value if i.classification.reviewer_category else None,
                "review_status": i.classification.review_status,
                "excerpt": redacted_excerpt(
                    i.post.text,
                    (i.classification.reviewer_category or i.classification.category) in HARMFUL_CATEGORIES,
                ),
            }
            for i in reviewed[:50]
        ],
        "caveats": [
            trends.TREND_CAVEAT,
            summary["confidence_note"],
            "No individual is scored, identified, or reported by this system. Findings require human judgement.",
        ],
    }
    repo.write_audit(conn, actor, "export_report", None, {"reviewed_examples": len(report["reviewed_examples"])})
    conn.commit()
    return report
