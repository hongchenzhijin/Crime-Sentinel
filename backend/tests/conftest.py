from __future__ import annotations

import os
import sys
from pathlib import Path

# Tests never call the live Meta Model API, even when backend/.env has a key.
os.environ["CRIME_SENTINEL_CLASSIFIER"] = "rules"
os.environ["CRIME_SENTINEL_EMBEDDINGS"] = "hash"

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import routes  # noqa: E402
from app.db import database  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ingestion import ingest_records, load_topics  # noqa: E402

TOPICS = [
    {"id": "topic_a", "label": "Case A coverage", "description": "test", "is_synthetic": True},
    {"id": "topic_b", "label": "Fan culture", "description": "test", "is_synthetic": True},
]


def make_post(i: int, text: str, day: int = 1, **overrides) -> dict:
    base = {
        "id": f"post_{i:04d}",
        "source_type": "synthetic",
        "source_name": "Test Synthetic Dataset",
        "published_at": f"2026-09-{day:02d}T12:00:00Z",
        "text": text,
        "language": "en",
        "hashtags": ["#tcc"],
        "public_topic_ids": ["topic_a"],
        "author_reference": f"account_{i % 3}",
        "interaction_reference_ids": [],
        "is_synthetic": True,
    }
    base.update(overrides)
    return base


SAMPLE_POSTS = [
    make_post(1, "Police said the Case A attacker acted alone, according to officials.", 1),
    make_post(2, "Researchers published a study on fandoms around the Case A attack.", 2),
    make_post(3, "He is not a hero. Remember the victims.", 3, public_topic_ids=["topic_a", "topic_b"]),
    make_post(4, "The Case A attacker is a legend, deserves respect", 4, public_topic_ids=["topic_b"]),
    make_post(5, "Who's next? Someone should finish what he started.", 5, public_topic_ids=["topic_b"]),
    make_post(6, "I'm going to do what he did at my school.", 6),
    make_post(7, "the attack changed everything", 7, interaction_reference_ids=["post_0006", "user_123"]),
    make_post(8, "Watched the documentary last night, anyone know about the timeline?", 8),
]


@pytest.fixture()
def conn(tmp_path):
    c = database.connect(tmp_path / "test.db")
    load_topics(c, TOPICS)
    ingest_records(c, SAMPLE_POSTS)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path, conn):
    db_file = tmp_path / "test.db"

    def override():
        c = database.connect(db_file)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[routes.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
