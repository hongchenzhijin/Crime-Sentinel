from app.db import repository as repo
from app.services.ingestion import Pseudonymiser, ingest_records, redact_text

from .conftest import make_post


def test_redacts_contact_details_and_handles():
    text = "Email help@example.org or call +60 12-345 6789, ask @someone_here, see https://example.org/x"
    out = redact_text(text)
    assert "help@example.org" not in out
    assert "345 6789" not in out
    assert "@someone_here" not in out
    assert "https://" not in out
    assert "[email removed]" in out and "[handle removed]" in out


def test_pseudonyms_are_stable_within_a_run_but_not_across_runs():
    a, b = Pseudonymiser(), Pseudonymiser()
    assert a("account_1") == a("account_1")
    assert a("account_1") != a("account_2")
    assert a("account_1") != b("account_1")
    assert "account_1" not in a("account_1")
    assert a(None) is None


def test_stored_posts_have_no_raw_author_ids(conn):
    rows = conn.execute("SELECT author_reference FROM posts").fetchall()
    assert all(r[0].startswith("anon_") for r in rows)
    assert not any("account_" in r[0] for r in rows)


def test_invalid_records_are_rejected_with_reasons(conn):
    report = ingest_records(conn, [
        make_post(100, "ok post"),
        {"id": "bad", "text": "missing fields"},
        make_post(101, "flag mismatch", is_synthetic=False),
        make_post(102, ""),
    ])
    assert report.accepted == 1
    assert len(report.rejected) == 3
    assert all(r["errors"] for r in report.rejected)


def test_interaction_refs_keep_only_post_references(conn):
    post = repo.get_post(conn, "post_0007")
    assert post.post.interaction_reference_ids == ["post_0006"]


def test_every_post_is_classified_with_model_version(conn):
    n_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    rows = conn.execute("SELECT model_name, model_version, review_status FROM classifications").fetchall()
    assert len(rows) == n_posts
    assert all(r["model_name"] and r["model_version"] and r["review_status"] == "pending" for r in rows)


def test_ingestion_is_audited(conn):
    entries = repo.list_audit(conn)
    assert any(e.action == "ingest_dataset" for e in entries)
