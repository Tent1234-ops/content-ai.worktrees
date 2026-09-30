# Phase 1: Classification Acceptance and Unknown

## Current State (2026-09-27)

This phase delivers a rejection mechanism and regression evidence, not a newly
validated classifier. No new independent test clips or audio-verified transcripts
were supplied. No production model was trained, activated, or relabeled.

Active model 14 still predicts Phone for all four previously evaluated clips,
including the headphone, keyboard and mouse cases. Its confidence is approximately
97-99%, but it has no validation-selected scope policy. High confidence among three
known labels is not evidence that an input belongs to any of those labels.

**Strict mode now withholds category-specific recommendations for this legacy
model on every new analysis, including a genuine Phone clip.** Transcripts and
observed keywords remain available. Raw classification and its confidence are
retained separately, under the expandable raw-prediction section. Existing saved
results are not rewritten. This must not be presented as improved Unknown recall.

Read-only audit: 154 eligible in-scope rows, split into 116 train, 21 validation
and 17 test rows. There are zero eligible explicitly reviewed Unknown rows.
Thirteen reviewed Hardware/Audio rows are exported as review candidates only:
they are not automatically labeled Unknown or moved between splits.

## Decision Flow

1. The queued analysis settings freeze the model ID, artifact hash and enforcement
   flag. The original filename is not a classifier feature.
2. The active classifier proposes one label from the transcript.
3. Its acceptance policy may keep that label or reject it as Unknown. It cannot
   replace Phone with Camera, and legacy keyword rules cannot override it.
4. A validated policy checks confidence and similarity to training text from the
   proposed category. Similarity uses scikit-learn character TF-IDF (3-5 character
   fragments), cosine similarity, and the nearest training example in that label.
5. Both the vectorizer and reference vectors use train rows only. This is lexical
   support, not a semantic guarantee. Hard negatives that share technical terms
   must be included in validation and the independent test.
6. Unknown stops reference selection, duration advice, missing/hook suggestions
   and current-trend ideas before category datasets are queried.

Code: `app/services/classification_acceptance.py`, `classification.py`,
`classification_training.py`, `analysis_settings.py`, `recommendation.py`.
UI: `frontend_flutter/lib/screens/result_screen.dart`.

## How the Policy Is Chosen

The classifier is fitted only on train. Grouped cross-validation and classifier
hyperparameter selection also use train, grouped by source channel. The final
classifier is not refitted on validation after selecting the rejection threshold.

The confidence cutoff is a predeclared training parameter, not changed to fix the
four old examples. A fixed grid of similarity cutoffs (0.00 to 0.95, step 0.05)
is compared on validation. A cutoff must meet the requested minimum in-scope
Macro F1, minimum recall across all known classes, and Unknown recall. Among
passing cutoffs, the mean of Macro F1 and Unknown recall determines selection,
then minimum class recall, Unknown recall, and the lower cutoff break ties.

Minimum validation coverage is three examples per known category and ten Unknown
examples from at least three channels. Independent Unknown test coverage is at
least ten examples from three other channels. These are engineering minimums,
not statistical proof or a sufficient real-world collection target. The broader
Phase 22 coverage gate remains separate and normally requires more data.

Model ranking uses validated-policy status and grouped CV, not Test results.
Test is evaluated after selection to determine deployment eligibility, never to
tune thresholds. Repeated development after inspecting Test requires a fresh
final holdout to support a new unbiased performance claim.

The persisted artifact includes the policy version, train/validation row IDs,
selected cutoff, validation results, fitted vectorizer and reference vectors.
Admin activation and CLI activation both require the scope gate. Disabling the
larger Phase 22 collection gate does not disable this requirement.

## Leakage Protection

Preparation checks identities across partitions using row ID, Video ID, channel,
creator group and normalized transcript (Unicode normalization, case and whitespace).
Deleted/ineligible validation and test rows still reserve their identities.
Different labels do not exempt a shared channel from this audit.

Recommendation eligibility separately excludes validation/test rows and their
channels/identities, including archived holdouts. The existing four videos remain
regression cases and cannot become the new final Test just by renaming them.

## Regression and ASR Diagnosis

`artifacts/evaluation/classification-scope-20260927/report.md` and `report.json`
record the four original transcripts replayed through the real active artifact.
All four are Unknown under strict enforcement, with zero reference clips and
zero category suggestions. This measures prevention of unsafe downstream advice,
not classification improvement. New in-scope and Unknown test metrics are null.

To separate transcription sensitivity from classifier errors, a person must
listen to each source clip and complete `transcript-review-template.json` with
the expected label, reviewer identity and audio-verified transcript. The media
hash binds each review to its original clip. A corrected-text success can show
sensitivity to transcription; it does not prove that ASR was the only cause.

Replay into a new output directory, preserving earlier reports:

```powershell
python -B -X utf8 scripts/diagnose_classification_scope.py `
  --baseline-report artifacts/evaluation/phase7-20260926/after/report.json `
  --reviews path/to/completed-transcript-review.json `
  --out artifacts/evaluation/classification-scope-reviewed-run
```

## Still Needed Before Calling This Phase Passed

1. Collect/review validation Unknown cases across headphone, keyboard, mouse and
   other out-of-scope families, with hard cases close to Phone/Camera/Laptop.
2. Reserve separate new test channels and clips before adjusting any rule. Record
   provenance and review labels; do not use these clips as recommendation references.
3. Review the four old audio/transcript pairs and record the diagnosis.
4. Train/compare on train plus validation selection, then evaluate the frozen
   candidate on independent test clips. Report known-class metrics and Unknown
   rejection separately, including false rejection of valid clips.
5. Activate manually only after the full evaluation gate passes. If no cutoff
   preserves both known-class recall and Unknown rejection, collect better data
   or compare another model; do not lower the gate after looking at Test.

## Runtime Compatibility

`CLASSIFICATION_REQUIRE_SCOPE_VALIDATION` defaults to `true`; no `.env` value was
changed. An explicit `false` is legacy diagnostic mode with an unvalidated warning,
not a validated solution and not permission to activate an unqualified model.
The value is captured in each new job's analysis settings. Restore strict mode
for actual use. Restart the backend and any separate analysis worker after changes.

References: [scikit-learn threshold selection](https://scikit-learn.org/stable/modules/classification_threshold.html),
[data leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).
