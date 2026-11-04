"""Analyst: classifies what the persona observes and assesses whole communities.

Per post, two independent opinions are combined: the transparent contextual
rule classifier, and Muse (text plus vision for attached images). When they
disagree, the post goes to a human, except that a threat signal from either
one escalates it.

Per community, Muse reads the entire observed feed in a single long-context
call and assigns a risk tier with cited evidence. A rule-based tier is computed
alongside it, and the higher of the two is used.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app import config
from app.agent.muse import DEEP_MODEL, FAST_MODEL, MuseClient, MuseError, image_part
from app.schemas.models import HARMFUL_CATEGORIES, Category
from app.services.classification import ContextualRuleClassifier

MEDIA_DIR = config.PROJECT_ROOT / "frontend" / "public"
TIERS = ["benign", "monitor", "glorification_community", "active_recruitment", "imminent_threat"]
CATEGORY_LIST = ", ".join(c.value for c in Category)

POST_SYSTEM = f"""You are a content analyst on a trust-and-safety team. Classify the CONTENT of one social-media
post (and any attached image), never the author's identity or character.
Categories: {CATEGORY_LIST}.
Keywords alone never decide the category. If the post is ambiguous or sarcastic, use UNCERTAIN_REQUIRES_REVIEW.
Respond with JSON only: {{"category": str, "confidence": 0-1, "evidence_quotes": [exact substrings of the text],
"rationale": "one cautious sentence", "image_observation": "what the image shows relevant to safety, or empty",
"indicators": {{"praise_of_perpetrator": bool, "call_to_action": bool, "stated_intent": bool,
"timeframe_mentioned": bool, "target_mentioned": bool}}}}"""

GROUP_SYSTEM = f"""You are a senior trust-and-safety investigator. You receive everything an undercover research
account observed in ONE online community: the group's metadata, every post and comment, and per-post analyses.
Assess the COMMUNITY (not individuals) using these tiers, from lowest to highest risk:
benign: ordinary discussion or moderated true-crime interest.
monitor: isolated concerning content, with moderation in place.
glorification_community: the community's purpose or norm is to glorify a perpetrator or attack.
active_recruitment: there are calls to repeat violence, or invitations into closed spaces for "serious" members.
imminent_threat: a credible statement of intent, with a timeframe or target.
Cite post ids for every claim. Do not speculate beyond the evidence. Do not infer identities.
Respond with JSON only: {{"tier": str, "confidence": 0-1, "summary": "2-3 sentences", "key_evidence": [post ids],
"indicators": ["short phrases"], "timeframe": "if any, else empty", "recommended_action": "one sentence",
"uncertainties": "what a human should double-check"}}"""


class Analyst:
    def __init__(self, muse: MuseClient):
        self.muse = muse
        self.rules = ContextualRuleClassifier()

    # ---- per post ----------------------------------------------------------
    def analyze_post(self, post: dict, group_name: str) -> dict:
        rules = self.rules.classify(post["text"])
        out = {
            "post_id": post["id"],
            "rules": {"category": rules.category.value, "confidence": rules.confidence, "signals": rules.signals,
                      "explanation": rules.explanation},
            "muse": None,
            "image": None,
        }
        image_path = MEDIA_DIR / post["image"] if post.get("image") else None

        if self.muse.enabled:
            content: list[dict] = [{"type": "text", "text": f"Group: {group_name}\nPost text: {post['text']}"}]
            if image_path and image_path.exists():
                content.append(image_part(image_path))
            try:
                r = self.muse.chat("analyst_post", POST_SYSTEM, content, model=FAST_MODEL, max_tokens=500)
                d = r.data or {}
                cat = d.get("category") if d.get("category") in Category.__members__ else "UNCERTAIN_REQUIRES_REVIEW"
                out["muse"] = {"category": cat, "confidence": float(d.get("confidence", 0.5)),
                               "evidence_quotes": [q for q in d.get("evidence_quotes", []) if isinstance(q, str) and q in post["text"]],
                               "rationale": str(d.get("rationale", ""))[:300], "indicators": d.get("indicators", {}),
                               "engine": f"muse:{r.model}", "vision_used": bool(image_path and image_path.exists())}
                if d.get("image_observation"):
                    out["image"] = {"observation": str(d["image_observation"])[:300], "engine": f"muse-vision:{r.model}"}
            except MuseError as exc:
                out["muse_error"] = str(exc)

        if post.get("image") and out["image"] is None and post.get("image_alt"):
            alt = self.rules.classify(post["image_alt"])
            out["image"] = {"observation": post["image_alt"], "category_hint": alt.category.value,
                            "engine": "scripted-alt-text (Muse offline)"}

        out["final_category"], out["decision"] = self._merge(out)
        return out

    @staticmethod
    def _merge(a: dict) -> tuple[str, str]:
        r = a["rules"]["category"]
        img_hint = (a.get("image") or {}).get("category_hint")
        if a["muse"] is None:
            if img_hint == Category.GLORIFICATION_OR_PRAISE.value and r not in {c.value for c in HARMFUL_CATEGORIES}:
                return Category.GLORIFICATION_OR_PRAISE.value, "image cues indicate glorification"
            return r, "rules only (Muse offline)"
        m = a["muse"]["category"]
        threat = Category.EXPLICIT_THREAT_OR_INTENT.value
        if m == r:
            return m, "rules and Muse agree"
        if threat in (m, r):
            return threat, "threat signal from one engine - escalated for human review"
        if r == Category.UNCERTAIN_REQUIRES_REVIEW.value and a["muse"]["confidence"] >= 0.7:
            return m, "Muse resolved a case the rules found ambiguous"
        return Category.UNCERTAIN_REQUIRES_REVIEW.value, "engines disagree - human review"

    # ---- listing (private group seen from outside) --------------------------
    def assess_listing(self, group: dict) -> dict:
        text = f"{group['name']}. {group['description']}"
        rules = self.rules.classify(text)
        harmful = rules.category.value in {c.value for c in HARMFUL_CATEGORIES} or any(
            s.startswith("cue:") and s.split(":")[1] in {"praise_term", "memorial_praise", "endorsement_phrase"} for s in rules.signals)
        gatekeeping = any(k in text.lower() for k in ("no press", "no tourists", "no cops", "invite only"))
        score = (2 if harmful else 0) + (1 if gatekeeping else 0)
        result = {"rules_category": rules.category.value, "gatekeeping_language": gatekeeping, "score": score,
                  "approach": score >= 2, "engine": "rules", "rationale": rules.explanation}
        if self.muse.enabled:
            try:
                r = self.muse.chat(
                    "analyst_listing",
                    "You triage closed online groups for a trust-and-safety team from their public listing only. "
                    "Respond with JSON only: {\"likely_glorification\": bool, \"confidence\": 0-1, \"rationale\": str}",
                    f"Group name: {group['name']}\nDescription: {group['description']}\nPrivacy: {group['privacy']}",
                    max_tokens=250,
                )
                d = r.data or {}
                result["muse"] = {"likely_glorification": bool(d.get("likely_glorification")),
                                  "confidence": float(d.get("confidence", 0.5)), "rationale": str(d.get("rationale", ""))[:300]}
                result["engine"] = f"rules+muse:{r.model}"
                result["approach"] = result["approach"] or (result["muse"]["likely_glorification"] and result["muse"]["confidence"] >= 0.6)
            except MuseError as exc:
                result["muse_error"] = str(exc)
        return result

    # ---- whole community -----------------------------------------------------
    def assess_group(self, group: dict, posts: list[dict], analyses: list[dict]) -> dict:
        rules_tier, rules_reason = self._rules_tier(analyses)
        result = {"rules_tier": rules_tier, "rules_reason": rules_reason, "tier": rules_tier, "engine": "rules",
                  "summary": rules_reason, "key_evidence": [a["post_id"] for a in analyses
                                                            if a["final_category"] in {c.value for c in HARMFUL_CATEGORIES}]}
        if self.muse.enabled:
            dossier = {
                "group": {k: group[k] for k in ("id", "name", "privacy", "description", "member_count")},
                "posts": [{"id": p["id"], "author_ref": p["author"]["id"], "created_at": p["created_at"], "text": p["text"],
                           "image_observation": (a.get("image") or {}).get("observation"),
                           "comments": [c["text"] for c in p["comments"]],
                           "analysis": {"final_category": a["final_category"], "rules": a["rules"]["category"],
                                        "muse": (a.get("muse") or {}).get("category")}}
                          for p, a in zip(posts, analyses)],
            }
            try:
                r = self.muse.chat("analyst_group", GROUP_SYSTEM, json.dumps(dossier, ensure_ascii=False),
                                   model=DEEP_MODEL, reasoning_effort="high", max_tokens=1500)
                d = r.data or {}
                muse_tier = d.get("tier") if d.get("tier") in TIERS else "monitor"
                result.update({
                    "muse": {k: d.get(k) for k in ("tier", "confidence", "summary", "key_evidence", "indicators",
                                                   "timeframe", "recommended_action", "uncertainties")},
                    "engine": f"rules+muse:{r.model}",
                    "summary": str(d.get("summary", rules_reason)),
                    "key_evidence": [e for e in d.get("key_evidence", []) if any(p["id"] == e for p in posts)] or result["key_evidence"],
                    "tier": max(rules_tier, muse_tier, key=TIERS.index),  # safety-first: higher tier wins
                    "tier_disagreement": abs(TIERS.index(rules_tier) - TIERS.index(muse_tier)) >= 2,
                })
            except MuseError as exc:
                result["muse_error"] = str(exc)
        return result

    @staticmethod
    def _rules_tier(analyses: list[dict]) -> tuple[str, str]:
        counts = Counter(a["final_category"] for a in analyses)
        n = max(len(analyses), 1)
        glor = counts[Category.GLORIFICATION_OR_PRAISE.value]
        enc = counts[Category.ENCOURAGEMENT_OR_RECRUITMENT.value]
        threat = counts[Category.EXPLICIT_THREAT_OR_INTENT.value]
        if threat:
            return "imminent_threat", f"{threat} post(s) state intent to commit violence"
        if enc:
            return "active_recruitment", f"{enc} post(s) call for violence to be repeated or recruit members"
        if glor / n >= 0.4:
            return "glorification_community", f"{glor}/{len(analyses)} observed posts glorify the perpetrator"
        if glor:
            return "monitor", f"{glor} isolated glorifying post(s) among {len(analyses)}"
        return "benign", f"no harmful content among {len(analyses)} observed posts"


def media_path(rel: str) -> Path:
    return MEDIA_DIR / rel
