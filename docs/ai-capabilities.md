# AI capabilities: PDQ, vision, embeddings, GraphRAG, learning loop, red-teaming

Every capability follows the project's rule that **AI judges, code enforces, humans decide**: a model's output is
always cross-checked by a second engine, disagreements go to a human, and nothing here classifies or profiles people.

| Capability | Technology | Runs | Code |
|---|---|---|---|
| Known-image matching | **PDQ** perceptual hash (Meta, open source) via `pdqhash` | locally, offline | [media.py](../backend/app/services/media.py) |
| Image understanding + OCR | **Meta Muse vision** (`muse-spark-1.3`) | Meta Model API | [classification.py](../backend/app/services/classification.py) |
| Semantic similarity & search | **fastembed** multilingual MiniLM (ONNX) | locally, offline after first download | [embeddings.py](../backend/app/services/embeddings.py) |
| Community intelligence | **GraphRAG**: networkx Louvain + Muse summaries + cited Q&A | local graph, Muse text | [graphrag.py](../backend/app/services/graphrag.py) |
| Learning from reviewers | retrieval-augmented **few-shot** prompting | Muse | [learning.py](../backend/app/services/learning.py) |
| Adversarial testing | Muse-generated **red-team** set, scored per tactic | Muse | [redteam.py](../backend/app/services/redteam.py) |

## 1. PDQ hash matching

Meta's [PDQ](https://github.com/facebook/ThreatExchange/tree/main/pdq) is the hash format used by industry
hash-sharing programmes for known terrorist and violent-extremist imagery. Every attached image is hashed at
ingestion (256 bits) and compared with a **simulated hash list** (`data/synthetic/hashlist.json`) holding all 8
rotations/flips of two "known" synthetic images. The originals are never served; only hashes are listed.

- Match = Hamming distance ≤ 31 (Meta's recommended threshold). Measured on the synthetic re-uploads: re-compressed,
  recoloured, shrunk and mirrored copies match at distance 0–2, captioned copies at 20–30, and unrelated images sit
  at 102–124. **Crops evade PDQ** (6% crop → distance 92–108), which is PDQ's known weakness; Muse vision covers it.
- A match **never makes a post harmful by itself** (a news post can show the same picture). If the classifier did
  not find harm, the post becomes `UNCERTAIN_REQUIRES_REVIEW` with at least `high` priority.
- The graph gets `SHARES_IMAGE` edges between posts re-sharing the same picture.

## 2. Vision

Posts with images are sent to Muse as text + downscaled JPEG. Muse classifies the post as a whole and returns an
image description, any text visible in the image, and the visual evidence for a harmful reading.

- **Two engines on images too:** the text Muse reads off an image (OCR) is run through the rule classifier. If the
  rules find harm Muse dismissed, the post goes to review.
- Harm may rest on visual evidence instead of a text quote, but it is flagged `visual_evidence_only`.
- Multimodal eval (10 hand-labelled items where the image changes the meaning, e.g. the same caption on a victims'
  vigil vs a shrine to the attacker): rules + PDQ 20% exact, Muse text-only 0% (it correctly routes everything to
  review), **Muse vision 70% exact, 0 harmful items missed, 0 benign items flagged**. Ten items is far too few for
  accuracy claims.

## 3. Embeddings

The Meta Model API has no embeddings model, so `paraphrase-multilingual-MiniLM-L12-v2` runs locally through
fastembed (ONNX, CPU; ~220 MB downloaded once into `backend/.cache/`). Vectors are stored per post. They power
`SIMILAR_CONTENT` edges (cosine ≥ 0.72), semantic search (`GET /api/search/semantic`), GraphRAG retrieval and
few-shot example selection. The model is multilingual: a Bahasa Malaysia "don't share the attack video, remember the
victims" post sits next to the English "Don't share fan edits… say the victims' names" (0.70). If fastembed is
unavailable, a hashed bag-of-words embedder is used and labelled as such.

## 4. GraphRAG

1. **Graph of posts** weighted by meaning (top-5 semantic neighbours), the same image (PDQ), distinctive hashtags
   (shared by ≤ 25% of posts, IDF-weighted) and public replies.
2. **Louvain communities** (networkx, fixed seed). On the demo data: 8 communities covering 243 of 245 posts.
3. **Community reports:** computed statistics (category mix, harmful share, 14-day trend, images, hash-list matches)
   plus a Muse title, summary, themes, trajectory and cited post ids (checked against the sample Muse saw). A rule
   risk level is computed from the statistics; the higher of rules/Muse is shown and a gap of ≥ 2 levels is flagged.
4. **Ask:** global context (all community reports) + local context (12 posts retrieved by semantic search). Citations
   like `[c03]` and `[post_0123]` are verified; citations to anything Muse was not shown are removed and reported.
   Questions about identities (real names, addresses, "who are the authors") are refused by policy before any model
   call, and every question is written to the audit log.

## 5. Learning loop

Confirmed and corrected reviews become examples. For each post, the 4 most similar reviewed posts (by embedding) are
shown to Muse; a post never sees its own label. **Reclassify with reviewer feedback** (Evaluation tab or
`POST /api/learning/reclassify`) replaces only model outputs; reviewer decisions are untouched and the before/after
transitions are audited. Nothing is fine-tuned. Agreement on reviewed posts is optimistic because templated
duplicates exist, and hash-list policy still overrides examples.

## 6. Red-teaming

`python scripts/red_team.py --regenerate` has Muse write adversarial posts for 8 tactics (coded praise, leetspeak,
paraphrased calls to action, euphemistic countdowns, reported-speech traps, counter-speech with loaded words, news
with loaded words, Malaysian code-switching), using only the fictional cases and filtered with the Safety Governor's
operational-detail and personal-information checks. Results on the generated set (42 items):

| Classifier | Evasion rate | False-alarm rate |
|---|---|---|
| Keyword baseline | 62% | 83% |
| Contextual rules | 62% | 22% |
| Muse + rules | 0% | 0% |

**Treat the Muse row with suspicion:** the labels are the generator's intent (unverified), and the same model family
wrote and judged the posts. The value of this test is the per-tactic breakdown of where the rules fail.

## Cost and reproducibility (live, 2026-11-03)

Full load (245 posts incl. 41 images, embeddings, 8 community summaries): ~96 s, ~$0.23. Evaluation (53 text + 10
multimodal items): ~45 s, ~$0.10, cached in `backend/.cache/evaluation.json` until eval sets, prompts or models
change (`--fresh` forces a re-run). Muse results vary between runs even at temperature 0: macro-F1 on the text set
ranged 0.77–0.84 across runs, while 0 false positives and 0 missed harmful items held in every run.
