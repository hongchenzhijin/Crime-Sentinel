# Data dictionary

## Post (input record, `data/synthetic/posts.json`)

| Field | Type | Notes |
|---|---|---|
| `id` | string | `[A-Za-z0-9_-]`, unique. |
| `source_type` | `synthetic` \| `permitted_research` | Must agree with `is_synthetic`. |
| `source_name` | string | Shown in the UI banner. |
| `source_url` | string \| null | Dropped for synthetic records. |
| `published_at` | ISO-8601 datetime | Used for trends and filters. |
| `text` | string (1–5000) | Redacted at ingestion: emails, links, `@handles`, and phone numbers are replaced. |
| `language` | string | ISO code. Only `en` is classified; anything else is routed to review. |
| `hashtags` | string[] | Normalised: lower-case, no `#`, de-duplicated. |
| `public_topic_ids` | string[] | References `topics.json`. |
| `author_reference` | string \| null | **Replaced at ingestion** with `anon_<hash>`, a salted SHA-256 whose salt exists only in memory for one load. Pseudonyms are stable within a load, cannot be reversed, and cannot be linked across loads. Kept only so trends can tell raw volume from unique contributors. |
| `interaction_reference_ids` | string[] | Content-level references to other **posts** (public replies/quotes). Values that do not look like a post id (e.g. account ids) are dropped. |
| `is_synthetic` | bool | |
| `_generator_kind` | string | Generator-only metadata naming the template family. Ignored at ingestion. **Not** a gold label. |

## Classification (stored per post)

| Field | Notes |
|---|---|
| `category` | Model output. One of the eight categories below. Never overwritten by review. |
| `confidence` | 0–1 **model confidence in the category**. Not a probability that anyone is dangerous. |
| `evidence_spans` | `{start, end, text, cue_category, note}`. `cue_category = KEYWORD_SIGNAL` marks discovery keywords. |
| `explanation` | Short, cautious rationale built from the matched cues. |
| `signals` | e.g. `keyword:attack`, `cue:praise_term`, `negated_cue`, `reported_speech`, `repeated_glorification_cues`, `unsupported_language`. |
| `category_scores` | Summed cue weights per category, for transparency. |
| `model_name`, `model_version`, `classified_at` | Provenance. |
| `review_status` | `pending` · `confirmed` · `corrected` · `marked_uncertain`. |
| `review_priority` | `urgent` (any threat/intent cue) · `high` · `normal` · `low`. Derived from content only. |
| `reviewer_category`, `reviewer_note`, `reviewed_at` | Human decision. |

### Categories

`NEWS_REPORTING`, `ACADEMIC_OR_RESEARCH`, `PREVENTION_OR_SUPPORT`, `NEUTRAL_DISCUSSION`, `GLORIFICATION_OR_PRAISE`,
`ENCOURAGEMENT_OR_RECRUITMENT`, `EXPLICIT_THREAT_OR_INTENT`, `UNCERTAIN_REQUIRES_REVIEW`.
"Harmful content" in aggregate metrics means the glorification, encouragement, and threat categories.

## Graph

Node types: `POST` (label = post id, never text), `HASHTAG`, `TOPIC`. `PUBLIC_COMMUNITY_REFERENCE` is reserved for
permitted sources and unused in the demo. There are no person nodes.

| Edge | Method | Meaning |
|---|---|---|
| `USES_HASHTAG` | `metadata:hashtags` | The post lists the hashtag. |
| `MENTIONS_TOPIC` | `metadata:public_topic_ids` | The dataset tags the post with the topic. |
| `SIMILAR_CONTENT` | `jaccard_word_overlap` | Word-overlap ≥ 0.3 (top 2 per post). |
| `PUBLICLY_LINKED_TO` | `metadata:interaction_reference_ids` | The post publicly replies to or quotes another post. |

None of these edges is evidence of membership, coordination, endorsement, or intent.

## Audit log

`timestamp`, `actor`, `action` (`ingest_dataset`, `review_confirm`, `review_change`, `review_mark_uncertain`,
`export_report`, `purge_expired`), `post_id`, `details` (JSON: before/after categories, model version, note).

## Retention

`CRIME_SENTINEL_RETENTION_DAYS` (default 30). `scripts/load_demo_data.py --purge-expired` deletes posts ingested
before the cut-off. `--delete-all` removes everything.
