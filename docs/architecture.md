# Architecture

```
data/synthetic/*.json
        │
        ▼
services/ingestion.py      validate (Pydantic PostIn) → minimise (redact, pseudonymise) → store
        │
        ▼
services/classification.py keyword signals ─┐
                           contextual cues ─┼→ uncertainty rules → ClassificationResult + review priority
                           (optional LLM)  ─┘
        │
        ▼
SQLite (db/database.py)    posts · classifications · topics · audit_log
        │
   ┌────┴──────────────┬─────────────────┬──────────────────┐
   ▼                   ▼                 ▼                  ▼
services/review.py  services/graph.py  services/trends.py  services/evaluation.py, report.py
   └────────────────────┴───────┬─────────┴──────────────────┘
                                ▼
                     api/routes.py (FastAPI, /api/*)
                                ▼
                frontend (React): Dashboard · Review · Network · Trends · Evaluation · Safety
```

## Design decisions

- **Separate layers.** Ingestion, classification, graph, trends, and presentation are independent modules.
  To add a permitted data source, write a function that produces `PostIn` dicts and call
  `ingest_records`. Nothing else changes.
- **Classifier interface.** Any object with `name`, `version`, and `classify(text, language) -> ClassificationResult`
  can be used. `get_classifier()` picks the LLM classifier if it is configured, otherwise the rule classifier.
- **Model output and human decisions are stored side by side.** `category`/`confidence` are never overwritten by
  reviews. `reviewer_category` holds the human decision, and the *effective* category (reviewer if present, else
  model) drives filters, the dashboard, and trends.
- **Computed, not hardcoded.** Dashboard, trend, emerging-topic, and evaluation numbers are recomputed from the
  database or test set on each request. Evaluation is cached per process because the test set is static.
- **SQLite + JSON columns.** This keeps the demo to one file. Filters use `json_each` for topic and hashtag
  membership.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check + loaded post count |
| GET | `/api/dataset` | Source, synthetic flag, period, retention |
| GET | `/api/topics` | Topic list |
| GET | `/api/dashboard/summary` | Aggregate metrics (accepts post filters) |
| GET | `/api/posts` | Paginated, filterable, sortable list |
| GET | `/api/posts/{id}` | Post + classification evidence |
| POST | `/api/posts/{id}/review` | Save a reviewer decision (`confirm` / `change` / `mark_uncertain`) |
| GET | `/api/posts/{id}/audit` | Audit entries for one post |
| GET | `/api/audit` | Recent audit log |
| GET | `/api/network` | Graph (filters + `edge_types`, `max_posts`) |
| GET | `/api/trends` | Category/topic series + emerging topics (`granularity=week|day`) |
| GET | `/api/evaluation` | Test-set metrics for both classifiers + reviewer feedback |
| GET | `/api/export/report` | Aggregate report with redacted examples (audited) |

Common post filters: `category`, `review_status`, `priority`, `topic_id`, `hashtag`, `date_from`, `date_to`,
`min_confidence`, `max_confidence`, `language`, `search`. Invalid values return `422`. Unknown posts return `404`.
There are deliberately no endpoints for engagement, messaging, or profiling, and a test enforces this.
