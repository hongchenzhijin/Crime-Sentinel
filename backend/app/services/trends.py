"""Aggregate trend and dashboard calculations, computed from stored data.

All metrics describe content volume. A rise in discussion is not evidence of
increased real-world danger, and nothing here scores individuals.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Literal

from app import config
from app.schemas.models import HARMFUL_CATEGORIES, Category, PostWithClassification, Topic

TREND_CAVEAT = (
    "Trends show changes in the volume of posts in this dataset only. An increase in discussion is not "
    "evidence of increased real-world danger and does not establish causation."
)
EMERGING_WINDOW_DAYS = 14
EMERGING_MIN_RECENT = 10
EMERGING_MIN_RATIO = 2.0


def effective(item: PostWithClassification) -> Category:
    return item.classification.reviewer_category or item.classification.category


def _bucket_start(ts: datetime, granularity: Literal["day", "week"]) -> str:
    d = ts.date()
    if granularity == "week":
        d = d - timedelta(days=d.weekday())
    return d.isoformat()


def compute_trends(
    items: list[PostWithClassification],
    topics: dict[str, Topic],
    granularity: Literal["day", "week"] = "week",
    min_sample: int = config.MIN_TREND_SAMPLE,
) -> dict:
    buckets: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "categories": Counter(), "topics": Counter(), "authors": set(),
    })
    for item in items:
        b = buckets[_bucket_start(item.post.published_at, granularity)]
        b["total"] += 1
        b["categories"][effective(item).value] += 1
        for tid in item.post.public_topic_ids:
            b["topics"][tid] += 1
        if item.post.author_reference:
            b["authors"].add(item.post.author_reference)

    series = []
    for start in sorted(buckets):
        b = buckets[start]
        sufficient = b["total"] >= min_sample
        series.append({
            "bucket_start": start,
            "total_posts": b["total"],
            "unique_author_pseudonyms": len(b["authors"]) if b["authors"] else None,
            "sufficient_sample": sufficient,
            # Below the threshold, breakdowns are withheld so small numbers are not over-read.
            "categories": dict(b["categories"]) if sufficient else {},
            "topics": dict(b["topics"]) if sufficient else {},
        })

    return {
        "granularity": granularity,
        "min_sample": min_sample,
        "series": series,
        "topics": [t.model_dump() for t in topics.values()],
        "emerging_topics": emerging_topics(items, topics),
        "caveat": TREND_CAVEAT,
        "is_synthetic": bool(items) and all(i.post.is_synthetic for i in items),
    }


def emerging_topics(items: list[PostWithClassification], topics: dict[str, Topic]) -> dict:
    """Compare the last window of the dataset with the window before it."""
    if not items:
        return {"window_days": EMERGING_WINDOW_DAYS, "topics": [], "reference_end": None}
    end = max(i.post.published_at for i in items)
    recent_start = end - timedelta(days=EMERGING_WINDOW_DAYS)
    prev_start = recent_start - timedelta(days=EMERGING_WINDOW_DAYS)
    recent, previous = Counter(), Counter()
    for i in items:
        ts = i.post.published_at
        for tid in i.post.public_topic_ids:
            if ts > recent_start:
                recent[tid] += 1
            elif ts > prev_start:
                previous[tid] += 1
    rows = []
    for tid in sorted(set(recent) | set(previous)):
        r, p = recent[tid], previous[tid]
        ratio = r / max(p, 1)
        rows.append({
            "topic_id": tid,
            "label": topics[tid].label if tid in topics else tid,
            "recent_count": r,
            "previous_count": p,
            "ratio": round(ratio, 2),
            "meets_sample_threshold": r >= EMERGING_MIN_RECENT,
            "emerging": r >= EMERGING_MIN_RECENT and ratio >= EMERGING_MIN_RATIO,
        })
    rows.sort(key=lambda x: (x["emerging"], x["ratio"]), reverse=True)
    return {
        "window_days": EMERGING_WINDOW_DAYS,
        "min_recent_count": EMERGING_MIN_RECENT,
        "min_ratio": EMERGING_MIN_RATIO,
        "reference_end": end.isoformat(),
        "topics": rows,
    }


def dashboard_summary(items: list[PostWithClassification], topics: dict[str, Topic]) -> dict:
    total = len(items)
    by_category = Counter(effective(i).value for i in items)
    by_model_category = Counter(i.classification.category.value for i in items)
    by_status = Counter(i.classification.review_status for i in items)
    by_priority = Counter(i.classification.review_priority for i in items if i.classification.review_status == "pending")
    pending = by_status.get("pending", 0)

    histogram = [0] * 10
    for i in items:
        histogram[min(int(i.classification.confidence * 10), 9)] += 1

    urgent_threat_pending = sum(
        1 for i in items
        if i.classification.review_status == "pending"
        and (i.classification.category == Category.EXPLICIT_THREAT_OR_INTENT or i.classification.review_priority == "urgent")
    )
    topic_counts = Counter(t for i in items for t in i.post.public_topic_ids)

    return {
        "total_posts": total,
        "by_category": {c.value: by_category.get(c.value, 0) for c in Category},
        "by_model_category": {c.value: by_model_category.get(c.value, 0) for c in Category},
        "by_review_status": dict(by_status),
        "pending_by_priority": {p: by_priority.get(p, 0) for p in ("urgent", "high", "normal", "low")},
        "pending_review": pending,
        "pending_review_pct": round(100 * pending / total, 1) if total else 0.0,
        "urgent_threat_pending": urgent_threat_pending,
        "harmful_content_posts": sum(1 for i in items if effective(i) in HARMFUL_CATEGORIES),
        "repeated_glorification_signal_posts": sum(
            1 for i in items if "repeated_glorification_cues" in i.classification.signals
        ),
        "confidence_histogram": [
            {"bucket": f"{b / 10:.1f}-{(b + 1) / 10:.1f}", "count": n} for b, n in enumerate(histogram)
        ],
        "top_topics": [
            {"topic_id": t, "label": topics[t].label if t in topics else t, "count": n}
            for t, n in topic_counts.most_common(8)
        ],
        "confidence_note": "Confidence is the classifier's confidence in a content category. "
                           "It is not a probability that any person is dangerous.",
    }
