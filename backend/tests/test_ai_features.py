"""PDQ hashing, vision, embeddings, GraphRAG, the learning loop and red-teaming. No network calls: Muse is faked."""

import json

import numpy as np
import pytest
from PIL import Image, ImageEnhance

from app import config
from app.agent.muse import MuseResult
from app.db import database
from app.schemas.models import Category, ClassificationResult, ReviewAction, ReviewRequest
from app.services import embeddings, graph, graphrag, learning, media, redteam
from app.services.classification import ContextualRuleClassifier, MuseClassifier
from app.services.ingestion import ingest_records, load_topics
from app.services.review import apply_review
from tests.conftest import SAMPLE_POSTS, TOPICS, make_post


class FakeMuse:
    """Records prompts and returns a fixed JSON reply (or one chosen by a function of the prompt)."""

    enabled = True

    def __init__(self, reply):
        self.reply, self.prompts = reply, []
        from app.agent.muse import UsageLedger
        self.ledger = UsageLedger()

    def chat(self, purpose, system, user, **kwargs):
        self.prompts.append((purpose, system, user))
        data = self.reply(user) if callable(self.reply) else self.reply
        return MuseResult(json.dumps(data), data, "muse-spark-1.3", 1, 10, 10, 0, 0.0)


def noise_image(path, seed, size=256):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    Image.fromarray(small).resize((size, size), Image.BICUBIC).save(path)
    return path


@pytest.fixture()
def media_env(tmp_path, monkeypatch):
    mdir = tmp_path / "media"
    mdir.mkdir()
    known = noise_image(mdir / "known.png", 1)
    ImageEnhance.Brightness(Image.open(known)).enhance(1.25).save(mdir / "reupload.png")
    noise_image(mdir / "other.png", 2)
    hl = tmp_path / "hashlist.json"
    pdq, quality = media.pdq_hash(known)
    hl.write_text(json.dumps({"entries": [{"id": "HL-T", "pdq": pdq, "quality": quality, "label": "known test image",
                                           "category": "GLORIFICATION_OR_PRAISE", "source": "test"}]}))
    monkeypatch.setattr(config, "MEDIA_DIR", mdir)
    monkeypatch.setattr(config, "HASHLIST_PATH", hl)
    return mdir


# ---- PDQ ------------------------------------------------------------------------------------------------------------

def test_pdq_matches_reupload_not_unrelated(media_env):
    known, _ = media.pdq_hash(media_env / "known.png")
    reupload, _ = media.pdq_hash(media_env / "reupload.png")
    other, _ = media.pdq_hash(media_env / "other.png")
    assert media.hamming(known, reupload) <= media.MATCH_THRESHOLD < media.hamming(known, other)
    assert media.match_hashlist(reupload)["entry_id"] == "HL-T"
    assert media.match_hashlist(other) is None


def test_media_path_rejects_traversal(media_env):
    with pytest.raises(ValueError):
        media.media_path("../hashlist.json")


def test_hash_match_never_makes_post_harmful_alone():
    neutral = ClassificationResult(category=Category.NEUTRAL_DISCUSSION, confidence=0.8, evidence_spans=[],
                                   explanation="x", signals=[], model_name="m", model_version="1")
    match = {"entry_id": "HL-T", "label": "known", "category": "GLORIFICATION_OR_PRAISE", "source": "t", "distance": 3}
    out, review = media.apply_hash_matches(neutral, [match])
    assert review and out.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert "pdq_hashlist_match:HL-T" in out.signals
    assert media.apply_hash_matches(neutral, []) == (neutral, False)


def test_ingestion_hashes_images_and_routes_matches(tmp_path, media_env):
    conn = database.connect(tmp_path / "m.db")
    load_topics(conn, TOPICS)
    ingest_records(conn, [make_post(1, "new edit, thoughts?", media=[{"file": "reupload.png", "alt_text": "edit"}]),
                          make_post(2, "Police said the Case A attacker acted alone.", 2)])
    row = conn.execute("SELECT c.category, c.review_priority, c.signals FROM classifications c WHERE post_id='post_0001'").fetchone()
    assert row["category"] == "UNCERTAIN_REQUIRES_REVIEW" and row["review_priority"] == "high"
    assert "pdq_hashlist_match:HL-T" in json.loads(row["signals"])
    m = media.post_media(conn, "post_0001")
    assert m[0]["hash_match"]["entry_id"] == "HL-T" and m[0]["url"] == "/api/media/reupload.png"


# ---- vision + OCR ---------------------------------------------------------------------------------------------------

def test_vision_evidence_supports_harm_without_text_quote(media_env):
    fake = FakeMuse({"category": "GLORIFICATION_OR_PRAISE", "confidence": 0.9, "evidence_quotes": [],
                     "image_observation": "A haloed hooded figure.", "image_text": "",
                     "visual_evidence": "halo and shrine around the attacker"})
    r = MuseClassifier(fake).classify("new edit, thoughts?", "en", [media_env / "other.png"])
    assert r.category == Category.GLORIFICATION_OR_PRAISE
    assert "visual_evidence_only" in r.signals and "muse_vision" in r.signals
    assert r.media_observations[0].observation == "A haloed hooded figure."
    assert isinstance(fake.prompts[0][2], list) and fake.prompts[0][2][1]["type"] == "image_url"


def test_ocr_text_goes_through_rules(media_env):
    fake = FakeMuse({"category": "NEUTRAL_DISCUSSION", "confidence": 0.9, "evidence_quotes": [],
                     "image_observation": "Poster with text.", "image_text": "I'm going to do what he did at my school",
                     "visual_evidence": ""})
    r = MuseClassifier(fake).classify("tick tock", "en", [media_env / "other.png"])
    assert r.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert "engines_disagree" in r.signals and any(s.startswith("ocr_cue:") for s in r.signals)


# ---- embeddings + graph ---------------------------------------------------------------------------------------------

def test_hashing_embeddings_rank_similar_text_first():
    e = embeddings.HashingEmbedder()
    v = e.embed(["the attacker is a legend honestly", "honestly the attacker is a legend", "library opening hours"])
    assert v[0] @ v[1] > v[0] @ v[2]


def test_semantic_search_and_graph_edges(conn):
    hits = embeddings.semantic_search(conn, "Police said the attacker acted alone", 3)
    assert hits and hits[0][0] == "post_0001"
    ids, matrix, model = embeddings.load_embeddings(conn)
    assert model == embeddings.HashingEmbedder.name and len(ids) == len(SAMPLE_POSTS)
    from app.db import repository as repo
    g = graph.build_graph(repo.all_posts(conn), repo.get_topics(conn), {"SIMILAR_CONTENT"},
                          vectors=dict(zip(ids, matrix)), vector_model=model, similarity_threshold=0.1)
    assert g.edges and all(e.method.startswith("semantic_embedding:") for e in g.edges)


def test_image_edges_link_reshared_images():
    edges = graph.image_edges(["a", "b", "c"], {"a": [("f" * 64, "x.png")], "b": [("f" * 63 + "e", "y.png")],
                                                 "c": [("0" * 64, "z.png")]})
    assert [(e.source, e.target, e.type) for e in edges] == [("a", "b", "SHARES_IMAGE")]


# ---- GraphRAG -------------------------------------------------------------------------------------------------------

def test_graphrag_offline_build_and_ask(conn, monkeypatch):
    monkeypatch.setattr(graphrag, "MIN_COMMUNITY_SIZE", 1)
    offline = FakeMuse({})
    offline.enabled = False
    summary = graphrag.build_communities(conn, muse=offline)
    assert summary["communities"] >= 1 and summary["summaries"] == "template"
    comms = graphrag.list_communities(conn)
    assert all(c["risk"]["final"] in graphrag.RISK_LEVELS and c["post_ids"] for c in comms)
    answer = graphrag.ask(conn, "what are people praising?", muse=offline)
    assert answer["engine"] == "retrieval-only" and answer["retrieved_posts"]


def test_graphrag_refuses_identity_questions(conn):
    r = graphrag.ask(conn, "What are the real names of the people posting?", muse=FakeMuse({}))
    assert r["refused"] and not r["retrieved_posts"]


def test_graphrag_drops_citations_muse_was_not_shown(conn, monkeypatch):
    monkeypatch.setattr(graphrag, "MIN_COMMUNITY_SIZE", 1)
    offline = FakeMuse({})
    offline.enabled = False
    graphrag.build_communities(conn, muse=offline)
    fake = FakeMuse({"answer": "Praise clusters in [c01] and [post_9999].", "cited_community_ids": ["c01", "c99"],
                     "cited_post_ids": ["post_9999"], "confidence": 0.6, "caveats": ""})
    r = graphrag.ask(conn, "where is praise concentrated?", muse=fake)
    assert r["cited_community_ids"] == ["c01"] and r["cited_post_ids"] == []
    assert r["unverified_citations"] == ["post_9999"]


# ---- learning loop --------------------------------------------------------------------------------------------------

def test_reclassify_uses_reviewer_examples_and_keeps_decisions(conn):
    apply_review(conn, "post_0007", ReviewRequest(action=ReviewAction.CHANGE,
                                                   reviewer_category=Category.NEUTRAL_DISCUSSION, note="just history"))
    examples = learning.reviewer_examples(conn)
    assert examples[0]["corrected"] and examples[0]["label"] == "NEUTRAL_DISCUSSION"
    fake = FakeMuse({"category": "NEWS_REPORTING", "confidence": 0.9, "evidence_quotes": ["Police said"]})
    clf = MuseClassifier(fake, examples=examples, embedder=embeddings.HashingEmbedder())
    summary = learning.reclassify(conn, classifier=clf)
    row = conn.execute("SELECT reviewer_category, review_status FROM classifications WHERE post_id='post_0007'").fetchone()
    assert (row["reviewer_category"], row["review_status"]) == ("NEUTRAL_DISCUSSION", "corrected")
    assert summary["reviewer_examples"] == 1 and summary["posts"] == len(SAMPLE_POSTS)
    shown = [u for _, _, u in fake.prompts if "Reviewer-verified examples" in u]
    assert shown and all('"the attack changed everything" ->' not in u.split("Post:")[1] for u in shown)
    # a post never sees its own reviewer decision as an example
    own = [u for _, _, u in fake.prompts if 'Post:\n"""the attack changed everything"""' in u]
    assert own and "Reviewer-verified examples" not in own[0]


# ---- red team -------------------------------------------------------------------------------------------------------

def test_red_team_outcomes_and_scoring():
    assert redteam.outcome("GLORIFICATION_OR_PRAISE", "NEUTRAL_DISCUSSION") == "evaded"
    assert redteam.outcome("GLORIFICATION_OR_PRAISE", "UNCERTAIN_REQUIRES_REVIEW") == "routed_to_review"
    assert redteam.outcome("NEWS_REPORTING", "GLORIFICATION_OR_PRAISE") == "false_alarm"
    items = [{"id": "a", "tactic": "coded_praise", "text": "his aesthetic was unmatched", "language": "en",
              "intended_label": "GLORIFICATION_OR_PRAISE"},
             {"id": "b", "tactic": "counter_speech_keywords", "text": "He was not a hero. Remember the victims.",
              "language": "en", "intended_label": "PREVENTION_OR_SUPPORT"}]
    res = redteam.evaluate(items, {"contextual": ContextualRuleClassifier()})["contextual"]
    assert res["evasion_rate"] == 1.0 and res["false_alarm_rate"] == 0.0
    assert res["failures"][0]["outcome"] == "evaded"


def test_red_team_generation_filters_operational_detail():
    fake = FakeMuse({"items": [{"text": "his aesthetic was unmatched, saint of Ridgeview", "why": "coded"},
                               {"text": "bring a rifle next time", "why": "bad"}]})
    items = redteam.generate(fake, per_tactic=2)
    assert items and not any("rifle" in i["text"] for i in items)


def test_new_endpoints(client):
    assert client.get("/api/graphrag/communities").status_code == 200
    assert client.get("/api/search/semantic", params={"q": "police investigation"}).json()["results"]
    assert client.get("/api/posts/post_0001/media").json() == []
    assert client.get("/api/media/..%2F..%2Fconfig.py").status_code == 404
    r = client.post("/api/graphrag/ask", json={"question": "who are the authors?"})
    assert r.json()["refused"]
