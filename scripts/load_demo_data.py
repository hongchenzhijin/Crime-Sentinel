"""Load the synthetic demo dataset into the local SQLite database (one command).

Usage (from the repository root):
    python scripts/load_demo_data.py               # regenerate + reset + load + classify
    python scripts/load_demo_data.py --no-generate # load the existing JSON files
    python scripts/load_demo_data.py --purge-expired  # only apply the retention policy
    python scripts/load_demo_data.py --delete-all     # delete all stored data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app import config  # noqa: E402
from app.db import database  # noqa: E402
from app.services.classification import get_classifier  # noqa: E402
from app.services import graphrag  # noqa: E402
from app.services.ingestion import ingest_file, purge_expired  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-generate", action="store_true", help="do not regenerate the synthetic JSON first")
    parser.add_argument("--purge-expired", action="store_true", help="delete records older than the retention period")
    parser.add_argument("--delete-all", action="store_true", help="delete all stored data and exit")
    args = parser.parse_args()

    conn = database.connect()
    if args.delete_all:
        database.reset_db(conn)
        print(f"Deleted all data in {config.DB_PATH}")
        return
    if args.purge_expired:
        print(f"Purged {purge_expired(conn)} expired posts (retention {config.RETENTION_DAYS} days)")
        return

    if not args.no_generate:
        import generate_demo_data

        generate_demo_data.write()

    database.reset_db(conn)
    classifier = get_classifier()
    report = ingest_file(conn, config.DEMO_POSTS_PATH, config.DEMO_TOPICS_PATH, classifier)
    print(f"Loaded {report.accepted} posts into {config.DB_PATH} using {classifier.name}@{classifier.version}")
    muse = getattr(classifier, "muse", None)
    if muse:
        usage = muse.ledger.as_dict()
        fallbacks = conn.execute("SELECT COUNT(*) FROM classifications WHERE signals LIKE '%muse_fallback%'").fetchone()[0]
        print(f"Meta Muse: {usage['calls']} calls, {usage['input_tokens'] + usage['output_tokens']} tokens, "
              f"~${usage['cost_usd']:.4f}; {fallbacks} posts fell back to the rule classifier")
    if report.rejected:
        print(f"Rejected {len(report.rejected)} invalid records:")
        for r in report.rejected[:10]:
            print("  ", r)
    rows = conn.execute("SELECT category, COUNT(*) FROM classifications GROUP BY category ORDER BY 2 DESC").fetchall()
    for category, n in rows:
        print(f"  {category:<32} {n}")
    images = conn.execute("SELECT COUNT(*), SUM(hash_match IS NOT NULL) FROM media").fetchone()
    model = conn.execute("SELECT model FROM embeddings LIMIT 1").fetchone()
    print(f"Images: {images[0]} hashed with PDQ, {images[1] or 0} match the hash list. "
          f"Embeddings: {model[0] if model else 'none'}")
    built = graphrag.build_communities(conn)
    print(f"GraphRAG: {built['communities']} communities covering {built['clustered_posts']} posts "
          f"({built['summaries']} summaries, ~${built['usage']['cost_usd']:.4f})")
    print("All records are SYNTHETIC.")


if __name__ == "__main__":
    main()
