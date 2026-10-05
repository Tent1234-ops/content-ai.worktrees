# Scope Holdout Protocol: 4 October 2026

This protocol is fixed before the new training run. It corrects an import-role
mismatch, not a model score. The user's 42 approved Unknown transcripts were
assigned by the generic channel hash to train=35, validation=5, test=2. Unknown
train rows are not fitted by the classifier or acceptance policy.

## Selection Rules

- Preserve every existing validation/test assignment, including archived rows.
- Move only entire training channels; move known rows on those channels too.
- Use identities and counts only. No titles, transcript terms, predictions,
  confidence scores, or engagement values participate in assignment selection.
- Target Unknown validation=10 and test=30. Remaining Unknown rows stay reserved.
- Among feasible exact-size assignments, minimize known training rows removed.
  Deterministic channel-hash ordering breaks ties. Do not search different seeds
  or repartition again after seeing evaluation results.
- Store the preview, checksum, prior row assignments, and immutable registry in
  the database. Future imports and startup migration must honor the registry.
- Fit every candidate from scratch. Existing artifacts/results remain unchanged.
  Recommendation evidence continues to use train-only eligible rows.

## Evaluation and Activation

Keep existing confidence=0.6, promotion=0.8, grouped-CV=5 and all Unknown sample,
channel and recall gates. Fit/tune classifier on known train only; select the
rejection cutoff on known/Unknown validation only. Rank candidates by scope
validation and grouped-CV, not Test. Test is an acceptance check, not a tuning set.
If the selected candidate fails, do not switch to a Test-selected alternative,
lower thresholds, or change partitions. Report the blocker; retain the active model.

This is a **repartitioned internal benchmark**, not a fresh external evaluation:
some newly held-out known examples were used by older models, and old validation/
test sets have prior exposure. Do not describe these results as unseen-video or
human utility evidence. The new candidates have channel/identity-disjoint data,
but fresh external testing remains a separate outstanding requirement.

## Preview

Artifact: `artifacts/scope-holdout-20261004/partition-preview.json`.
SHA256: `707a1d5656f0e8a443561ace09b754ed8f580de7c994e3be7571390d68cdb8a0`.
Unknown: 2 reserved, 10 validation, 30 test. Known: Phone 63/12/5,
Camera 61/13/6, Laptop 54/5/26 (train/validation/test). 46 rows move, no deletions.
