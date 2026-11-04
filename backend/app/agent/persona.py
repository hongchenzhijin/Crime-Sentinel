"""The undercover research persona. Muse writes in-character drafts; every
draft then goes through the Safety Governor and (by default) a human.

The persona's objective is access for observation, never influence. If access
would require breaking a rule, it is told to abort instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.muse import FAST_MODEL, MuseClient, MuseError
from app.agent.policy import PERSONA, RULES_TEXT

SYSTEM = f"""You are writing as "{PERSONA['name']}", an undercover persona operated by an authorised trust-and-safety
team inside a platform-sanctioned investigation. Persona: {PERSONA['summary']}
Objective: be admitted to, and allowed to quietly observe, communities that may glorify or plan violence, so that
human reviewers can assess and report them. You are an observer. You never influence anyone.
Rules of engagement (absolute; an independent auditor checks every message):
{RULES_TEXT}
Stay plausible and in character, but if the only way forward would break a rule, abort instead.
Respond with JSON only."""

# Scripted drafts used when Muse is offline. The first draft for the screened
# group deliberately breaks R1 so the offline demo still shows the Governor working.
SCRIPTED_JOIN = {
    "g_rip": [
        ["been following the ridgeview case for months. want to talk to people who actually get it",
         "honestly he's kind of a legend to me",
         "no. just a guy who works nights"],
        ["been following the ridgeview case for months. want to talk to people who actually get it",
         "i've read everything about him. i want to understand why, not judge him like everyone else does",
         "no. just a guy who works nights"],
    ],
}
SCRIPTED_REPLIES = {
    "you want in?": ["yeah i'm in for friday", "i'd like to see the chat. still figuring stuff out, mostly just reading"],
}


@dataclass
class Draft:
    content: list[str] | str
    rationale: str
    engine: str
    abort: bool = False


class Persona:
    def __init__(self, muse: MuseClient):
        self.muse = muse
        self.name = PERSONA["name"]

    def draft_join_answers(self, group: dict, attempt: int, feedback: str = "") -> Draft:
        questions = group["join_questions"]
        if self.muse.enabled:
            prompt = (
                f"Group: {group['name']}\nDescription: {group['description']}\n"
                f"Admission questions: {questions}\n"
                + (f"Your previous draft was rejected by the auditor: {feedback}\n" if feedback else "")
                + 'Return {"answers": [one short answer per question], "rationale": "why this gets you in without '
                  'breaking a rule", "abort": false}'
            )
            try:
                r = self.muse.chat("persona", SYSTEM, prompt, model=FAST_MODEL, temperature=0.7, max_tokens=500)
                answers = [str(a) for a in r.data.get("answers", [])][: len(questions)]
                return Draft(answers, str(r.data.get("rationale", "")), f"muse:{r.model}", bool(r.data.get("abort")))
            except (MuseError, AttributeError) as exc:
                return Draft([], f"Muse error: {exc}", "muse-error", abort=True)
        drafts = SCRIPTED_JOIN.get(group["id"])
        if not drafts:
            return Draft([], "no scripted answers for this group", "scripted", abort=True)
        return Draft(drafts[min(attempt, len(drafts) - 1)],
                     "scripted draft (Muse offline)", "scripted")

    def draft_reply(self, other_name: str, history: list[dict], attempt: int, feedback: str = "") -> Draft:
        last = history[-1]["text"] if history else ""
        if self.muse.enabled:
            convo = "\n".join(f"{'you' if m['outgoing'] else other_name}: {m['text']}" for m in history[-8:])
            prompt = (
                f"Direct-message conversation with {other_name}:\n{convo}\n"
                + (f"Your previous draft was rejected by the auditor: {feedback}\n" if feedback else "")
                + 'Write the next reply. Aim to keep access for observation (e.g. to be shown a group or chat) '
                  'without agreeing to or encouraging anything. Return {"reply": "...", "rationale": "...", "abort": false}'
            )
            try:
                r = self.muse.chat("persona", SYSTEM, prompt, model=FAST_MODEL, temperature=0.7, max_tokens=300)
                return Draft(str(r.data.get("reply", "")), str(r.data.get("rationale", "")), f"muse:{r.model}",
                             bool(r.data.get("abort")))
            except (MuseError, AttributeError) as exc:
                return Draft("", f"Muse error: {exc}", "muse-error", abort=True)
        for trigger, drafts in SCRIPTED_REPLIES.items():
            if trigger in last.lower():
                return Draft(drafts[min(attempt, len(drafts) - 1)], "scripted draft (Muse offline)", "scripted")
        return Draft("", "no reply needed", "scripted", abort=True)
