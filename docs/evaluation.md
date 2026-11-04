# Evaluation

Run `python scripts/evaluate_classifier.py` (add `--json` for the full output). The same results are shown on the
Evaluation tab.

## Test set

`data/synthetic/labelled_eval_set.json`: **53 synthetic, hand-labelled items** (49 English, 4 Bahasa Malaysia). They
are worded differently from the demo-data templates and include deliberately hard cases: negated praise, reported
speech, harmless first-person plans, coded praise, and paraphrased calls to action.

| Label | n |
|---|---|
| News reporting | 8 |
| Academic / research | 7 |
| Prevention / support | 8 |
| Neutral discussion | 8 |
| Glorification / praise | 9 |
| Encouragement / recruitment | 5 |
| Explicit threat / intent | 4 |
| Uncertain – requires review | 4 |

## Results

| Model | Macro-F1 | Accuracy* | FP rate (non-harmful → harmful) | Harmful recall | Harmful routed to review |
|---|---|---|---|---|---|
| `sentinel-contextual-rules@0.1.0` | 0.79 | 0.79 | 0.0% (0/31) | 77.8% (14/18) | 1 |
| `keyword-baseline@0.1.0` | 0.11 | 0.21 | 45.2% (14/31) | 27.8% (5/18) | 0 |

\*Accuracy is shown only for completeness. Classes are imbalanced, so use the per-class metrics instead.

In the harm-binary view, an `UNCERTAIN` prediction is counted as **routed to human review**. It is neither a hit
nor a miss.

### Known failure cases (contextual classifier)

- **False negatives:** coded praise without cue terms (`"his aesthetic was unmatched…"`), gamified phrasing variants
  (`"still the highest score anyone got"`), and paraphrased calls to repeat (`"somebody needs to carry on his work"`).
- **Confusions within harmful categories:** `"planning to finish what he started at my campus"` is labelled
  encouragement instead of threat/intent, because the intent pattern requires an explicit first-person subject. It
  still gets urgent priority.
- **Conservative routing:** news and research that quote praise terms (`"fans are calling the killer a hero"`) can go
  to review instead of being labelled news or research. This is the intended trade-off.
- **Bahasa Malaysia:** all 4 items go to review (0% accuracy by design). The classifier is not validated for `ms`.

### Decision thresholds

- `MIN_CONFIDENCE = 0.45`: below this, the result is uncertain.
- `AMBIGUITY_RATIO = 0.75`: if the runner-up score is at least 75% of the top score *and* the two categories fall on
  different sides of the harm boundary, the result is uncertain.
- Confidence = top cue score / (total cue score + 0.8), capped at 0.97.

## Limitations

The test set is small and synthetic, and it was written by the team that wrote the cues, so these results are
**optimistic**. They will not transfer to real content, where slang, coded language, and sarcasm are far more
varied. A credible evaluation needs independently labelled, properly sampled data with inter-annotator agreement.
