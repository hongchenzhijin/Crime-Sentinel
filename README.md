# Crime Sentinel

> A governed undercover AI agent, powered by Meta Muse, that finds the communities glorifying violence before they act.

The most dangerous True Crime Community (TCC) spaces are not public. They sit behind admission questions ("are you
a journalist?") and invite-only chats, where keyword filters and public scraping can't reach. Crime Sentinel applies
the [Apate.ai](https://lighthouse.mq.edu.au/article/june-2023/scamming-the-scammers) idea (AI personas that pose as
plausible scam victims to gather intelligence) to violent-extremism prevention:

1. A **research persona** written by **Meta Muse** passes the gatekeeper's questions of a closed group and is
   later invited into a secret chat.
2. An independent **Safety Governor** (hard rules plus a separate Muse judge) checks every message the persona
   wants to send. The persona never praises, encourages, commits to anything, or starts violent topics.
3. **Muse analyses** what the persona observes: post text and images (vision), then the whole community in one
   long-context call.
4. It drafts an **evidence-backed report to Meta Integrity**, and a human approves it before it is sent.
5. Observed posts flow into a **human review console** with explainable classification, a network graph, trends,
   and evaluation.

The demo runs on a **sandbox social platform** with fictional people and groups, because real-platform access was
not available. A real deployment would need to be operated by the platform itself. See
[docs/sentinel-agent.md](docs/sentinel-agent.md) for the architecture, every place Muse is used, and what has and
hasn't been verified.

**It assesses content and communities, never people.** No identity resolution, no individual threat scores, and no
automated reports to police or schools.

The original product brief is in [Project_Sentinel_Build_Spec.md](Project_Sentinel_Build_Spec.md) (old working
title). The agent extends that brief, and its persona boundaries replace the brief's "no personas" non-goal.

## Demo script: Sentinel agent (about 3 minutes)

1. Open **Mission Control** (the default tab). Show the intelligence brief and the engine panel (Muse connected,
   models, live cost).
2. **Launch mission.** The log streams: the Muse planner picks searches, and the persona finds 4 groups. The
   survivors' group is **skipped (R6)**.
3. Public groups are observed and assessed as benign or monitor. That contrast is the point.
4. Private group *rest in power r.*: the persona drafts admission answers and the **Safety Governor checks them**.
   In offline mode the first draft ("he's kind of a legend") is blocked under R1; with Muse, show whichever verdicts
   occur. The gatekeeper admits Alex.
5. In the sandbox pane (persona: private group), show the glorification feed and fan-edit image. The Analyst event
   shows the vision observation.
6. The gatekeeper DMs "you want in?". The persona's eager draft is **blocked (R2: commitment)** and replaced with a
   non-committal reply. The invite link arrives, and the persona joins the **secret group**.
7. A threat post is detected and the community is rated **IMMINENT THREAT**. An urgent report draft appears, and a
   human clicks **Approve & send to Meta Integrity**.
8. Switch the pane to **Meta Integrity inbox** to show the report, its evidence, and the recommended action. Then
   open the **Review queue** to see the observed posts ready for human confirmation.

Try it yourself: in the sandbox (`Open sandbox platform`), view as *Public visitor* and try to join
*rest in power r.* while saying you're a journalist. The gatekeeper declines you, which is exactly why an
undercover approach is needed.

---

## Quick start

Requirements: Python 3.11+ (tested on 3.12) and Node.js 20+ (tested on 24).

```bash
# 1. Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd ..

# 2. Load the synthetic demo dataset (one command: generate + validate + minimise + classify)
python scripts/load_demo_data.py

# 3. Run the API (http://127.0.0.1:8000, docs at /docs)
cd backend
uvicorn app.main:app --port 8000

# 4. Run the dashboard in a second terminal (http://localhost:5173)
cd frontend
npm install
npm run dev
```

The dashboard needs no platform credentials. Vite proxies `/api` to the backend on port 8000.

### Tests and evaluation

```bash
cd backend && python -m pytest          # 88 backend tests (offline; Muse is mocked)
cd frontend && npm test                 # frontend unit tests
cd frontend && npm run build            # type-check + production build
python scripts/evaluate_classifier.py   # per-class metrics, confusion matrix, FP/FN examples, multimodal (--fresh re-runs Muse)
python scripts/red_team.py              # AI red-team stress test (--regenerate writes a new set with Muse)
```

### Data management

```bash
python scripts/load_demo_data.py --no-generate     # reload the existing JSON without regenerating
python scripts/load_demo_data.py --purge-expired   # apply the retention policy (default 30 days)
python scripts/load_demo_data.py --delete-all      # delete everything stored
python scripts/generate_demo_data.py --seed 2      # regenerate data/synthetic/posts.json only
```

### Meta Muse (recommended)

```bash
cp backend/.env.example backend/.env       # put your Meta Model API key in MODEL_API_KEY
python scripts/generate_sandbox_media.py   # optional: generate post images with muse-image-1.0
python scripts/generate_dataset_media.py   # optional: regenerate dataset images, hash list and multimodal eval set
```

Restart the backend. Mission Control then shows "Meta Muse connected". Without a key, missions run in a clearly
labelled offline scripted mode, so the demo never depends on network access. Optional: `MUSE_DEEP_MODEL=muse-wonder-1.0`
for the long-context community assessment.

With a key set, the bulk dataset classifier also uses Muse (`muse-spark-1.3`, `reasoning_effort=minimal`), with the
contextual rules as a safety net: Muse's harm labels must quote the post, harm the rules find but Muse dismisses goes to
review, and unvalidated languages always go to review. Re-run `python scripts/load_demo_data.py --no-generate` to
reclassify (245 posts: about 30 s, ~$0.10). `CRIME_SENTINEL_CLASSIFIER=rules|muse|auto` (default `auto`) forces an
engine; the test suite pins `rules` so it never calls the API.

---

## What's in the MVP

| Area | What it does |
|---|---|
| **Ingestion** | Validates every record (Pydantic), rejects invalid ones with reasons, redacts emails/links/@handles/phone numbers, replaces author references with salted one-way pseudonyms (salt discarded after each load), and keeps only post-to-post interaction references. |
| **Classification** | Layered: keyword *discovery* signals → contextual cue patterns (with negation and reported-speech handling) → uncertainty rules (weak cues, cues that cross the harm boundary, unsupported language → `UNCERTAIN_REQUIRES_REVIEW`). Each result stores category, confidence, evidence spans, rationale, signals, per-category cue scores, model name/version, and review priority. |
| **Review queue** | Filter by category, topic, hashtag, review status, language, date range, confidence, or text. Harmful-category text is hidden behind a content warning. Evidence spans are highlighted in the original text. Reviewers can confirm, correct, or mark uncertain; the model's output is preserved alongside the decision; every action is audited. |
| **Images: PDQ + vision** | Every attached image is hashed with Meta's open-source **PDQ** perceptual hash (locally) and matched against a simulated industry hash list; matches route posts to human review but never make them harmful alone. **Muse vision** describes each image, reads text in it (which the rules engine also checks) and classifies text + image together. |
| **Intelligence (GraphRAG)** | Posts are linked by meaning (local **multilingual embeddings**), re-shared images, distinctive hashtags and replies, then clustered with **Louvain**. Muse writes a report per community (rules and Muse risk levels side by side) and answers analyst questions with **verified citations**; identity questions are refused. Includes multilingual semantic search. |
| **Network** | Cytoscape graph of posts, hashtags, and topics with toggleable edge types (`USES_HASHTAG`, `MENTIONS_TOPIC`, `SIMILAR_CONTENT` (semantic), `PUBLICLY_LINKED_TO`, `SHARES_IMAGE` (PDQ)); posts can be coloured by GraphRAG community. Every edge records its method and provenance. No person nodes. The disclaimer is always visible. |
| **Trends** | Weekly/daily volume by category and per-topic small multiples, computed from the data. Buckets below the minimum sample size (5) withhold breakdowns. Emerging-topic check compares the last 14 days with the 14 days before (≥10 recent posts and ≥2× growth). |
| **Dashboard** | Aggregate content indicators: category counts, % awaiting review, urgent items, repeated-glorification signals, confidence distribution, eval-set false-positive rate. |
| **Evaluation** | Per-class precision/recall/F1, confusion matrix, false-positive/false-negative examples, per-language results, compared against a naive keyword baseline, plus live reviewer-agreement stats. A multimodal set where the image changes the meaning, an **AI red-team** stress test per evasion tactic, and a **learning loop** that reclassifies with reviewer decisions as similarity-retrieved few-shot examples (no retraining, reviews untouched). |
| **Export & audit** | JSON report with aggregates and redacted reviewed examples (harmful-category text withheld). Ingestion, reviews, and exports are recorded in the audit log. |

## Demo walkthrough: review console (about 5 minutes)

1. **Problem.** On the Evaluation tab, the keyword baseline flags 45% of news, research, and prevention posts as
   harmful.
2. **Dataset.** The banner on every page shows the source, period, post count, and the **SYNTHETIC** label.
3. **Same keyword, different context.** In the Review queue, search for `attack`. The same word appears in news
   reporting, research, prevention, glorification, and uncertain items. Open a few to compare the highlighted cues
   (solid underline) with the keyword (dotted underline, a discovery signal only).
4. **Review.** Filter to *Uncertain – requires review*, open an item, and correct it. The audit trail updates, and
   the Dashboard's "after review" column and the Evaluation tab's reviewer agreement reflect the change.
5. **Network.** Click the *Anniversary countdown trend* topic node, then *Filter graph to topic*. Click any edge to
   see how it was created. Toggle *Similar content* edges on.
6. **Trends.** The anniversary-countdown topic rises sharply in the last three weeks and is flagged as
   *Emerging (simulated)*. Note the caveat: more discussion is not evidence of real-world danger.
7. **Impact.** An authorised trust-and-safety team could use reviewed, aggregate intelligence to prioritise
   moderation and counter-messaging. Use **Export report** to download it.

## Evaluation results (synthetic, n = 53)

| Model | Macro-F1 | False-positive rate (non-harmful flagged harmful) | Harmful recall |
|---|---|---|---|
| Meta Muse `muse-spark-1.3` + rules safety net (live runs, 2026-11-03, ~$0.09 each) | 0.77–0.84 (varies by run) | 0.0% (0/31) every run | 83.3% (+3 routed to review, 0 missed) every run |
| Contextual rule classifier | 0.79 | 0.0% (0/31) | 77.8% (+1 routed to review) |
| Keyword baseline | 0.11 | 45.2% (14/31) | 27.8% |

The contextual classifier misses coded praise ("his aesthetic was unmatched") and paraphrased calls to action
("somebody needs to carry on his work"). All 4 Bahasa Malaysia items go to human review by design. **These numbers
are optimistic**: the test set is small and synthetic, and it was written by the same team that wrote the cues. See
[docs/evaluation.md](docs/evaluation.md).

Images (10 items where the image changes the meaning): rules + PDQ 20% exact, Muse text-only 0% (all routed to
review), **Muse vision 70% exact with 0 harmful missed and 0 benign flagged**. AI red team (42 Muse-generated,
unverified adversarial posts): evasion rate keyword baseline 62%, rules 62%, Muse 0%. The Muse figure is flattered
because the same model family wrote and judged the posts. Details: [docs/ai-capabilities.md](docs/ai-capabilities.md).

## Limitations

- The rule-based classifier will miss new slang, coded language, and sarcasm, and cannot claim complete detection.
- Only English is validated. Muse classifies other languages, but its label is kept as a suggestion and the post always goes to review.
- PDQ does not survive crops (a 6% crop already breaks the match); vision covers some of that gap.
- GraphRAG summaries, vision descriptions and answers are model-generated. Citations are checked, but the content of
  a summary is not proof. The red-team labels are unverified.
- The demo has a single local reviewer identity and no authentication. Deploying with real data would require
  access control.
- The trend timeline is deliberately constructed, and the generator seed was chosen so that only the constructed
  topic crosses the emerging threshold (with other seeds, random noise can also cross it).
- This is a prototype, **not a validated threat-assessment system**. Before any real-world use, it needs legal,
  privacy (including Malaysian PDPA), platform-policy, and safeguarding review.

## Repository layout

```
backend/app/        FastAPI app: api/, schemas/, services/ (ingestion, classification, graph, trends, review,
                    evaluation, report), db/
backend/tests/      pytest suite
frontend/src/       React + TypeScript + Vite + Tailwind; features/{dashboard,review,network,trends,evaluation}
data/synthetic/     posts.json, topics.json (generated), labelled_eval_set.json (hand-labelled)
scripts/            generate_demo_data.py, load_demo_data.py, evaluate_classifier.py
docs/               architecture, data dictionary, safety & ethics, evaluation
```

See [docs/architecture.md](docs/architecture.md), [docs/data-dictionary.md](docs/data-dictionary.md), and
[docs/safety-and-ethics.md](docs/safety-and-ethics.md).
