# Project Sentinel --- Build Specification

> **Working title:** Project Sentinel\
> **Tagline:** Turning public social-media signals into earlier, safer
> intervention.\
> **Document purpose:** Product and engineering brief for Codex, Claude
> Code, or another coding agent to build a hackathon-ready MVP.

------------------------------------------------------------------------

## 1. Project overview

Project Sentinel is an AI-assisted social intelligence prototype
designed to help authorised safety researchers identify and understand
**publicly observable online communities that glorify, celebrate, or
encourage real-world violence**, with an initial research focus on True
Crime Communities (TCC).

The system should go beyond keyword matching. It analyses permitted
public content, classifies context, identifies recurring themes, and
visualises relationships between public posts and topics. It should help
a human reviewer understand emerging patterns without automatically
labelling real people as dangerous.

### Core problem

Basic keyword filters are easy to evade and often misunderstand context.
A post about a school attack could be journalism, academic research,
prevention advocacy, neutral discussion, glorification, or a credible
threat. Treating all of these alike creates false positives and can
suppress legitimate speech.

### Proposed solution

Build a controlled intelligence workflow that:

1.  Ingests a small, permitted dataset of public posts or synthetic
    research data.
2.  Detects potentially relevant content using a combination of keyword
    signals and contextual AI classification.
3.  Groups related content into themes or candidate communities.
4.  Maps relationships between posts, hashtags, topics, and **publicly
    observable** interactions.
5.  Prioritises items for human review using transparent evidence and
    calibrated risk indicators.
6.  Presents trends and evidence in an investigator-facing dashboard.

**Important product boundary:** The MVP is an analytical and
prevention-support tool, not an autonomous undercover agent. Do not
create deceptive personas, contact real TCC members, infiltrate private
groups, manipulate recommendation systems, or attempt to provoke users
into violent conversations. The original honeypot inspiration can be
discussed as a future research direction, but it is not part of this
MVP.

------------------------------------------------------------------------

## 2. Goals and non-goals

### MVP goals

-   Demonstrate contextual classification of TCC-related content.
-   Distinguish at least these categories:
    -   `NEWS_REPORTING`
    -   `ACADEMIC_OR_RESEARCH`
    -   `PREVENTION_OR_SUPPORT`
    -   `NEUTRAL_DISCUSSION`
    -   `GLORIFICATION_OR_PRAISE`
    -   `ENCOURAGEMENT_OR_RECRUITMENT`
    -   `EXPLICIT_THREAT_OR_INTENT`
    -   `UNCERTAIN_REQUIRES_REVIEW`
-   Show why a post received a category, including evidence spans and
    model confidence.
-   Visualise relationships between posts, hashtags, topics, and public
    community-level entities.
-   Show trends over time using dataset timestamps.
-   Support human review, correction, and feedback.
-   Clearly communicate uncertainty and avoid claiming that a person is
    dangerous based on a post or graph connection.

### Non-goals for the hackathon MVP

-   No automated contact, messaging, commenting, liking, following, or
    joining groups.
-   No fabricated identity or AI persona interacting with real users.
-   No access to private groups, private messages, restricted profiles,
    or non-public data.
-   No bypassing platform controls, rate limits, authentication, or API
    permissions.
-   No scraping that violates a platform's terms or access restrictions.
-   No facial recognition, identity resolution, doxxing, location
    inference, or deanonymisation.
-   No individual-level threat prediction or automated accusations.
-   No automatic reporting to police or school authorities.
-   No claim that the system can predict an attack or establish
    causation.

------------------------------------------------------------------------

## 3. Priority order

Build in this order. A convincing end-to-end workflow is more valuable
than many incomplete features.

  -----------------------------------------------------------------------
  Priority                Component               Required outcome
  ----------------------- ----------------------- -----------------------
  P0 --- Essential        Dataset and ingestion   Load synthetic or
                                                  explicitly permitted
                                                  public research data

  P0 --- Essential        Contextual              Classify content into
                          classification          the categories above,
                                                  with explanations and
                                                  uncertainty

  P0 --- Essential        Human-review workflow   Reviewer can inspect,
                                                  correct, and resolve
                                                  flagged items

  P0 --- Essential        Network visualisation   Display relationships
                                                  between public posts,
                                                  hashtags, and topics

  P0 --- Essential        Risk/trend dashboard    Show aggregate trends
                                                  and review priorities
                                                  without scoring
                                                  individuals

  P1 --- Important        Evidence and audit      Preserve source,
                          trail                   timestamp, model
                                                  version, rationale, and
                                                  reviewer action

  P1 --- Important        Search and filters      Filter by category,
                                                  date, topic,
                                                  confidence, and review
                                                  status

  P1 --- Important        Evaluation              Measure classification
                                                  quality and document
                                                  limitations

  P2 --- Stretch          Permitted live          Add only if platform
                          public-data connector   access and terms
                                                  clearly permit it

  P2 --- Stretch          Multilingual support    Evaluate English and
                                                  Bahasa Malaysia; add
                                                  other languages only
                                                  with suitable data

  P2 --- Stretch          Emerging-topic          Identify increases in
                          detection               public topic activity,
                                                  with minimum sample
                                                  thresholds

  P2 --- Stretch          Exportable research     Export aggregate
                          report                  findings and reviewed
                                                  evidence
  -----------------------------------------------------------------------

**Do not start with live Facebook integration.** Build the full workflow
against synthetic data first. A reliable demo should not depend on
access to a platform API, which may be unavailable or restricted.

------------------------------------------------------------------------

## 4. Suggested MVP user journey

1.  The reviewer opens the dashboard.
2.  The dashboard displays the dataset source, collection period, and
    whether the data is synthetic or real.
3.  The reviewer selects a topic or time period.
4.  Sentinel displays relevant posts and contextual classifications.
5.  The reviewer opens an item to inspect the text, category,
    confidence, evidence spans, and explanation.
6.  The reviewer confirms, changes, or marks the classification as
    uncertain.
7.  The network view shows how posts connect through shared hashtags or
    topics. It does **not** imply that every connected account belongs
    to a harmful group.
8.  The trends view shows aggregate changes over time.
9.  The reviewer can export a report containing aggregate statistics and
    selected, appropriately redacted examples.

------------------------------------------------------------------------

## 5. System architecture

Use a modular architecture. Keep ingestion, analysis, graph
construction, and presentation separate so that a permitted data source
can be added later without rewriting the application.

``` text
                    ┌──────────────────────────┐
                    │ Synthetic / permitted    │
                    │ public research dataset │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │ Data ingestion &         │
                    │ validation               │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │ Normalisation &          │
                    │ privacy minimisation     │
                    └────────────┬─────────────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
     ┌──────────────────────┐          ┌──────────────────────┐
     │ Keyword / phrase     │          │ Contextual text      │
     │ signals              │          │ classification       │
     └──────────┬───────────┘          └──────────┬───────────┘
                └────────────────┬────────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │ Evidence and uncertainty │
                    │ aggregation               │
                    └────────────┬─────────────┘
                                 │
                 ┌───────────────┼────────────────┐
                 ▼               ▼                ▼
        ┌──────────────┐ ┌──────────────┐ ┌────────────────┐
        │ Human review │ │ Topic / graph│ │ Aggregate trend│
        │ queue        │ │ construction │ │ calculations   │
        └──────┬───────┘ └──────┬───────┘ └───────┬────────┘
               └───────────────┼─────────────────┘
                               ▼
                    ┌──────────────────────────┐
                    │ Investigator dashboard  │
                    │ and audit log            │
                    └──────────────────────────┘
```

### Suggested technology stack

Choose familiar, hackathon-friendly tools and avoid unnecessary
infrastructure.

-   **Frontend:** React + TypeScript + Vite.
-   **UI:** Tailwind CSS and a consistent component library of your
    choice.
-   **Charts:** Recharts or another lightweight charting library.
-   **Network graph:** Cytoscape.js or React Flow. Use Cytoscape.js for
    graph exploration.
-   **Backend:** Python 3.11+ with FastAPI.
-   **Validation:** Pydantic.
-   **Storage:** SQLite for the MVP; PostgreSQL only if needed.
-   **Data processing:** pandas.
-   **NLP baseline:** scikit-learn TF-IDF baseline, followed by a
    suitable transformer or LLM classifier.
-   **Embeddings / clustering:** sentence-transformers and a clustering
    method only if they improve the demo.
-   **Testing:** pytest for backend; Vitest/React Testing Library for
    frontend.

If the team already has a preferred stack, retain it. The architecture
matters more than the exact libraries.

------------------------------------------------------------------------

## 6. Data model

Create a documented schema and validate all imported records.

### Post

``` json
{
  "id": "post_0001",
  "source_type": "synthetic",
  "source_name": "Sentinel Demo Dataset",
  "source_url": null,
  "published_at": "2026-10-01T12:00:00Z",
  "text": "Example post text for demonstration.",
  "language": "en",
  "hashtags": ["example_topic"],
  "public_topic_ids": ["topic_01"],
  "author_reference": null,
  "interaction_reference_ids": [],
  "is_synthetic": true
}
```

Do not store real account identifiers by default. If a permitted
research dataset contains identifiers, remove or pseudonymise them at
ingestion and document the reason for retaining any field. Do not
attempt to reverse pseudonyms.

### Classification

``` json
{
  "post_id": "post_0001",
  "category": "UNCERTAIN_REQUIRES_REVIEW",
  "confidence": 0.0,
  "evidence_spans": [],
  "explanation": "Short, cautious explanation based only on the post content.",
  "signals": ["keyword_signal"],
  "model_name": "baseline-classifier",
  "model_version": "0.1.0",
  "review_status": "pending",
  "reviewer_category": null,
  "reviewed_at": null
}
```

Confidence is model confidence, not the probability that a person is
dangerous. Keep these concepts separate in the UI and documentation.

### Graph entities and edges

Use community-level or content-level nodes, not real-person risk
profiles.

Suggested node types:

-   `POST`
-   `HASHTAG`
-   `TOPIC`
-   `PUBLIC_COMMUNITY_REFERENCE` (only where the source is permitted and
    the entity is genuinely public)

Suggested edge types:

-   `USES_HASHTAG`
-   `MENTIONS_TOPIC`
-   `SIMILAR_CONTENT`
-   `PUBLICLY_LINKED_TO`

Every edge should include provenance and a description of how it was
created. A shared hashtag or semantic similarity is not proof of
membership, coordination, endorsement, or intent.

------------------------------------------------------------------------

## 7. Classification design

### Use a layered approach

1.  **Baseline signals:** Known terms, phrase patterns, and hashtags.
    These are discovery signals, not final decisions.
2.  **Contextual classifier:** Classify the meaning and intent expressed
    in the post, considering the surrounding text supplied by the
    dataset where permitted.
3.  **Uncertainty handling:** If the model is unsure, the content is
    ambiguous, or categories overlap, return
    `UNCERTAIN_REQUIRES_REVIEW`.
4.  **Human review:** A reviewer makes the final decision for any
    high-impact interpretation.
5.  **Feedback loop:** Store reviewer corrections to evaluate and
    improve the classifier. Do not silently retrain on reviewer
    decisions.

### Classification principles

-   Separate neutral discussion from praise or encouragement.
-   Do not infer intent from keywords alone.
-   Do not infer a user's beliefs or risk level from a single post.
-   Do not treat following, liking, or sharing as proof of endorsement.
-   Include a short rationale and relevant text evidence.
-   Make uncertainty visible.
-   Do not generate graphic descriptions or reproduce unnecessary
    violent material in the UI.
-   Do not use model-generated explanations as proof; show the original
    permitted evidence alongside them.

### Evaluation

Create a small, manually labelled test set. Report:

-   Precision, recall, and F1 by category.
-   Confusion matrix.
-   False-positive examples, especially news, research, and prevention
    content.
-   False-negative examples, where harmful glorification or
    encouragement was missed.
-   Performance by language, if multilingual classification is
    attempted.

Do not report only overall accuracy; class imbalance can make it
misleading. Clearly label the dataset size and limitations.

------------------------------------------------------------------------

## 8. Community and network analysis

The network graph is a central demo feature, but it must be interpreted
carefully.

### What to visualise

-   Posts connected by shared public hashtags.
-   Posts connected by shared topics.
-   Similar public content clusters.
-   Aggregate activity by topic over time.
-   Public community references only when obtained through a permitted
    source.

### What not to claim

-   Do not label a connected set of accounts as a TCC group solely
    because they share a hashtag.
-   Do not infer private membership or hidden relationships.
-   Do not infer coordination from graph proximity.
-   Do not rank individual users by dangerousness.
-   Do not display personal contact details or inferred identities.

### Suggested graph interactions

-   Click a topic node to filter related posts.
-   Click a hashtag node to inspect its public usage in the dataset.
-   Click a post node to open its evidence panel.
-   Toggle edge types.
-   Filter by date range and classification category.
-   Show the source and method behind each connection.

Add an always-visible note: **"Connections indicate observed content
relationships in this dataset; they do not establish membership,
coordination, or intent."**

------------------------------------------------------------------------

## 9. Risk and trend dashboard

The dashboard should prioritise **content and themes for review**, not
people.

Suggested indicators:

-   Number of posts by classification category.
-   Percentage awaiting human review.
-   Topic activity over time.
-   Number of posts with repeated glorification signals.
-   Number of explicit threat/intent items awaiting urgent human review.
-   Classification confidence distribution.
-   False-positive rate on the labelled evaluation set.

### Important safeguards

-   Use minimum sample thresholds before showing a trend.
-   Show the dataset time range and source.
-   Distinguish raw post volume from unique authors where author data is
    available and permitted.
-   Do not present a rise in discussion as proof of increased real-world
    danger.
-   Do not produce an individual "threat score".
-   Do not automatically send allegations or alerts to authorities.

For a demo, use synthetic data with a deliberately constructed timeline
so judges can see how an emerging topic appears. Clearly mark all such
data as synthetic.

------------------------------------------------------------------------

## 10. Challenges and mitigation

  -----------------------------------------------------------------------
  Challenge               Why it matters          MVP mitigation
  ----------------------- ----------------------- -----------------------
  Context and sarcasm     The same terms appear   Contextual
                          in reporting, research, classification plus
                          prevention, and         human review
                          glorification           

  Evasion and coded       Keyword lists become    Combine signals with
  language                outdated                semantic analysis; do
                                                  not claim complete
                                                  detection

  False positives         Legitimate speech may   Uncertainty category,
                          be misclassified        evidence display,
                                                  reviewer corrections

  False negatives         Harmful material may be Evaluate recall by
                          missed                  category and disclose
                                                  limitations

  Platform API            Facebook data access is Start with synthetic or
  restrictions            limited and             explicitly permitted
                          permission-dependent    datasets

  Private-group           Private spaces raise    No private-group access
  boundaries              privacy and safety      or infiltration
                          concerns                

  Minors and sensitive    TCC discussions may     Minimise data, avoid
  data                    involve minors and      identity collection,
                          vulnerable people       restrict access, set
                                                  retention limits

  Harmful exposure        Reviewers may encounter Content warnings,
                          disturbing content      text-only previews,
                                                  opt-in detail, reviewer
                                                  safety guidance

  Graph                   Shared hashtags do not  Label every edge with
  overinterpretation      prove membership or     its evidence and method
                          intent                  

  Model bias and language English-first models    Evaluate
  gaps                    may misread Bahasa      language-specific
                          Malaysia or slang       performance; use
                                                  uncertain status when
                                                  unsupported

  Data security           Research data can be    Local demo storage,
                          sensitive               access controls, no
                                                  unnecessary identifiers

  Legal and terms         Data collection may     Review applicable
  compliance              breach platform terms   platform terms and
                          or privacy law          Malaysian legal/privacy
                                                  requirements before
                                                  real-data collection
  -----------------------------------------------------------------------

### Privacy and safety requirements

-   Use synthetic data for the hackathon demo wherever possible.
-   Only use real data when its collection and use are clearly
    permitted.
-   Collect the minimum data needed for the stated research purpose.
-   Do not collect private messages, credentials, phone numbers, precise
    locations, or personal contact information.
-   Avoid storing account handles. If a dataset requires stable
    references, use non-reversible pseudonyms and keep no identity
    mapping.
-   Define a retention period and a deletion mechanism.
-   Restrict access to reviewers.
-   Keep an audit log of reviewer actions and data exports.
-   Do not expose raw sensitive content in public demo environments.
-   Do not use the system to contact, threaten, bait, or provoke people.
-   Do not make automated claims about a person's propensity for
    violence.

Before any real-world deployment, obtain appropriate legal, privacy,
platform-policy, and safeguarding review. This is a prototype, not a
validated threat-assessment system.

------------------------------------------------------------------------

## 11. Suggested repository structure

``` text
project-sentinel/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── data-dictionary.md
│   ├── safety-and-ethics.md
│   └── evaluation.md
├── data/
│   ├── synthetic/
│   └── README.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── ingestion.py
│   │   │   ├── classification.py
│   │   │   ├── graph.py
│   │   │   ├── trends.py
│   │   │   └── review.py
│   │   └── db/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── features/
│   │   │   ├── dashboard/
│   │   │   ├── review/
│   │   │   ├── network/
│   │   │   └── trends/
│   │   └── lib/
│   └── package.json
└── scripts/
    ├── generate_demo_data.py
    └── evaluate_classifier.py
```

Adjust this structure if the repository already exists. Do not overwrite
existing work without inspecting it first.

------------------------------------------------------------------------

## 12. API outline

Suggested FastAPI endpoints:

  Method   Endpoint                        Purpose
  -------- ------------------------------- -------------------------------------
  `GET`    `/api/health`                   Health check
  `GET`    `/api/dashboard/summary`        Aggregate dashboard metrics
  `GET`    `/api/posts`                    Paginated, filterable post list
  `GET`    `/api/posts/{post_id}`          Post and classification evidence
  `POST`   `/api/posts/{post_id}/review`   Save human review decision
  `GET`    `/api/network`                  Filtered content/topic graph
  `GET`    `/api/trends`                   Aggregate topic and category trends
  `GET`    `/api/evaluation`               Classifier evaluation metrics

Validate inputs, paginate list endpoints, and return clear errors. Do
not expose endpoints for automated social-media engagement or user
profiling.

------------------------------------------------------------------------

## 13. Hackathon demo plan

A strong demo should show a complete workflow in a few minutes.

### Demo sequence

1.  **Problem:** Keyword filters miss context and harmful communities
    can be distributed across many posts.
2.  **Dataset:** Load a clearly labelled synthetic dataset containing
    news, research, prevention, neutral discussion, glorification, and
    explicit threats.
3.  **Classification:** Show the same sensitive keyword appearing in
    different contexts and receiving different classifications.
4.  **Review:** Open a flagged item, inspect evidence, and correct an
    uncertain classification.
5.  **Network:** Explore a graph connecting public posts through topics
    and hashtags.
6.  **Trends:** Show an aggregate increase in a synthetic topic over
    time, with a clear caveat that this is not proof of real-world
    danger.
7.  **Impact:** Explain how an authorised safety team could use reviewed
    intelligence to improve moderation and prevention.

### Demo acceptance criteria

The MVP is ready to present when:

-   A fresh clone can be started using documented commands.
-   Synthetic data can be loaded with one command.
-   The dashboard renders without external platform credentials.
-   A user can filter and inspect posts.
-   Every classification displays its category, confidence, and
    rationale.
-   An uncertain item can be reviewed and corrected.
-   The graph is interactive and its edges have clear meanings.
-   Trends are calculated from the dataset rather than hardcoded.
-   Synthetic data is visibly labelled throughout the UI.
-   The README explains limitations, privacy safeguards, and evaluation
    results.

------------------------------------------------------------------------

## 14. Implementation milestones

### Milestone 1 --- Working skeleton

-   Inspect the repository and existing code before editing.
-   Set up backend and frontend.
-   Define schemas and seed synthetic data.
-   Implement health check and dataset loading.
-   Build a basic dashboard shell.

### Milestone 2 --- Intelligence pipeline

-   Implement keyword baseline.
-   Implement contextual classification interface.
-   Add uncertainty handling and evidence spans.
-   Add tests with contrasting examples.
-   Store model version and classification rationale.

### Milestone 3 --- Review and graph

-   Build review queue and correction flow.
-   Build graph API and interactive graph.
-   Add provenance for every node and edge.
-   Add date and category filters.

### Milestone 4 --- Trends and evaluation

-   Calculate aggregate trends.
-   Build evaluation script and labelled test set.
-   Display confusion matrix and per-class metrics.
-   Document failure cases and limitations.

### Milestone 5 --- Demo polish

-   Improve loading, empty, and error states.
-   Add privacy and synthetic-data labels.
-   Test from a clean environment.
-   Prepare the demo dataset and walkthrough.
-   Verify that no feature contacts real users or accesses restricted
    data.

------------------------------------------------------------------------

## 15. Instructions to the coding agent

Act as a senior full-stack engineer helping build a responsible
hackathon MVP.

1.  First inspect the existing repository, files, framework, and current
    implementation. Do not assume the repository is empty.
2.  Summarise the current state and propose a short implementation plan
    before making large changes.
3.  Implement the P0 features first. Do not spend time on live Facebook
    integration before the synthetic-data workflow works end to end.
4.  Prefer simple, maintainable code over unnecessary abstractions.
5.  Keep frontend and backend contracts explicit and typed.
6.  Add tests for classification edge cases, API validation, graph
    provenance, and trend calculations.
7.  Never invent real-world findings. Synthetic records and simulated
    trends must be labelled as such.
8.  Never add deceptive personas, automated engagement, private-group
    infiltration, identity resolution, or individual threat scoring.
9.  Do not silently treat model confidence as a real-world threat
    probability.
10. Keep a clear `README.md` with setup, run, test, architecture, demo,
    and limitations instructions.
11. If a requirement is ambiguous, choose the safest reasonable
    implementation and document the assumption.
12. After each milestone, report files changed, commands run, tests
    passed, known issues, and the next milestone.

### First task

Inspect the repository and implement **Milestone 1 --- Working
skeleton**. Before coding, report the detected stack and any existing
functionality that should be preserved. Then proceed with the smallest
coherent implementation that can load synthetic data and display a
working dashboard.
