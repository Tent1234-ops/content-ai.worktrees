# Laptop / Unknown Development Protocol

This extends the completed scope-holdout correction at the user's request.
The registered holdout plan and labels stay unchanged. Dataset 25 (a laptop
stand review labeled Laptop) is a review candidate, not silently relabeled.

## Development Only

- Query known Train/Validation and Unknown Validation explicitly in SQL.
  Never load Test transcripts in the development runner.
- Train classifiers and vocabulary on known Train only. Select C from
  0.5, 1, 2, 4 using five-fold channel-grouped CV, not Validation or Test.
- Compare existing word/character features with normalized Thai character
  features and PyThaiNLP word + normalized character features. Do not add
  category dictionaries, product-name overrides, or title-based predictions.
- Keep confidence >= 0.6 and quality gates >= 0.8. Validation selects the
  rejection policy only; it is development evidence, not an unbiased test.
- Start with existing scope v1. If feature normalization also needs to be
  applied to similarity, record a new policy version and preserve old artifact
  behavior. Any additional experiments must be logged, not hidden.
- No data edits, model registration, activation, or Test evaluation during
  these experiments. Do not force a pass. Record every candidate, including
  failures, per-row validation outcomes, and the exact configuration.

## After Development

Freeze one configuration before a separate acceptance run. A failed candidate
does not authorize switching to a Test-selected alternative. Keep the current
active model unless the existing complete promotion gates pass. Reused internal
Test is not new external evidence. No claim that classification confidence
proves recommendations improve engagement.

## Scope v2 Experiment (Declared Before Its Evaluation)

Use the same Thai whitespace normalization for the Train-only similarity
vocabulary. Require both absolute support and a contrast margin: best cosine
similarity to the predicted class minus best cosine similarity to another
known class. Select from the existing 0..0.95 step-0.05 support grid and margin
0, 0.05, 0.10 on all 40 Validation examples; confidence remains 0.6. This adds
60 calibration candidates, not 60 classifier fits. Report all candidates.
The margin is a rejection check only, never a replacement class prediction.
Ten Unknown Validation examples are a small calibration set; do not claim
generalization from it. Old v1 artifacts must retain their original behavior.

## Bounded Hybrid Experiment

The first three lexical candidates failed Validation, including Laptop raw
recall <= 0.6. The previously fitted embedding model recognizes the Laptop
examples but misses Phone examples. Next compare a single feature-concatenation
family: normalized Thai word/character TF-IDF plus the existing frozen local
multilingual MiniLM document embeddings. Equal feature-block weights, no class
override. Select logistic C from 0.5, 1, 2, 4, 8, 16 using grouped Train CV.
Encode fixed pretrained embeddings once for efficiency; fit TF-IDF separately
inside every CV training fold. No validation vocabulary fitting. Calibrate both
v1/v2 rejection on Validation and report failures as well as successes. Stop
this development batch after that comparison; no Test-based iteration.
