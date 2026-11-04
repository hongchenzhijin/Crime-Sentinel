"""Classifier evaluation against a small, manually labelled test set.

Reports per-class precision/recall/F1, a confusion matrix, false-positive and
false-negative examples, and per-language results, for both the contextual
classifier and the naive keyword baseline.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from app import config
from app.schemas.models import HARMFUL_CATEGORIES, Category
from app.services.classification import (
    Classifier,
    ContextualRuleClassifier,
    KeywordBaselineClassifier,
    classify_all,
    get_muse_classifier,
)

LABELS = [c.value for c in Category]
UNCERTAIN = Category.UNCERTAIN_REQUIRES_REVIEW.value
HARMFUL = {c.value for c in HARMFUL_CATEGORIES}


def load_eval_set(path: Path = config.EVAL_SET_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def score(gold: list[str], pred: list[str]) -> dict:
    confusion = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p in zip(gold, pred):
        confusion[g][p] += 1
    support = Counter(gold)
    per_class = {}
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[g][label] for g in LABELS if g != label)
        fn = sum(confusion[label][p] for p in LABELS if p != label)
        per_class[label] = {**_prf(tp, fp, fn), "support": support.get(label, 0), "predicted": tp + fp}
    present = [label for label in LABELS if support.get(label)]
    macro_f1 = sum(per_class[l]["f1"] for l in present) / len(present) if present else 0.0

    # Binary view: harmful content vs not. UNCERTAIN predictions are counted as
    # "routed to human review", not as correct or incorrect decisions.
    non_harmful_gold = [(g, p) for g, p in zip(gold, pred) if g not in HARMFUL and g != UNCERTAIN]
    harmful_gold = [(g, p) for g, p in zip(gold, pred) if g in HARMFUL]
    fp_harm = sum(1 for _, p in non_harmful_gold if p in HARMFUL)
    fn_harm = sum(1 for _, p in harmful_gold if p not in HARMFUL and p != UNCERTAIN)
    return {
        "n": len(gold),
        "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / len(gold), 3) if gold else 0.0,
        "macro_f1": round(macro_f1, 3),
        "per_class": per_class,
        "confusion_matrix": {"labels": LABELS, "matrix": [[confusion[g][p] for p in LABELS] for g in LABELS]},
        "harm_binary": {
            "false_positive_rate": round(fp_harm / len(non_harmful_gold), 3) if non_harmful_gold else 0.0,
            "false_positives": fp_harm,
            "non_harmful_items": len(non_harmful_gold),
            "missed_harmful": fn_harm,
            "harmful_items": len(harmful_gold),
            "harmful_routed_to_review": sum(1 for _, p in harmful_gold if p == UNCERTAIN),
            "harmful_recall": round(sum(1 for _, p in harmful_gold if p in HARMFUL) / len(harmful_gold), 3)
            if harmful_gold else 0.0,
        },
    }


def evaluate_classifier(classifier: Classifier, items: list[dict]) -> dict:
    preds = [r.category.value for r in classify_all(classifier, [(i["text"], i.get("language", "en")) for i in items])]
    gold = [i["label"] for i in items]
    result = score(gold, preds)
    result["model"] = f"{classifier.name}@{classifier.version}"

    by_lang: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
    for i, p in zip(items, preds):
        g_list, p_list = by_lang[i.get("language", "en")]
        g_list.append(i["label"])
        p_list.append(p)
    result["by_language"] = {
        lang: {k: v for k, v in score(g, p).items() if k in ("n", "accuracy", "macro_f1", "harm_binary")}
        for lang, (g, p) in by_lang.items()
    }

    def example(i: dict, p: str) -> dict:
        return {"id": i["id"], "text": i["text"], "language": i.get("language", "en"), "gold": i["label"],
                "predicted": p, "note": i.get("note", "")}

    result["false_positive_examples"] = [
        example(i, p) for i, p in zip(items, preds) if i["label"] not in HARMFUL and i["label"] != UNCERTAIN and p in HARMFUL
    ]
    result["false_negative_examples"] = [
        example(i, p) for i, p in zip(items, preds) if i["label"] in HARMFUL and p not in HARMFUL and p != UNCERTAIN
    ]
    result["routed_to_review_examples"] = [
        example(i, p) for i, p in zip(items, preds) if p == UNCERTAIN and i["label"] != UNCERTAIN
    ]
    return result


def _cache_key(path: Path, muse: Classifier | None) -> str:
    """Changes whenever an eval file, the hash list, a classifier version or the Muse prompts change."""
    from app.services import classification

    h = hashlib.sha256()
    for f in (path, config.MULTIMODAL_EVAL_PATH, config.HASHLIST_PATH):
        h.update(f.read_bytes() if f.exists() else b"-")
    h.update(f"{ContextualRuleClassifier.version}|{muse.name}@{muse.version}".encode() if muse else b"rules-only")
    h.update((classification.MUSE_SYSTEM_PROMPT + classification.VISION_ADDENDUM).encode())
    return h.hexdigest()


@lru_cache(maxsize=1)
def run_evaluation(path: Path = config.EVAL_SET_PATH, fresh: bool = False) -> dict:
    """Evaluate every classifier. With Muse, the result is cached on disk (it takes ~1 minute and costs ~$0.10) and
    recomputed only when the eval sets, hash list, classifier versions or prompts change, or with fresh=True."""
    muse = get_muse_classifier()
    key = _cache_key(path, muse)
    if muse and not fresh and config.EVAL_CACHE_PATH.exists():
        cached = json.loads(config.EVAL_CACHE_PATH.read_text(encoding="utf-8"))
        if cached.get("cache_key") == key:
            return cached["result"]
    result = _compute_evaluation(path, muse)
    if muse:
        config.EVAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.EVAL_CACHE_PATH.write_text(json.dumps({"cache_key": key, "result": result}), encoding="utf-8")
    return result


def _compute_evaluation(path: Path, muse: Classifier | None) -> dict:
    items = load_eval_set(path)
    muse_result = None
    if muse:
        muse_result = evaluate_classifier(muse, items)
        muse_result["usage"] = muse.muse.ledger.as_dict()
    return {
        "dataset": {
            "path": str(path.relative_to(config.PROJECT_ROOT)) if path.is_relative_to(config.PROJECT_ROOT) else str(path),
            "size": len(items),
            "label_distribution": dict(Counter(i["label"] for i in items)),
            "languages": dict(Counter(i.get("language", "en") for i in items)),
            "is_synthetic": True,
        },
        "contextual": evaluate_classifier(ContextualRuleClassifier(), items),
        "baseline": evaluate_classifier(KeywordBaselineClassifier(), items),
        "muse": muse_result,
        "multimodal": run_multimodal(muse),
        "limitations": [
            "The test set is small, synthetic, and written by the same team that wrote the classifier cues, so "
            "results are likely optimistic and will not transfer directly to real-world data.",
            "Coded language, sarcasm, and new slang are under-represented; recall on real content will be lower.",
            "Bahasa Malaysia items are routed to human review because the classifier is not validated for that language.",
            "Accuracy is shown for completeness only; use per-class precision/recall because classes are imbalanced.",
        ],
    }


def run_multimodal(muse: Classifier | None, path: Path = config.MULTIMODAL_EVAL_PATH) -> dict | None:
    """Image-dependent items: rules + PDQ (offline) vs Muse reading only the text vs Muse with vision."""
    from app.services import media

    if not path.exists():
        return None
    items = load_eval_set(path)
    files = [[media.media_path(f) for f in i["media"]] for i in items]
    matches = [[m for m in (media.match_hashlist(media.pdq_hash(f)[0]) for f in fs if f.exists()) if m] for fs in files]

    def run(clf: Classifier, with_images: bool) -> list[str]:
        results = classify_all(clf, [(i["text"], i.get("language", "en"), fs if with_images else [])
                                     for i, fs in zip(items, files)])
        return [media.apply_hash_matches(r, m)[0].category.value for r, m in zip(results, matches)]

    engines = {"rules_pdq": ("Rules + PDQ hash list (offline)", run(ContextualRuleClassifier(), False))}
    if muse:
        engines["muse_text"] = ("Muse, text only + PDQ", run(muse, False))
        engines["muse_vision"] = ("Muse vision + PDQ", run(muse, True))
    gold = [i["label"] for i in items]
    summary = {}
    for key, (label, preds) in engines.items():
        harmful = [(g, p) for g, p in zip(gold, preds) if g in HARMFUL]
        benign = [(g, p) for g, p in zip(gold, preds) if g not in HARMFUL]
        summary[key] = {
            "label": label,
            "accuracy": round(sum(g == p for g, p in zip(gold, preds)) / len(items), 3),
            "harmful_caught": sum(p in HARMFUL for _, p in harmful),
            "harmful_routed_to_review": sum(p == UNCERTAIN for _, p in harmful),
            "harmful_items": len(harmful),
            "benign_flagged_harmful": sum(p in HARMFUL for _, p in benign),
            "benign_items": len(benign),
        }
    return {
        "size": len(items),
        "engines": summary,
        "items": [{"id": i["id"], "text": i["text"], "image": i["media"][0], "gold": i["label"], "note": i.get("note", ""),
                   "hash_match": bool(m), "predictions": {k: v[1][n] for k, v in engines.items()}}
                  for n, (i, m) in enumerate(zip(items, matches))],
        "note": "10 hand-labelled synthetic items built so that the image changes the meaning; far too small for "
                "accuracy claims. PDQ matches never make a post harmful on their own; they route it to review.",
    }


def reviewer_feedback(conn: sqlite3.Connection) -> dict:
    """Agreement between model output and human reviewer decisions (no retraining)."""
    rows = conn.execute(
        "SELECT category, reviewer_category FROM classifications WHERE review_status != 'pending' AND reviewer_category IS NOT NULL"
    ).fetchall()
    corrections = Counter((r["category"], r["reviewer_category"]) for r in rows if r["category"] != r["reviewer_category"])
    agree = sum(1 for r in rows if r["category"] == r["reviewer_category"])
    return {
        "reviewed": len(rows),
        "agreement_rate": round(agree / len(rows), 3) if rows else None,
        "corrections": [{"model_category": m, "reviewer_category": r, "count": n} for (m, r), n in corrections.most_common()],
        "note": "Reviewer decisions are stored for evaluation only; the classifier is not retrained automatically.",
    }
