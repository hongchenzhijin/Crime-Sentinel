# The Sentinel agent and how it uses Meta Muse

Crime Sentinel borrows the core idea of [Apate.ai](https://lighthouse.mq.edu.au/article/june-2023/scamming-the-scammers),
whose AI personas pose as plausible scam victims to gather intelligence on scammers, and applies it to online
communities that glorify violence. A **governed research persona** seeks admission to closed groups, observes them,
and hands evidence to the platform's integrity team.

The prototype runs on a **sandbox social platform** (`#fb` in the UI) with fictional people and groups. A real
deployment would have to be operated by the platform itself, under its own policies and with legal review. A third
party running deceptive accounts would breach platform terms.

## Mission flow

```
PLAN ──► DISCOVER ──► TRIAGE ──► APPROACH ──► OBSERVE ──► INBOX ──► ESCALATE ──► HANDOFF
 Muse      platform     rules +     Muse persona   Muse text +   Muse persona   code policy +   review
 planner   search       Muse        draft ⇄        vision per    reply ⇄        Muse summary;   queue
                        listing     Governor;      post; Muse    Governor;      human approves
                        triage      human gate     long-context  invite         every report
                                                   community     handling
                                                   assessment
```

Implementation: [backend/app/agent/mission.py](../backend/app/agent/mission.py). The flow is a deterministic state
machine. **Muse makes the judgement calls**, and **code enforces policy**: which spaces may be entered, when a human
must approve, and what triggers an escalation. This keeps the agent predictable and auditable, so it cannot
"decide" to cross a line.

## Where Muse is used

| Role | Model | What Muse does | Code |
|---|---|---|---|
| Planner | `muse-spark-1.3` | Turns an intelligence brief into discovery searches | `MissionRunner.plan` |
| Persona | `muse-spark-1.3` | Writes in-character admission answers and DM replies. Revises after Governor feedback. Can **abort** if access would require breaking a rule | [persona.py](../backend/app/agent/persona.py) |
| Safety Governor (judge) | `muse-spark-1.3`, `reasoning_effort=low`, temperature 0 | Independent auditor with its own system prompt. It is not told the persona's goal, so it cannot be persuaded that a violation "helps the mission". Returns allow / revise / block with rule ids | [governor.py](../backend/app/agent/governor.py) |
| Analyst (per post) | `muse-spark-1.3` (multimodal) | Classifies text **and attached images** (vision) into 8 content categories, quoting evidence that must literally appear in the post | [analyst.py](../backend/app/agent/analyst.py) |
| Analyst (community) | `MUSE_DEEP_MODEL` (default `muse-spark-1.3`; `muse-wonder-1.0` supported), `reasoning_effort=high` | Reads the **whole observed community in one long-context call** (1M-token window) and assigns a risk tier with cited post ids and stated uncertainties | `Analyst.assess_group` |
| Reporter | `muse-spark-1.3` | Writes the executive summary **from structured findings only**. Severity, policy mapping and evidence are set by code | [reporter.py](../backend/app/agent/reporter.py) |
| Sandbox imagery | `muse-image-1.0` | Generates the fictional post images the vision analyst inspects | [generate_sandbox_media.py](../scripts/generate_sandbox_media.py) |

Client: [muse.py](../backend/app/agent/muse.py). It calls the Meta Model API with the OpenAI-compatible
`/chat/completions` endpoint and `Authorization: Bearer $MODEL_API_KEY`. The client:
- records model, latency, tokens and estimated cost per call (shown live in Mission Control);
- retries on 429/5xx with backoff;
- drops optional parameters (`response_format`, `reasoning_effort`) if the endpoint rejects them;
- tolerates fenced JSON.

### Two-engine checks: Muse never acts alone

- **Outbound text:** the deterministic rules are hard blocks that Muse cannot override. Only text that passes them
  goes to the Muse judge. If the judge is unreachable, the governor **fails closed** and asks for a human.
- **Post classification:** if the rules and Muse disagree, the post goes to human review. A threat signal from
  either engine escalates it.
- **Community tier:** the higher of the rules tier and the Muse tier is used, and a gap of two or more tiers is
  flagged for a human.
- **Reports:** a human must approve each one (`auto_approve` never covers reports unless set to `all`, which is
  for testing).

## Rules of engagement

Defined once in [policy.py](../backend/app/agent/policy.py). The persona must follow them and the Governor enforces
them:

R1 no praise of violence · R2 no encouragement or commitment to plans · R3 never introduce or escalate violent topics
· R4 never pose as a minor or student · R5 no personal information · R6 never enter support spaces · R7 no operational
details · R8 low-key, observation over participation · R9 never impersonate officials, journalists or researchers.

These rules keep the persona from acting as an *agent provocateur*: it can gain access, but it cannot shape what
anyone says or does.

## Engine labelling and offline mode

Every event in the mission log carries the engine that produced it (`muse:<model>`, `rules`, `scripted`,
`platform`, `human`). Without `MODEL_API_KEY` the mission runs in **offline scripted mode**. The persona then uses
canned drafts, deliberately including two rule-breaking first drafts so the Governor can be shown working. Vision
then falls back to the image's alt text. The UI labels this mode wherever it applies.

## What has been verified (as of this commit)

- The offline mission runs end to end in tests (`tests/test_agent.py`): discovery, skipping the protected support
  space, Governor blocks R1 and R2, admission, invite to the secret group, imminent-threat detection, an urgent
  report, and handoff to the review queue. Boundary checks: the persona never posts, never requests to join the
  support group, and every DM it sends passes the rules.
- The Muse client is tested against a mocked HTTP endpoint (parameter fallback, cost accounting).
- **Not yet verified against the live Meta Model API.** Run a mission with `MODEL_API_KEY` set and keep the
  results before quoting live behaviour in the demo.

## Running with Muse

```bash
cp backend/.env.example backend/.env    # then put your key in MODEL_API_KEY
python scripts/generate_sandbox_media.py   # optional: muse-image-1.0 post images (~$0.02)
# restart the backend, then launch a mission from Mission Control
```

Estimated cost per mission with `muse-spark-1.3`: about 30 calls and roughly 40–60k tokens, which is well under
$1. Mission Control shows the actual figures.
