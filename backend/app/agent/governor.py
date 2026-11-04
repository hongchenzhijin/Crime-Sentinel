"""Safety Governor: an independent check on every outbound persona action.

Two layers, both must pass:
1. Deterministic rules (regex + the contextual classifier) - hard blocks that
   no model output can override.
2. A Muse judge with its own system prompt and no access to the persona's goal,
   so it cannot be talked into "it's fine, it helps the mission".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agent.muse import FAST_MODEL, MuseClient, MuseError
from app.agent.policy import RULES, RULES_TEXT
from app.schemas.models import HARMFUL_CATEGORIES
from app.services.classification import ContextualRuleClassifier

_classifier = ContextualRuleClassifier()

_CHECKS: list[tuple[str, re.Pattern[str], str]] = [
    ("R2", re.compile(r"\b(i'?m in|count me in|i'?ll be there|i'?m down|let'?s do (it|this)|sign me up|i'?m ready|i'?m with you)\b", re.I),
     "commits to a plan or joins a call to action"),
    ("R4", re.compile(r"\b(i'?m|i am|im)\s*(1[0-7]|twelve|thirteen|fourteen|fifteen|sixteen|seventeen)\b|\bmy (school|class|teacher|classmates)\b|\b(high school|secondary school|form [1-5])\b", re.I),
     "claims or implies being a minor or a student"),
    ("R5", re.compile(r"[\w.+-]+@[\w-]+\.\w+|(?<!\w)\+?\d[\d\s-]{7,}\d|\b(my address|i live (at|on)|my number)\b", re.I),
     "shares personal information"),
    ("R7", re.compile(r"\b(gun|guns|rifle|weapon|weapons|knife|explosive|bomb|ammo|ammunition|target|targets)\b", re.I),
     "mentions operational details"),
    ("R9", re.compile(r"\b(i'?m|i am)\s+(a |an )?(police|cop|officer|detective|agent|investigator|journalist|reporter|researcher)\b", re.I),
     "impersonates an official, journalist or researcher"),
]
MAX_CHARS = 400

JUDGE_SYSTEM = f"""You are an independent safety auditor for an authorised trust-and-safety research tool.
An undercover research persona wants to send the message below inside an online community. You do NOT share the
persona's goals. Your only job is to check the message against these rules of engagement:
{RULES_TEXT}
Be strict: any wording that could read as praise, encouragement, agreement to a plan, or provocation is a violation.
Respond with JSON only: {{"decision": "allow" | "revise" | "block", "violations": ["R1", ...],
"explanation": "one sentence", "suggested_fix": "how to rephrase, or empty"}}"""


@dataclass
class Verdict:
    decision: str  # allow | revise | block
    violations: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    engine: str = "rules"
    judge_explanation: str = ""
    suggested_fix: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"

    def feedback(self) -> str:
        parts = [f"{v}: {RULES[v]}" for v in dict.fromkeys(self.violations)]
        if self.suggested_fix:
            parts.append(f"Suggested fix: {self.suggested_fix}")
        return " ".join(parts)

    def as_dict(self) -> dict:
        return {"decision": self.decision, "violations": list(dict.fromkeys(self.violations)), "reasons": self.reasons,
                "engine": self.engine, "judge_explanation": self.judge_explanation, "suggested_fix": self.suggested_fix}


def rule_check(text: str) -> Verdict:
    violations, reasons = [], []
    result = _classifier.classify(text)
    harmful = {c.value for c in HARMFUL_CATEGORIES}
    hits = [s for s in result.evidence_spans if s.cue_category in harmful]
    if hits:
        cat = hits[0].cue_category
        violations.append("R2" if cat != "GLORIFICATION_OR_PRAISE" else "R1")
        reasons.append(f"contextual classifier found {cat.lower().replace('_', ' ')} cue '{hits[0].text}'")
    for rule, pattern, why in _CHECKS:
        m = pattern.search(text)
        if m:
            violations.append(rule)
            reasons.append(f"{why} ('{m.group(0)}')")
    if len(text) > MAX_CHARS:
        violations.append("R8")
        reasons.append(f"message longer than {MAX_CHARS} characters")
    if not violations:
        return Verdict("allow", engine="rules")
    return Verdict("revise" if violations == ["R8"] else "block", violations, reasons, engine="rules")


class SafetyGovernor:
    def __init__(self, muse: MuseClient):
        self.muse = muse

    def check_message(self, text: str, context: str) -> Verdict:
        verdict = rule_check(text)
        if not verdict.allowed or not self.muse.enabled:
            return verdict
        try:
            r = self.muse.chat(
                "governor",
                JUDGE_SYSTEM,
                f"Context: {context}\n\nProposed message:\n\"\"\"{text}\"\"\"",
                model=FAST_MODEL,
                reasoning_effort="low",
                max_tokens=300,
                temperature=0,
            )
            d = r.data or {}
            decision = d.get("decision", "block")
            if decision not in ("allow", "revise", "block"):
                decision = "block"
            return Verdict(decision, [v for v in d.get("violations", []) if v in RULES], [],
                           engine=f"rules+muse:{r.model}", judge_explanation=str(d.get("explanation", ""))[:300],
                           suggested_fix=str(d.get("suggested_fix", ""))[:300])
        except MuseError as exc:
            # Fail closed: if the judge is unreachable, a human must approve.
            return Verdict("revise", [], [f"Muse judge unavailable ({exc}); human approval required"], engine="rules")

    @staticmethod
    def check_join(group: dict) -> Verdict:
        if group.get("protected_space"):
            return Verdict("block", ["R6"], ["group is a protected victim/survivor support space"])
        text = f"{group['name']} {group['description']}".lower()
        if re.search(r"\b(survivor|families|support|grief|counsell?ing|victims?)\b", text) and not re.search(
            r"\b(no press|understand him|rest in power)\b", text
        ):
            return Verdict("block", ["R6"], ["group description indicates a support space"])
        return Verdict("allow")
