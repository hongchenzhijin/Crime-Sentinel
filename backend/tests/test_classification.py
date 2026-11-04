import pytest

from app.schemas.models import Category
from app.services.classification import ContextualRuleClassifier, KeywordBaselineClassifier, review_priority

clf = ContextualRuleClassifier()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Police said the Ridgeview attack is under investigation, according to officials.", Category.NEWS_REPORTING),
        ("Researchers published a peer-reviewed study on the Ridgeview attack and online fandoms.", Category.ACADEMIC_OR_RESEARCH),
        ("Stop glorifying the Ridgeview attack. Remember the victims.", Category.PREVENTION_OR_SUPPORT),
        ("Watched the documentary about the Ridgeview attack, anyone know why the timeline changed?", Category.NEUTRAL_DISCUSSION),
        ("The Ridgeview attack guy is a legend, deserves respect", Category.GLORIFICATION_OR_PRAISE),
        ("Ridgeview attack anniversary soon. Who's next?", Category.ENCOURAGEMENT_OR_RECRUITMENT),
        ("I'm going to do what he did in the Ridgeview attack at my school.", Category.EXPLICIT_THREAT_OR_INTENT),
    ],
)
def test_same_keyword_different_contexts(text, expected):
    """The same sensitive keyword ('attack') receives different categories by context."""
    result = clf.classify(text)
    assert result.category == expected
    assert "keyword:attack" in result.signals


def test_negated_praise_is_counter_speech():
    result = clf.classify("He was not a hero. Nobody should call him a legend.")
    assert result.category == Category.PREVENTION_OR_SUPPORT
    assert "negated_cue" in result.signals


def test_reported_speech_is_not_endorsement():
    result = clf.classify("Fans are calling the attacker a hero online, which is disturbing")
    assert result.category not in {Category.GLORIFICATION_OR_PRAISE}


def test_keyword_without_context_requires_review():
    result = clf.classify("the shooting changed everything")
    assert result.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert result.confidence < 0.5


def test_no_signals_is_low_confidence_neutral():
    result = clf.classify("Going to the library later to pick up some novels.")
    assert result.category == Category.NEUTRAL_DISCUSSION
    assert result.confidence <= 0.5


def test_first_person_harmless_plan_is_not_threat():
    result = clf.classify("I'm going to watch the documentary about the attack tonight.")
    assert result.category != Category.EXPLICIT_THREAT_OR_INTENT


def test_unsupported_language_routes_to_review():
    result = clf.classify("Dia memang legenda, hormat", language="ms")
    assert result.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert "unsupported_language" in result.signals


def test_mixed_signals_across_harm_boundary_are_uncertain():
    result = clf.classify("Researchers call him an icon of the online subculture")
    assert result.category == Category.UNCERTAIN_REQUIRES_REVIEW


def test_evidence_spans_point_into_text():
    text = "The attacker is a legend, deserves respect"
    result = clf.classify(text)
    assert result.evidence_spans
    for span in result.evidence_spans:
        assert text[span.start : span.end] == span.text


def test_explanation_disclaims_author_assessment_and_records_model():
    result = clf.classify("The attacker is a legend")
    assert "not an assessment of the author" in result.explanation
    assert result.model_name and result.model_version
    assert 0.0 <= result.confidence <= 1.0


def test_threat_is_urgent_priority():
    result = clf.classify("I'm going to make them pay at my school")
    assert review_priority(result.category, result.confidence, result.category_scores) == "urgent"


def test_baseline_flags_news_as_harmful():
    """Documents the failure mode the contextual layer is designed to fix."""
    result = KeywordBaselineClassifier().classify("Police said the attack is under investigation.")
    assert result.category == Category.GLORIFICATION_OR_PRAISE


# --- Muse classifier (two engines), with a fake Muse client: no network calls ---

from app.agent.muse import MuseError, MuseResult  # noqa: E402
from app.services.classification import MuseClassifier, classify_all, get_classifier  # noqa: E402


class FakeMuse:
    enabled = True

    def __init__(self, reply=None, error=False):
        self.reply, self.error, self.calls = reply or {}, error, 0

    def chat(self, purpose, system, user, **kwargs):
        self.calls += 1
        if self.error:
            raise MuseError("boom")
        return MuseResult("", self.reply, "muse-spark-1.3", 1, 10, 10, 0, 0.0)


def muse_clf(**reply):
    return MuseClassifier(FakeMuse(reply))


def test_muse_catches_coded_praise_rules_miss():
    text = "his aesthetic was unmatched, true saint"
    r = muse_clf(category="GLORIFICATION_OR_PRAISE", confidence=0.85, evidence_quotes=["true saint"]).classify(text)
    assert r.category == Category.GLORIFICATION_OR_PRAISE
    assert r.model_name == "muse:muse-spark-1.3"
    assert any(s.text == "true saint" for s in r.evidence_spans)


def test_muse_harm_without_real_quote_goes_to_review():
    r = muse_clf(category="GLORIFICATION_OR_PRAISE", confidence=0.9, evidence_quotes=["not in the post"]).classify(
        "Watched the documentary last night")
    assert r.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert "muse_evidence_not_found" in r.signals


def test_rules_threat_overrides_muse_dismissal():
    text = "I'm going to do what he did at my school."
    r = muse_clf(category="NEUTRAL_DISCUSSION", confidence=0.9, evidence_quotes=[]).classify(text)
    assert r.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert "engines_disagree" in r.signals
    assert review_priority(r.category, r.confidence, r.category_scores) == "urgent"


def test_unvalidated_language_routed_to_review_with_suggestion():
    r = muse_clf(category="GLORIFICATION_OR_PRAISE", confidence=0.9, evidence_quotes=["legenda"]).classify(
        "Dia memang legenda, hormat", language="ms")
    assert r.category == Category.UNCERTAIN_REQUIRES_REVIEW
    assert "muse_suggested:GLORIFICATION_OR_PRAISE" in r.signals


def test_muse_failure_falls_back_to_rules():
    r = MuseClassifier(FakeMuse(error=True)).classify("The attacker is a legend")
    assert r.model_name == ContextualRuleClassifier.name
    assert "muse_fallback" in r.signals


def test_muse_results_cached_and_batched():
    fake = FakeMuse({"category": "NEWS_REPORTING", "confidence": 0.9, "evidence_quotes": ["Police said"]})
    clf_ = MuseClassifier(fake)
    out = classify_all(clf_, [("Police said it happened.", "en")] * 3)
    assert [r.category for r in out] == [Category.NEWS_REPORTING] * 3
    assert fake.calls <= 3 and clf_.classify("Police said it happened.").category == Category.NEWS_REPORTING


def test_tests_run_offline():
    assert get_classifier().name == ContextualRuleClassifier.name
