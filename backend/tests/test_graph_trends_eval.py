from datetime import datetime, timedelta, timezone

from app.db import repository as repo
from app.schemas.models import Category, Classification, Post, PostWithClassification
from app.services import evaluation, graph, trends


def test_every_edge_has_method_and_provenance(conn):
    g = graph.build_graph(repo.all_posts(conn), repo.get_topics(conn))
    assert g.edges
    node_ids = {n.id for n in g.nodes}
    for e in g.edges:
        assert e.method and e.provenance
        assert e.source in node_ids and e.target in node_ids


def test_graph_has_no_person_nodes(conn):
    g = graph.build_graph(repo.all_posts(conn), repo.get_topics(conn))
    assert {n.type for n in g.nodes} <= {"POST", "HASHTAG", "TOPIC", "PUBLIC_COMMUNITY_REFERENCE"}
    assert not any("anon_" in n.label or "account_" in n.label for n in g.nodes)


def test_public_link_edges_only_between_known_posts(conn):
    g = graph.build_graph(repo.all_posts(conn), repo.get_topics(conn), {"PUBLICLY_LINKED_TO"})
    assert [(e.source, e.target) for e in g.edges] == [("post_0007", "post_0006")]


def test_similarity_edges_respect_threshold():
    assert graph.jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
    assert graph.jaccard(frozenset(), frozenset({"a"})) == 0.0


def test_graph_truncation(conn):
    g = graph.build_graph(repo.all_posts(conn), repo.get_topics(conn), max_posts=3)
    assert g.truncated
    assert sum(1 for n in g.nodes if n.type == "POST") == 3


def _item(i: int, ts: datetime, topics=("t1",), category=Category.NEUTRAL_DISCUSSION) -> PostWithClassification:
    return PostWithClassification(
        post=Post(id=f"post_{i}", source_type="synthetic", source_name="s", source_url=None, published_at=ts,
                  text="x", language="en", hashtags=[], public_topic_ids=list(topics), author_reference=f"anon_{i % 2}",
                  interaction_reference_ids=[], is_synthetic=True),
        classification=Classification(post_id=f"post_{i}", category=category, confidence=0.8, evidence_spans=[],
                                      explanation="", signals=[], model_name="m", model_version="1",
                                      classified_at=ts),
    )


def test_trends_are_computed_and_small_buckets_withheld():
    base = datetime(2026, 9, 7, tzinfo=timezone.utc)  # Monday
    items = [_item(i, base + timedelta(hours=i)) for i in range(6)]  # week 1: 6 posts
    items += [_item(100 + i, base + timedelta(days=7, hours=i)) for i in range(2)]  # week 2: 2 posts
    result = trends.compute_trends(items, {}, "week", min_sample=5)
    w1, w2 = result["series"]
    assert w1["total_posts"] == 6 and w1["sufficient_sample"] and w1["categories"]["NEUTRAL_DISCUSSION"] == 6
    assert w2["total_posts"] == 2 and not w2["sufficient_sample"] and w2["categories"] == {}
    assert w1["unique_author_pseudonyms"] == 2
    assert "not evidence of increased real-world danger" in result["caveat"]


def test_emerging_topic_requires_volume_and_growth():
    end = datetime(2026, 10, 30, tzinfo=timezone.utc)
    items = [_item(i, end - timedelta(days=20), topics=("old",)) for i in range(10)]
    items += [_item(100 + i, end - timedelta(days=3), topics=("new",)) for i in range(12)]
    items += [_item(200 + i, end - timedelta(days=2), topics=("tiny",)) for i in range(3)]
    rows = {r["topic_id"]: r for r in trends.emerging_topics(items, {})["topics"]}
    assert rows["new"]["emerging"]
    assert not rows["tiny"]["emerging"]  # growth but below minimum sample
    assert not rows["old"]["emerging"]


def test_score_metrics():
    gold = ["NEWS_REPORTING", "NEWS_REPORTING", "GLORIFICATION_OR_PRAISE", "NEUTRAL_DISCUSSION"]
    pred = ["NEWS_REPORTING", "GLORIFICATION_OR_PRAISE", "GLORIFICATION_OR_PRAISE", "UNCERTAIN_REQUIRES_REVIEW"]
    s = evaluation.score(gold, pred)
    assert s["per_class"]["NEWS_REPORTING"] == {"precision": 1.0, "recall": 0.5, "f1": 0.667, "support": 2, "predicted": 1}
    assert s["per_class"]["GLORIFICATION_OR_PRAISE"]["precision"] == 0.5
    assert s["harm_binary"]["false_positives"] == 1
    assert s["harm_binary"]["non_harmful_items"] == 3
    labels = s["confusion_matrix"]["labels"]
    m = s["confusion_matrix"]["matrix"]
    assert m[labels.index("NEWS_REPORTING")][labels.index("GLORIFICATION_OR_PRAISE")] == 1


def test_full_evaluation_beats_baseline_on_false_positives():
    result = evaluation.run_evaluation()
    assert result["dataset"]["size"] >= 50
    ctx, base = result["contextual"]["harm_binary"], result["baseline"]["harm_binary"]
    assert ctx["false_positive_rate"] < base["false_positive_rate"]
    assert result["limitations"]
