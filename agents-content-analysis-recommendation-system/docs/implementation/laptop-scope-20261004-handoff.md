# Laptop / Unknown: Train-Validation Development

## Scope

User request: improve Laptop classification and Unknown acceptance from
Train/Validation. Protocol: [development rules](laptop-scope-20261004-protocol.md).
Do not change the immutable split plan, lower promotion/confidence gates, fit
Unknown Validation, or use Test to pick a method.

## Completed

- Confirmed failures using actual Validation transcripts, not filenames alone.
  Baseline SVM #41: IDs 73/92 (MacBook) predicted Phone; ID238 correctly predicted
  Laptop but confidence 0.510 < 0.6; ID237 accepted Laptop. ID25 is a stand review.
- Added transcript-only Thai normalization and PyThaiNLP word/character features.
  Source text, timestamps, database rows, and old fitted artifacts stay intact.
  New normalization retains Thai tone marks and Latin word boundaries.
- Added development runners whose SQL excludes Test before loading records.
  Fit vocabulary and classifier on known Train only; C selection uses grouped CV.
- Added optional scope v2: normalized Train similarity plus competing-class
  margin, selected on known/Unknown Validation together. It can reject, not
  replace a predicted class. v1 remains the default and retains its behavior.
- Added explicit per-model acceptance-policy version and compatible readiness
  reporting. No previously failed model becomes qualified through this change.
- Ran three lexical experiments (four C values each), then v2 recalibration.
  All failed the joint Validation gate. Failures are retained, not hidden.

## Data Review Needed (Not Automatically Relabeled)

| ID | Existing label/split | Evidence to review |
| --- | --- | --- |
| 25 | Laptop / Validation | Temu laptop stand; transcript describes six-height metal stand and nonslip silicone, not a laptop review |
| 3 | Phone / Validation | Tutorial for applying a screen protector |
| 4 | Phone / Validation | Loan-payment app tutorial, not a phone hardware review |

The assistant asked the user whether Laptop covers the device only or accessories.
Do not remove failed examples just to improve metrics. Establish the scope rule,
review it consistently across Train/Validation, preserve split/channel boundaries,
record old/new labels and hashes via the existing reviewed-dataset workflow, then
freeze a new data version. Test label review needs an independent human process,
not developer access to Test predictions for tuning.

Laptop Train contains mostly Windows notebook reviews; MacBook representation is
limited. More data is not automatically needed in every category. First settle
scope/label quality, then fill actual Train subtype/channel gaps with new sources
outside held-out channels. Never move the MacBook Validation examples into Train.

## Artifacts

- `artifacts/laptop-scope-20261004/development-v1/report.json`: all grouped-CV
  candidates, chosen C, per-row Validation raw outcomes, v1 calibration grid.
- `artifacts/laptop-scope-20261004/contrast-v2/report.json`: all v2 grids and failures.
- Development joblib files are explicitly `development_only`; they are not
  registered production artifacts and must not be manually activated.
- `scripts/develop_classification_scope.py`: repeat into a NEW directory; supports
  `--recalibrate <original-run>` with exact development fingerprint validation.
- `scripts/develop_hybrid_scope.py`: bounded lexical + frozen local embedding
  experiment. Embeddings have no supervised fit; TF-IDF is fitted separately in
  each grouped-CV fold. Runtime probabilities are checked against cached math.

## Final Result

**Development batch finished; the production problem is NOT fully resolved.**
No candidate passes joint Validation. No Test was queried by either runner;
no Test evaluation, registration, or activation was performed.

Hybrid C=16 was selected on grouped Train CV: accuracy 96.07%, Macro F1 98.04%.
These are development/model-selection scores, not independent accuracy claims.
Laptop Validation: ID73 now predicts Laptop at 0.806; ID238 at 0.793; ID237 at
0.954. ID92 still predicts Phone at 0.530 (rejected), and stand ID25 predicts
Laptop at 0.487 (rejected). Accepted Laptop improves from SVM #41's 1/5 to 3/5,
but does not reach 4/5 required by the unchanged 80% gate.

| Hybrid Validation configuration | Phone | Camera | Laptop | Unknown rejected |
| --- | --- | --- | --- | --- |
| Confidence 0.6 only | 9/12 | 13/13 | 3/5 | 7/10 |
| v1 support 0.30 | 9/12 | 10/13 | 3/5 | 8/10 |
| v2 support 0, contrast 0 | 9/12 | 11/13 | 3/5 | 8/10 |

The last two rows are diagnostic operating points, **not qualified policies**.
At least one known-class recall remains below 0.8. Runtime continues to reject
unvalidated policies; do not equate blanket withholding with 100% Unknown recall.
Report: `artifacts/laptop-scope-20261004/hybrid-v1/report.json`.

Verification: complete backend suite **501 passed** before the final added
per-class-gate regression test. Logs: `backend-tests.stdout.log` and
`backend-tests.stderr.log` in the same artifact directory. Focused tests and
final static checks are recorded below. API health and web both return 200;
registry still contains 42 models, active #14, zero managed training jobs.

Final focused verification: **51 passed**, including the new regression proving
that high overall scores cannot bypass Laptop's per-class recall gate. Logs:
`final-focused.stdout.log` / `final-focused.stderr.log`. Python compileall passed
for both services and development runners. No frontend files changed; no new
browser/ASR acceptance claim. All development/training/test processes completed.

Files changed: `classification_features.py`, `classification_acceptance.py`,
`classification_training.py` (explicit spec policy version),
`classification_readiness.py`, `model_management.py` (version compatibility),
the two development scripts, feature/acceptance regression tests, and these docs.
The existing model catalog/default policy were not switched to an unsuccessful
experimental candidate. The web/API already running on 8080/8000 remain available.

## Still Pending

- Human scope/label review for IDs25/3/4 and a consistent review rule. The user
  has not yet answered the scope question at this checkpoint.
- Fill MacBook Train representation using new eligible sources on non-held-out
  channels if device-only scope is confirmed. Do not infer an arbitrary number
  guarantees passing; review current Train subtype coverage first.
- Refit against corrected/versioned data, then select/freeze on Train/Validation.
- New Test evaluation, registry creation/activation, new MP4/Whisper testing, and
  human recommendation utility evaluation are not part of completed evidence.
- Active registry model remains #14; the strict Unknown gate is not disabled.
