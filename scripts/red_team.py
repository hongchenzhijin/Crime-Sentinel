"""AI red-team stress test: Muse writes adversarial posts per evasion tactic; every classifier is scored on them.

Usage:
    python scripts/red_team.py               # generate the set if missing (needs Muse), then evaluate
    python scripts/red_team.py --regenerate  # write a fresh set (~8 Muse calls), then evaluate
    python scripts/red_team.py --per-tactic 8

Writes data/synthetic/red_team_set.json (UNVERIFIED machine-generated items) and red_team_results.json, which the
Evaluation tab shows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import redteam  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regenerate", action="store_true", help="generate a new adversarial set with Muse")
    parser.add_argument("--per-tactic", type=int, default=6)
    args = parser.parse_args()
    r = redteam.run(regenerate=args.regenerate, per_tactic=args.per_tactic)
    print(f"Red-team set: {r['size']} items from {r['set']['generator']} (verified by a human: {r['set']['verified']})\n")
    names = list(r["classifiers"])
    print(f"{'tactic':<30}" + "".join(f"{n:>22}" for n in names))
    for tactic in r["tactics"]:
        row = []
        for n in names:
            c = r["classifiers"][n]["by_tactic"].get(tactic, {})
            total = sum(c.values()) or 1
            bad = c.get("evaded", 0) + c.get("false_alarm", 0)
            row.append(f"{bad}/{total} failed")
        print(f"{tactic:<30}" + "".join(f"{x:>22}" for x in row))
    print()
    for n in names:
        c = r["classifiers"][n]
        print(f"{n:<12} {c['model']:<42} evasion rate {c['evasion_rate']:.0%}   false-alarm rate {c['false_alarm_rate']:.0%}")


if __name__ == "__main__":
    main()
