"""Builds the report sent to the platform's integrity team.

Structure, policy mapping and severity are produced in code, so they are
deterministic and auditable. Muse only writes the executive summary, and only
from the structured findings.
"""

from __future__ import annotations

import json

from app.agent.muse import FAST_MODEL, MuseClient, MuseError

SEVERITY = {"imminent_threat": "urgent", "active_recruitment": "high", "glorification_community": "normal",
            "monitor": "low", "benign": "none"}
POLICIES = {
    "GLORIFICATION_OR_PRAISE": "Dangerous Organizations & Individuals: glorification of violent events/perpetrators",
    "ENCOURAGEMENT_OR_RECRUITMENT": "Violence & Incitement: calls to action; Dangerous Orgs: recruitment",
    "EXPLICIT_THREAT_OR_INTENT": "Violence & Incitement: statements of intent to commit violence",
}
ACTIONS = {
    "imminent_threat": "URGENT: route to the escalations team for credible-threat assessment. A human decides on any "
                       "law-enforcement referral under existing platform policy.",
    "active_recruitment": "Review the group and its admins for removal. Preserve evidence. Monitor linked closed spaces.",
    "glorification_community": "Review the group against glorification policy. Consider removal, or reduced "
                               "distribution with counter-speech resources.",
    "monitor": "Add to the watch list. Re-assess if activity increases.",
}


def build_report(muse: MuseClient, mission_id: str, group: dict, assessment: dict, analyses: list[dict],
                 posts: list[dict], access_path: list[dict]) -> dict:
    by_id = {p["id"]: p for p in posts}
    evidence = []
    for a in analyses:
        if a["post_id"] not in assessment["key_evidence"]:
            continue
        p = by_id[a["post_id"]]
        evidence.append({
            "post_id": p["id"], "account_id": p["author"]["id"], "created_at": p["created_at"], "text": p["text"],
            "category": a["final_category"], "policy": POLICIES.get(a["final_category"], "-"),
            "image_observation": (a.get("image") or {}).get("observation"), "decision_basis": a["decision"],
        })
    tier = assessment["tier"]
    report = {
        "mission_id": mission_id,
        "group": {k: group[k] for k in ("id", "name", "privacy", "member_count", "description")},
        "risk_tier": tier,
        "severity": SEVERITY[tier],
        "assessment_engine": assessment["engine"],
        "assessment_summary": assessment["summary"],
        "evidence": evidence,
        "recommended_action": ACTIONS.get(tier, "No action."),
        "access_path": access_path,
        "caveats": [
            "Content-level assessment of a sandbox community. It is not a determination about any person.",
            "Evidence was gathered by a governed research persona that did not post, praise, or encourage anything.",
        ],
    }
    report["executive_summary"], report["summary_engine"] = _summary(muse, report)
    return report


def _summary(muse: MuseClient, report: dict) -> tuple[str, str]:
    fallback = (f"{report['group']['name']} ({report['group']['privacy']}) was assessed as "
                f"{report['risk_tier'].replace('_', ' ')} on the basis of {len(report['evidence'])} cited posts. "
                f"{report['assessment_summary']}")
    if not muse.enabled:
        return fallback, "template"
    try:
        r = muse.chat(
            "reporter",
            "Write a concise executive summary (max 90 words) for a trust-and-safety escalation, using only the "
            "structured findings provided. Neutral, factual tone. Cite post ids. No speculation about identities. "
            'Respond with JSON only: {"summary": "..."}',
            json.dumps({k: report[k] for k in ("group", "risk_tier", "assessment_summary", "evidence")}, ensure_ascii=False),
            model=FAST_MODEL, max_tokens=300,
        )
        return str(r.data.get("summary", fallback)), f"muse:{r.model}"
    except (MuseError, AttributeError):
        return fallback, "template"
