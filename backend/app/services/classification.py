"""Layered content classification.

Layer 1 - keyword signals: sensitive terms used only for *discovery*.
Layer 2 - contextual cues: phrase patterns that indicate how a topic is being
          discussed (reporting, research, prevention, praise, encouragement,
          stated intent). Cues negated by counter-speech are discarded.
Layer 3 - uncertainty handling: ambiguous, weak, or unsupported-language
          content is returned as UNCERTAIN_REQUIRES_REVIEW.

Every result describes *content*, never the person who wrote it. Confidence
is the classifier's confidence in a category, not a probability of danger.
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app import config
from app.agent.muse import FAST_MODEL, MuseClient, MuseError
from app.schemas.models import (
    HARMFUL_CATEGORIES,
    Category,
    ClassificationResult,
    EvidenceSpan,
    MediaObservation,
    ReviewPriority,
)

log = logging.getLogger(__name__)

CONTEXTUAL_MODEL_NAME = "sentinel-contextual-rules"
CONTEXTUAL_MODEL_VERSION = "0.1.0"
BASELINE_MODEL_NAME = "keyword-baseline"
BASELINE_MODEL_VERSION = "0.1.0"

SUPPORTED_LANGUAGES = {"en"}

CATEGORY_LABELS = {
    Category.NEWS_REPORTING: "news reporting",
    Category.ACADEMIC_OR_RESEARCH: "academic or research discussion",
    Category.PREVENTION_OR_SUPPORT: "prevention, support, or counter-speech",
    Category.NEUTRAL_DISCUSSION: "neutral discussion",
    Category.GLORIFICATION_OR_PRAISE: "glorification or praise of violence",
    Category.ENCOURAGEMENT_OR_RECRUITMENT: "encouragement or recruitment",
    Category.EXPLICIT_THREAT_OR_INTENT: "an explicit statement of threat or intent",
    Category.UNCERTAIN_REQUIRES_REVIEW: "uncertain",
}


@dataclass(frozen=True)
class Cue:
    pattern: re.Pattern[str]
    category: Category
    weight: float
    name: str


def _p(regex: str) -> re.Pattern[str]:
    return re.compile(regex, re.IGNORECASE)


# --- Layer 1: discovery keywords (never decide a category on their own) ------
KEYWORD_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("attack", _p(r"\battack(?:s|er|ers)?\b")),
    ("shooting", _p(r"\bshoot(?:ing|ings|er|ers)?\b")),
    ("killer", _p(r"\bkill(?:er|ers|ings?)\b")),
    ("massacre", _p(r"\bmassacres?\b")),
    ("gunman", _p(r"\bgunm[ae]n\b")),
    ("weapon", _p(r"\bweapons?\b")),
    ("manifesto", _p(r"\bmanifestos?\b")),
    ("copycat", _p(r"\bcopycats?\b")),
    ("victims", _p(r"\bvictims?\b")),
    ("perpetrator", _p(r"\bperpetrators?\b")),
]

# --- Layer 2: contextual cues -----------------------------------------------
_FIRST_PERSON_INTENT = r"\b(?:i'?m|i am|im)\s+(?:gonna|going to)\b|\bi(?:'ll| will)\b|\bi'?m (?:planning|planning on)\b|\bi plan to\b"
_HARM_OBJECT = (
    r"(?:do what (?:he|they) did|make (?:them|everyone|all of them) pay|finish what (?:he|they) started"
    r"|be the next one|bring (?:a|my) (?:weapon|gun)|hurt (?:them|everyone|people)|they(?:'ll| will) all regret)"
)

CUES: list[Cue] = [
    # Explicit threat / intent: first-person intent near a harmful object.
    Cue(_p(rf"(?:{_FIRST_PERSON_INTENT})[^.!?\n]{{0,60}}?{_HARM_OBJECT}"), Category.EXPLICIT_THREAT_OR_INTENT, 3.5, "first_person_intent"),
    Cue(_p(r"\b(?:at|to) my (?:school|class|campus|college|office)\b"), Category.EXPLICIT_THREAT_OR_INTENT, 0.8, "personal_target_reference"),
    Cue(_p(r"\b(?:they(?:'ll| will) all (?:pay|regret it)|everyone (?:there )?will (?:pay|regret it))\b"), Category.EXPLICIT_THREAT_OR_INTENT, 2.5, "retribution_statement"),
    Cue(_p(r"\b(?:writing|finished) my (?:own )?manifesto\b"), Category.EXPLICIT_THREAT_OR_INTENT, 2.5, "own_manifesto"),
    # Encouragement / recruitment.
    Cue(_p(r"\b(?:who(?:'?s| is) next|someone (?:should|needs to|has to) (?:do it|finish|do the same|step up)|finish what (?:he|they) started|be the next one|do it again|your turn now)\b"), Category.ENCOURAGEMENT_OR_RECRUITMENT, 3.0, "call_to_repeat"),
    Cue(_p(r"\bfollow (?:his|their) (?:lead|example|path)\b"), Category.ENCOURAGEMENT_OR_RECRUITMENT, 2.5, "follow_example"),
    Cue(_p(r"\b(?:join (?:us|our (?:server|group|channel))|dm (?:me )?for (?:the )?(?:link|server|invite)|invite[- ]only (?:server|group|chat)|private (?:server|group|chat) for (?:real )?fans)\b"), Category.ENCOURAGEMENT_OR_RECRUITMENT, 2.0, "recruitment_invite"),
    # Glorification / praise.
    Cue(_p(r"\b(?:hero|legend|icon|idol|martyr|saint|visionary)s?\b"), Category.GLORIFICATION_OR_PRAISE, 1.5, "praise_term"),
    Cue(_p(r"\b(?:goat|iconic|king|fan ?edits?|tribute edits?|shrine|stan(?:ning)?)\b"), Category.GLORIFICATION_OR_PRAISE, 1.2, "fandom_term"),
    Cue(_p(r"\b(?:deserves? (?:respect|more credit|a statue)|did nothing wrong|did what (?:he|they) had to|showed (?:them|everyone)|so brave|was right)\b"), Category.GLORIFICATION_OR_PRAISE, 2.5, "endorsement_phrase"),
    Cue(_p(r"\b(?:rest in power|never forget the (?:king|legend)|rip king)\b"), Category.GLORIFICATION_OR_PRAISE, 2.0, "memorial_praise"),
    Cue(_p(r"\b(?:love|admire|idoli[sz]e|worship)\b[^.!?\n]{0,30}\b(?:him|the (?:shooter|attacker|killer|perpetrator))\b"), Category.GLORIFICATION_OR_PRAISE, 2.0, "admiration"),
    Cue(_p(r"\b(?:high score|body count record)\b"), Category.GLORIFICATION_OR_PRAISE, 2.0, "gamified_harm"),
    # Prevention / support / counter-speech.
    Cue(_p(r"\b(?:if you or someone|helpline|hotline|reach out|you(?:'re| are) not alone|support (?:line|services|group)|counsell?or|warning signs|talk to (?:someone|a trusted)|report (?:concerns|it|them)|crisis (?:line|text)|check in on|mental health)\b"), Category.PREVENTION_OR_SUPPORT, 1.5, "support_language"),
    Cue(_p(r"\b(?:stop (?:calling|glorifying|romanti[cs]i[sz]ing|sharing)|not (?:a )?(?:hero|legend|icon)|don'?t (?:share|glorify|give (?:him|them) (?:attention|a platform))|remember the victims|say (?:the )?victims'? names|prevention)\b"), Category.PREVENTION_OR_SUPPORT, 2.0, "counter_speech"),
    # News reporting.
    Cue(_p(r"\b(?:police (?:said|say|confirmed)|according to|officials? (?:said|say)|authorities|press conference|reported|court|trial|sentenced|charged|verdict|breaking|statement released|investigators?|spokesperson|update:)"), Category.NEWS_REPORTING, 1.2, "reporting_language"),
    # Academic / research.
    Cue(_p(r"\b(?:study|studies|researchers?|research|paper|journal|peer[- ]reviewed|dataset|literature|survey|criminolog\w*|thesis|findings|methodology|lecture|seminar)\b"), Category.ACADEMIC_OR_RESEARCH, 1.2, "research_language"),
    # Neutral discussion.
    Cue(_p(r"\b(?:documentary|podcast|episode|series|book|watched|watching|listening to|anyone (?:know|else|watched)|thoughts on|timeline|case files?|theor(?:y|ies)|curious)\b"), Category.NEUTRAL_DISCUSSION, 1.0, "discussion_language"),
]

# Negation in the few characters before a harmful cue flips it into
# counter-speech (e.g. "he is NOT a hero", "nobody should call him a legend").
NEGATION_WINDOW = 30
_NEGATION = _p(r"(?:\bnot\b|\bnever\b|\bisn'?t\b|\bwasn'?t\b|\bno\b|\bnobody\b|\bstop calling\b|\bwould never\b|\bdon'?t\b|\bcalling (?:him|them) a\b|\bnot going to\b)[^.!?\n]*$")
# Reported speech ("fans are calling him a legend") marks a cue as described, not endorsed.
_REPORTED_SPEECH = _p(r"(?:\b(?:fans|accounts|users|people|some|posts|communities)\b[^.!?\n]{0,25}\b(?:call(?:ing)?|describ(?:e|ing)|label(?:ling)?|refer(?:ring)? to)\b)[^.!?\n]*$")


@dataclass
class _Match:
    cue: Cue
    start: int
    end: int
    text: str
    negated: bool = False
    reported: bool = False


class Classifier(Protocol):
    name: str
    version: str

    def classify(self, text: str, language: str = "en", media: list[Path] | None = None) -> ClassificationResult: ...


def keyword_signals(text: str) -> list[EvidenceSpan]:
    spans = []
    for name, pattern in KEYWORD_SIGNALS:
        for m in pattern.finditer(text):
            spans.append(
                EvidenceSpan(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    cue_category="KEYWORD_SIGNAL",
                    note=f"Sensitive keyword '{name}': a discovery signal only, not a decision.",
                )
            )
    return spans


def _find_cues(text: str) -> list[_Match]:
    matches: list[_Match] = []
    for cue in CUES:
        for m in cue.pattern.finditer(text):
            match = _Match(cue, m.start(), m.end(), m.group(0))
            if cue.category in HARMFUL_CATEGORIES:
                prefix = text[max(0, m.start() - NEGATION_WINDOW) : m.start()]
                match.negated = bool(_NEGATION.search(prefix))
                match.reported = bool(_REPORTED_SPEECH.search(text[max(0, m.start() - 60) : m.start()]))
            matches.append(match)
    # Drop harmful cues that sit inside a counter-speech phrase ("not a hero").
    counter = [m for m in matches if m.cue.name == "counter_speech"]
    for m in matches:
        if m.cue.category in HARMFUL_CATEGORIES and any(c.start <= m.start and m.end <= c.end for c in counter):
            m.negated = True
    return matches


def review_priority(category: Category, confidence: float, scores: dict[str, float]) -> ReviewPriority:
    if category == Category.EXPLICIT_THREAT_OR_INTENT:
        return "urgent"
    if scores.get(Category.EXPLICIT_THREAT_OR_INTENT.value, 0) > 0:
        return "urgent"  # any unresolved intent cue gets a human look first
    if category == Category.ENCOURAGEMENT_OR_RECRUITMENT:
        return "high"
    if category == Category.GLORIFICATION_OR_PRAISE:
        return "high" if confidence >= 0.6 else "normal"
    if category == Category.UNCERTAIN_REQUIRES_REVIEW:
        harmful = sum(scores.get(c.value, 0) for c in HARMFUL_CATEGORIES)
        return "high" if harmful > 0 else "normal"
    return "low"


class ContextualRuleClassifier:
    """Transparent, offline contextual classifier used by default in the demo."""

    name = CONTEXTUAL_MODEL_NAME
    version = CONTEXTUAL_MODEL_VERSION

    # Decision thresholds (documented in docs/evaluation.md).
    MIN_CONFIDENCE = 0.45
    AMBIGUITY_RATIO = 0.75

    def classify(self, text: str, language: str = "en", media: list[Path] | None = None) -> ClassificationResult:
        keywords = keyword_signals(text)
        matches = _find_cues(text)

        scores: dict[str, float] = {c.value: 0.0 for c in Category if c != Category.UNCERTAIN_REQUIRES_REVIEW}
        spans: list[EvidenceSpan] = []
        signals: list[str] = sorted({f"keyword:{s.text.lower()}" for s in keywords})
        harmful_counts: dict[Category, int] = {}

        for m in matches:
            category, weight, note = m.cue.category, m.cue.weight, f"Phrase associated with {CATEGORY_LABELS[m.cue.category]}."
            if m.negated:
                category, weight = Category.PREVENTION_OR_SUPPORT, 1.0
                note = "Harmful phrase appears negated or rejected (counter-speech)."
                signals.append("negated_cue")
            elif m.reported:
                category, weight = Category.NEUTRAL_DISCUSSION, 0.8
                note = "Harmful phrase appears as reported speech (describing others), not endorsement."
                signals.append("reported_speech")
            else:
                signals.append(f"cue:{m.cue.name}")
                if category in HARMFUL_CATEGORIES:
                    harmful_counts[category] = harmful_counts.get(category, 0) + 1
            scores[category.value] += weight
            spans.append(EvidenceSpan(start=m.start, end=m.end, text=m.text, cue_category=category, note=note))

        if harmful_counts.get(Category.GLORIFICATION_OR_PRAISE, 0) >= 2:
            signals.append("repeated_glorification_cues")

        spans.extend(keywords)
        spans.sort(key=lambda s: (s.start, s.end))
        signals = sorted(set(signals))
        scores = {k: round(v, 2) for k, v in scores.items()}

        category, confidence, reason = self._decide(scores, bool(keywords), language)
        if language not in SUPPORTED_LANGUAGES:
            signals.append("unsupported_language")

        explanation = self._explain(category, confidence, reason, matches, keywords)
        return ClassificationResult(
            category=category,
            confidence=round(confidence, 3),
            evidence_spans=spans,
            explanation=explanation,
            signals=signals,
            model_name=self.name,
            model_version=self.version,
            category_scores=scores,
        )

    def _decide(self, scores: dict[str, float], has_keywords: bool, language: str) -> tuple[Category, float, str]:
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        (top_cat, top), (second_cat, second) = ranked[0], ranked[1]
        total = sum(scores.values())

        if language not in SUPPORTED_LANGUAGES:
            return (
                Category.UNCERTAIN_REQUIRES_REVIEW,
                0.2,
                f"The classifier has not been validated for language '{language}', so a human must review it.",
            )
        if total == 0:
            if has_keywords:
                return (
                    Category.UNCERTAIN_REQUIRES_REVIEW,
                    0.3,
                    "Sensitive keywords appear but there is no contextual cue showing how they are used.",
                )
            return Category.NEUTRAL_DISCUSSION, 0.4, "No sensitive keywords or contextual cues were found."

        confidence = min(0.97, top / (total + 0.8))
        top_c, second_c = Category(top_cat), Category(second_cat)
        crosses_harm_boundary = (top_c in HARMFUL_CATEGORIES) != (second_c in HARMFUL_CATEGORIES)
        if second > 0 and second >= self.AMBIGUITY_RATIO * top and crosses_harm_boundary:
            return (
                Category.UNCERTAIN_REQUIRES_REVIEW,
                confidence,
                f"Cues for {CATEGORY_LABELS[top_c]} and {CATEGORY_LABELS[second_c]} are similarly strong.",
            )
        if confidence < self.MIN_CONFIDENCE:
            return (
                Category.UNCERTAIN_REQUIRES_REVIEW,
                confidence,
                "Contextual cues are weak or mixed, so the model is not confident in any category.",
            )
        return top_c, confidence, ""

    @staticmethod
    def _explain(category: Category, confidence: float, reason: str, matches: list[_Match], keywords: list[EvidenceSpan]) -> str:
        parts: list[str] = []
        if category == Category.UNCERTAIN_REQUIRES_REVIEW:
            parts.append(f"Marked for human review: {reason}")
        else:
            cue_texts = [f"'{m.text}'" for m in matches if m.cue.category == category and not (m.negated or m.reported)]
            if category == Category.PREVENTION_OR_SUPPORT:
                cue_texts += [f"'{m.text}'" for m in matches if m.negated]
            if category == Category.NEUTRAL_DISCUSSION:
                cue_texts += [f"'{m.text}'" for m in matches if m.reported]
            label = CATEGORY_LABELS[category]
            if cue_texts:
                parts.append(f"Phrases such as {', '.join(dict.fromkeys(cue_texts[:3]))} suggest {label} ({confidence:.0%} model confidence).")
            else:
                parts.append(f"{reason} ({confidence:.0%} model confidence).")
        if keywords:
            kw = ", ".join(dict.fromkeys(f"'{k.text.lower()}'" for k in keywords[:4]))
            parts.append(f"Sensitive keywords ({kw}) were treated as discovery signals only.")
        parts.append("Based only on this post's text; it is not an assessment of the author.")
        return " ".join(parts)


class KeywordBaselineClassifier:
    """Naive keyword filter, kept only as an evaluation baseline.

    It represents the approach Crime Sentinel is designed to improve on: any
    sensitive term is flagged as harmful regardless of context.
    """

    name = BASELINE_MODEL_NAME
    version = BASELINE_MODEL_VERSION
    _praise = _p(r"\b(?:hero|legend|icon|idol|king|goat)\b")
    _repeat = _p(r"\b(?:next|again|join)\b")
    _intent = _p(r"\b(?:i'?m going to|i will|i'll)\b")

    def classify(self, text: str, language: str = "en", media: list[Path] | None = None) -> ClassificationResult:
        keywords = keyword_signals(text)
        if self._intent.search(text) and keywords:
            category = Category.EXPLICIT_THREAT_OR_INTENT
        elif self._repeat.search(text) and keywords:
            category = Category.ENCOURAGEMENT_OR_RECRUITMENT
        elif self._praise.search(text) or keywords:
            category = Category.GLORIFICATION_OR_PRAISE
        else:
            category = Category.NEUTRAL_DISCUSSION
        return ClassificationResult(
            category=category,
            confidence=1.0 if keywords else 0.5,
            evidence_spans=keywords,
            explanation="Keyword baseline: flags any sensitive term without considering context.",
            signals=[f"keyword:{k.text.lower()}" for k in keywords],
            model_name=self.name,
            model_version=self.version,
        )


MUSE_SYSTEM_PROMPT = """You classify public social-media posts for an authorised trust-and-safety research tool that
studies online communities around violent attacks. Classify the CONTENT only. Never make claims about the author's
beliefs, identity, or dangerousness.

Categories:
- NEWS_REPORTING: factual reporting of events, often attributed to police, officials, or outlets.
- ACADEMIC_OR_RESEARCH: research, study, or analytical discussion of the phenomenon.
- PREVENTION_OR_SUPPORT: counter-speech, rejecting glorification, remembering victims, support resources.
- NEUTRAL_DISCUSSION: on-topic talk (documentaries, timelines, describing what others say) without endorsement.
- GLORIFICATION_OR_PRAISE: praising or idolising an attacker or attack, including coded or aesthetic praise
  ("his aesthetic was unmatched", "saint", fan edits, countdowns celebrating an anniversary).
- ENCOURAGEMENT_OR_RECRUITMENT: urging others to commit or repeat violence, including paraphrased calls to action
  ("somebody needs to carry on his work", "who's next").
- EXPLICIT_THREAT_OR_INTENT: the poster states their own intent or a plan to commit violence.
- UNCERTAIN_REQUIRES_REVIEW: ambiguous, sarcastic, or you are unsure.

Keywords alone do not determine intent: reported speech ("fans are calling him a hero, which is disturbing") and
negation ("he was not a hero") are not glorification. When in doubt, use UNCERTAIN_REQUIRES_REVIEW.
Evidence quotes must be exact substrings copied from the post.
Respond with JSON only: {"category": str, "confidence": number 0-1, "evidence_quotes": [str],
"explanation": "one short, cautious sentence"}"""


VISION_ADDENDUM = """
One or more images are attached to the post. Classify the post AS A WHOLE (text and images together): the same
caption can be a memorial for victims or a shrine to an attacker depending on the picture. A haloed or idolised
image of an attacker, a shrine to them, or a celebratory countdown is glorification even with a neutral caption;
the same picture shared with a critical caption is not. Add to the JSON:
"image_observation": "one neutral sentence describing what is visible",
"image_text": "any text visible in the images, verbatim, or empty",
"visual_evidence": "what in the image supports a harmful category, or empty"."""

FEW_SHOT_HEADER = """Reviewer-verified examples from this deployment (human decisions; follow them where a post is
genuinely similar, but judge this post on its own content):"""


class MuseClassifier:
    """Meta Muse classifier (text + vision), cross-checked by the contextual rules (two engines).

    Muse decides the category, and the rules act as a safety net:
    - harm flagged by Muse must be backed by a quote that appears in the post, or by visual evidence in an image;
    - harm the rules find (in the post, or in text Muse read off an image) but Muse dismisses goes to human review;
    - languages the tool is not validated for always go to review (Muse's suggestion is kept as a signal);
    - any Muse failure falls back to the rule result.
    Rule cue scores are stored as `category_scores`, so an intent cue keeps a post urgent whatever Muse says.

    Learning loop: `examples` are reviewer decisions. For each post the most similar ones (by embedding) are added
    to the prompt as few-shot examples, so corrections take effect without retraining a model.
    """

    version = "0.3.0"
    MAX_EXAMPLES = 4

    def __init__(self, muse: MuseClient | None = None, model: str = FAST_MODEL,
                 fallback: Classifier | None = None, workers: int = 8,
                 examples: list[dict] | None = None, embedder=None):
        self.muse = muse or MuseClient()
        self.model = model
        self.name = f"muse:{model}"
        self.fallback = fallback or ContextualRuleClassifier()
        self.workers = workers
        self._cache: dict[tuple, ClassificationResult] = {}
        self.examples = examples or []
        self.embedder = embedder
        self._example_vectors = (embedder.embed([e["text"] for e in self.examples])
                                 if embedder is not None and self.examples else None)

    def classify(self, text: str, language: str = "en", media: list[Path] | None = None) -> ClassificationResult:
        key = (text, language, tuple(str(m) for m in media or ()))
        if key not in self._cache:
            self._cache[key] = self._classify(text, language, list(media or ()))
        return self._cache[key]

    def classify_many(self, items: list[tuple]) -> list[ClassificationResult]:
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(lambda item: self.classify(*item), items))

    def _few_shot(self, text: str) -> list[dict]:
        pool = [i for i, e in enumerate(self.examples) if e["text"].strip() != text.strip()]  # never its own label
        if not pool:
            return []
        if self._example_vectors is not None:
            scores = self._example_vectors[pool] @ self.embedder.embed([text])[0]
            ranked = [pool[i] for i in sorted(range(len(pool)), key=lambda i: -scores[i])]
        else:
            ranked = pool
        return [self.examples[i] for i in ranked[: self.MAX_EXAMPLES]]

    def _classify(self, text: str, language: str, media: list[Path]) -> ClassificationResult:
        from app.services.media import image_part

        rules = self.fallback.classify(text, language)
        images = [m for m in media if Path(m).exists()]
        shots = self._few_shot(text)
        prompt = f'Language: {language}\nPost:\n"""{text}"""'
        if shots:
            prompt = FEW_SHOT_HEADER + "\n" + "\n".join(
                f'- "{e["text"][:300]}" -> {e["label"]}' + (f' (reviewer note: {e["note"][:150]})' if e.get("note") else "")
                for e in shots) + "\n\n" + prompt
        user: str | list[dict] = prompt
        if images:
            user = [{"type": "text", "text": prompt}, *(image_part(Path(m)) for m in images)]
        try:
            r = self.muse.chat(
                "classifier_vision" if images else "classifier",
                MUSE_SYSTEM_PROMPT + (VISION_ADDENDUM if images else ""),
                user,
                model=self.model,
                reasoning_effort="minimal",
                max_tokens=600 if images else 400,
                temperature=0,
            )
            data = r.data or {}
            category = Category(data["category"])
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        except (MuseError, KeyError, ValueError, TypeError, AttributeError) as exc:
            log.warning("Muse classification failed, using rule classifier: %s", exc)
            rules.signals = sorted(set(rules.signals + ["muse_fallback"]))
            return rules

        spans = [s for s in rules.evidence_spans if s.cue_category == "KEYWORD_SIGNAL"]
        quoted = 0
        for quote in (data.get("evidence_quotes") or [])[:5]:
            idx = text.find(quote) if isinstance(quote, str) and quote.strip() else -1
            if idx >= 0:
                quoted += 1
                spans.append(EvidenceSpan(start=idx, end=idx + len(quote), text=quote, cue_category=category,
                                          note="Quoted by Meta Muse as evidence."))

        signals = set(rules.signals) | {"muse_classifier"}
        if shots:
            signals.add(f"fewshot_reviewer_examples:{len(shots)}")
        notes: list[str] = []
        scores = dict(rules.category_scores)
        rules_category = rules.category
        observations: list[MediaObservation] = []
        visual_evidence = ""
        if images:
            signals.add("muse_vision")
            image_text = str(data.get("image_text") or "")[:500]
            visual_evidence = str(data.get("visual_evidence") or "")[:300]
            observations = [MediaObservation(file=Path(m).name, observation=str(data.get("image_observation") or "")[:400],
                                             image_text=image_text, visual_evidence=visual_evidence,
                                             engine=f"muse-vision:{r.model}") for m in images[:1]]
            if image_text.strip():
                # Second engine on the image too: run the rules over the text Muse read off the image (OCR).
                ocr = self.fallback.classify(image_text, language)
                for k, v in ocr.category_scores.items():
                    scores[k] = round(scores.get(k, 0) + v, 2)
                if ocr.category in HARMFUL_CATEGORIES:
                    signals.add(f"ocr_cue:{ocr.category.value}")
                    if rules_category not in HARMFUL_CATEGORIES:
                        rules_category = ocr.category

        uncertain = Category.UNCERTAIN_REQUIRES_REVIEW
        muse_harmful, rules_harmful = category in HARMFUL_CATEGORIES, rules_category in HARMFUL_CATEGORIES
        if muse_harmful and not quoted and not (images and visual_evidence.strip()):
            signals.add("muse_evidence_not_found")
            notes.append(f"Muse suggested {CATEGORY_LABELS[category]} but quoted nothing from the post, so a human must check.")
            category = uncertain
        elif rules_harmful and not muse_harmful and category != uncertain:
            signals.add("engines_disagree")
            notes.append(f"The rule engine found {CATEGORY_LABELS[rules_category]} cues that Muse did not, so a human must decide.")
            spans += [s for s in rules.evidence_spans if s.cue_category == rules_category]
            category = uncertain
        elif muse_harmful != rules_harmful and rules.category != uncertain:
            signals.add("engines_disagree")  # Muse caught harm the rules missed (e.g. coded praise, an image)
        if muse_harmful and not quoted and visual_evidence.strip() and category != uncertain:
            signals.add("visual_evidence_only")
            notes.append(f"The harmful reading rests on the image: {visual_evidence}")
        if language not in SUPPORTED_LANGUAGES and category != uncertain:
            signals.add(f"muse_suggested:{category.value}")
            notes.append(f"Muse suggests {CATEGORY_LABELS[category]}, but the tool is not validated for '{language}', "
                         "so a human must review it.")
            category = uncertain
        if confidence < ContextualRuleClassifier.MIN_CONFIDENCE and category != uncertain:
            notes.append("Muse's confidence is low.")
            category = uncertain

        explanation = " ".join([str(data.get("explanation", ""))[:400], *notes])
        unique = {(s.start, s.end, s.cue_category): s for s in spans}
        return ClassificationResult(
            category=category,
            confidence=round(confidence, 3),
            evidence_spans=sorted(unique.values(), key=lambda s: (s.start, s.end)),
            explanation=f"{explanation} (Muse-generated rationale; verify against the original text.)",
            signals=sorted(signals),
            model_name=self.name,
            model_version=self.version,
            category_scores=scores,
            media_observations=observations,
        )


def classify_all(classifier: Classifier, items: list[tuple]) -> list[ClassificationResult]:
    """Classify (text, language[, media paths]) tuples, in parallel when the classifier supports it."""
    many = getattr(classifier, "classify_many", None)
    return many(items) if many else [classifier.classify(*item) for item in items]


def get_muse_classifier(examples: list[dict] | None = None) -> MuseClassifier | None:
    """The Muse classifier, or None when CRIME_SENTINEL_CLASSIFIER=rules or no API key is configured."""
    mode = os.getenv("CRIME_SENTINEL_CLASSIFIER", "auto").lower()
    if mode == "rules":
        return None
    if config.LLM_BASE_URL and config.LLM_MODEL:
        client = MuseClient(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL.rstrip("/"))
        model = config.LLM_MODEL
    else:
        client, model = MuseClient(), FAST_MODEL
    if not client.enabled:
        if mode == "muse":
            raise RuntimeError("CRIME_SENTINEL_CLASSIFIER=muse but no API key is set (MODEL_API_KEY in backend/.env)")
        return None
    if examples:
        from app.services.embeddings import get_embedder

        return MuseClassifier(client, model, examples=examples, embedder=get_embedder())
    return MuseClassifier(client, model)


def get_classifier(examples: list[dict] | None = None) -> Classifier:
    """Muse when a key is configured (default `auto`), otherwise the offline rule classifier."""
    return get_muse_classifier(examples) or ContextualRuleClassifier()
