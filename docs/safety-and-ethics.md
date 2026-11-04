# Safety and ethics

Crime Sentinel has two parts:
- a **governed undercover research agent**, which runs only on the sandbox platform in this prototype;
- a **content-review console** for human reviewers.

It is a prevention-support prototype, **not** a threat-assessment system.

## Why an undercover persona, and why it is constrained

The highest-risk spaces are closed. In the sandbox you can see this directly: the gatekeeper rejects anyone who
says they are press, police or a researcher. Watching only public content misses the invite-only spaces where calls
to action and statements of intent appear. Apate.ai showed that AI personas can gather intelligence safely when
they are designed to *absorb* attention rather than cause harm.

The main ethical risk of a persona is that it acts as an **agent provocateur**: it could encourage, validate, or
co-create the behaviour it is meant to detect. Crime Sentinel is built so this cannot happen:

| Rule | Enforcement |
|---|---|
| R1 no praise of violence/perpetrators | Contextual classifier hard block + Muse judge |
| R2 no encouragement or commitment to plans | Regex for commitment language + classifier + Muse judge |
| R3 never introduce/escalate violent topics | Muse judge. The persona replies only to direct questions; there is no posting capability at all |
| R4 never pose as a minor or student | Regex hard block. The persona profile is an adult |
| R5 no personal information | Regex hard block |
| R6 never enter victim/survivor/support spaces | Protected-space flag + description heuristic. The mission skips them |
| R7 no operational details | Regex hard block |
| R8 observation over participation | Length limit. No reply unless asked a direct question |
| R9 never impersonate officials, press, researchers | Regex hard block |

Further safeguards:
- **Fail closed.** If the Muse judge is unavailable, human approval is required.
- **Humans in the loop.** Configurable approval for messages, joins and invites. Every report always requires
  approval, and reviewers can edit a message, but the edit must still pass the rules.
- **Full audit.** Every draft, verdict, approval, and platform action is logged with the engine that produced it.
  Approvals also go to the global audit log.
- **No reach beyond the platform.** No identity resolution or location inference, and no contact with police or
  schools. The recommended action on an imminent threat routes to the platform's own escalation team, where a human
  decides on any law-enforcement referral under existing policy.
- **The persona is registered.** The sandbox flags the persona account (`is_sentinel_persona`), modelling a
  platform-side registry so integrity teams never action their own research accounts.

## Content-level safeguards (review console)

| Risk | Mitigation |
|---|---|
| Keywords misread context | Keywords are discovery signals only. Contextual cues decide, with handling for negation and reported speech |
| Ambiguity, sarcasm, unsupported language | Routed to `UNCERTAIN_REQUIRES_REVIEW` |
| Model output treated as fact | Rationales are labelled "model-generated - not proof" and shown next to highlighted original text |
| Confidence mistaken for danger | "Model confidence, not a probability that anyone is dangerous" is shown wherever confidence appears |
| Graph over-interpretation | Always-visible disclaimer and per-edge provenance. No person nodes |
| Reviewer harm | Harmful text hidden behind a content warning, including rationales that quote it |
| Personal data | Redaction, one-way pseudonyms with no mapping, retention purge, delete-all |

## Before any real-world use

1. The platform itself would have to operate it, with Terms of Service, legal review (including Malaysia's PDPA and
   the law on undercover online investigation), and a safeguarding review, especially where minors may be present.
2. Independent red-teaming of the Governor against adversarial gatekeepers.
3. Evaluation on independently labelled real data, including Bahasa Malaysia.
4. A trained escalation team. No automated alerts to authorities.
