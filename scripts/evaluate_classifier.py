"""Evaluate the Muse classifier (if configured), the contextual classifier and the keyword baseline on the labelled test set.

Usage: python scripts/evaluate_classifier.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.evaluation import LABELS, run_evaluation  # noqa: E402

SHORT = {label: "".join(w[0] for w in label.split("_"))[:4] for label in LABELS}


def print_model(name: str, r: dict) -> None:
    print(f"\n=== {name}: {r['model']} ===")
    print(f"n={r['n']}  macro-F1={r['macro_f1']:.3f}  accuracy={r['accuracy']:.3f} (do not rely on accuracy alone)")
    hb = r["harm_binary"]
    print(f"Harmful-content view: false-positive rate {hb['false_positive_rate']:.1%} "
          f"({hb['false_positives']}/{hb['non_harmful_items']} non-harmful items flagged), "
          f"harmful recall {hb['harmful_recall']:.1%}, missed {hb['missed_harmful']}, "
          f"routed to review {hb['harmful_routed_to_review']}")
    print(f"\n{'category':<32}{'P':>7}{'R':>7}{'F1':>7}{'support':>9}")
    for label, m in r["per_class"].items():
        print(f"{label:<32}{m['precision']:>7.2f}{m['recall']:>7.2f}{m['f1']:>7.2f}{m['support']:>9}")
    print("\nConfusion matrix (rows = gold, columns = predicted):")
    print(" " * 6 + "".join(f"{SHORT[l]:>6}" for l in LABELS))
    for label, row in zip(LABELS, r["confusion_matrix"]["matrix"]):
        print(f"{SHORT[label]:<6}" + "".join(f"{v:>6}" for v in row))
    for key, title in (("false_positive_examples", "False positives"), ("false_negative_examples", "False negatives")):
        print(f"\n{title} ({len(r[key])}):")
        for ex in r[key]:
            print(f"  [{ex['id']}] gold={ex['gold']} pred={ex['predicted']}: {ex['text'][:80]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument("--fresh", action="store_true", help="ignore the cached Muse evaluation and re-run it")
    args = parser.parse_args()
    result = run_evaluation(fresh=args.fresh)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    ds = result["dataset"]
    print(f"Evaluation set: {ds['size']} SYNTHETIC hand-labelled items, languages {ds['languages']}")
    if result["muse"]:
        print_model("Meta Muse classifier (rules as safety net)", result["muse"])
        u = result["muse"]["usage"]
        print(f"Muse usage: {u['calls']} calls, {u['input_tokens'] + u['output_tokens']} tokens, ~${u['cost_usd']:.4f}")
    print_model("Contextual classifier", result["contextual"])
    mm = result["multimodal"]
    if mm:
        print(f"\n=== Multimodal set ({mm['size']} items where the image changes the meaning) ===")
        for key, e in mm["engines"].items():
            print(f"{e['label']:<34} accuracy {e['accuracy']:.0%}  harmful caught {e['harmful_caught']}/{e['harmful_items']}"
                  f" (+{e['harmful_routed_to_review']} to review)  benign flagged {e['benign_flagged_harmful']}/{e['benign_items']}")
        for i in mm["items"]:
            preds = "  ".join(f"{k}={v[:12]}" for k, v in i["predictions"].items())
            print(f"  [{i['id']}] gold={i['gold'][:12]:<12} pdq={'Y' if i['hash_match'] else '-'}  {preds}")
    print_model("Keyword baseline", result["baseline"])
    print("\nLimitations:")
    for line in result["limitations"]:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
