# Retraining and Outcome Collection Gaps

Date: 2026-10-14, Asia/Bangkok.

## Request and Actual Result

The owner requested retraining after the corrected transcript replacement and an
estimate of additional clips needed to enable Outcome prediction.

- Classification retraining completed through the existing Admin worker.
- Four real candidates were fitted and registered, IDs 44-47. No candidate passed
  the existing qualification gates; none was activated.
- Outcome real-data preflight was run and remained blocked. No real Outcome
  model was fitted, no synthetic model was substituted, and the Outcome registry
  still contains zero models.
- No threshold, split assignment, rights confirmation, or sampling claim was
  changed to obtain a passing result.

## Data Quality Holds

A scan of the 309 classification-eligible records found three clear source-quality
problems before fitting:

| Dataset | Category | Video ID | Existing split | Problem |
| --- | --- | --- | --- | --- |
| 258 | Camera | tC-9SOcKgoM | train | English text labelled Thai |
| 502 | Laptop | LSDdOvpbj6M | train | Missing-caption notice instead of transcript |
| 529 | Phone | 4TbEACxj1rI | validation | English text labelled Thai |

These were backed up and held using `is_training_eligible=false`,
`transcript_quality=poor`, and explanatory review notes. Text, identity, language,
source, statistics, and split were retained. Each hold has a SystemLog entry.
The poor quality excludes these rows through the existing production transcript
conditions, including paths that do not require the training eligibility flag.
No row was deleted and the database still has 536 datasets.

The first attempt aborted when the existing update schema ignored quality/note
fields; an outer InnoDB transaction rolled back the eligibility update. Read-back
confirmed all three original states. The reviewed retry used the existing service
for eligibility and explicit ORM quality/note updates in the same outer transaction.
It succeeded and produced exactly three quality-hold logs. Do not rerun it.

## Classification Run

- Run: `f12b91c2-1682-4379-ae0e-304c23a64e50`.
- Version: `web-20261014T084115-f12b91c2`.
- Started 15:41:20 and finished 15:53:20 Bangkok, 12 minutes.
- 306 in-scope examples: Phone 101, Camera 98, Laptop 107.
- Train 215, Validation 36, Test 55; channel splits unchanged.
- Unknown remains evaluation-only: Validation 10, Test 30, two reserved Train
  examples not fitted. This is not a fresh externally collected test set.
- Existing 0.8 promotion requirements, 0.6 starting confidence threshold,
  channel-grouped CV, and validation-selected scope policy were retained.
- The cached multilingual embedding model was available; no model download.

| Model ID | Candidate | Grouped CV accuracy | Test before scope policy | Qualified |
| --- | --- | ---: | ---: | --- |
| 46 | Calibrated TF-IDF Linear SVM | 95.35% | 94.55% | No |
| 45 | Tuned TF-IDF Logistic Regression | 90.23% | 94.55% | No |
| 47 | Multilingual Embedding Logistic Regression | 82.79% | 90.91% | No |
| 44 | TF-IDF Complement Naive Bayes | 81.40% | 92.73% | No |

Rank 1 is #46, selected by the existing validation/grouped-CV criteria, not by
choosing the best Test outcome. All models failed `no_validation_cutoff_passed`.
For #46 at the prespecified zero similarity cutoff, Validation Laptop recall was
2/6 (33.33%) and Unknown rejection 6/10 (60%). Raising the similarity cutoff
improved Unknown rejection but did not resolve the Laptop acceptance gap. This
diagnostic point is not a newly selected production threshold.

With an invalid scope policy, the runtime intentionally abstains on all in-scope
evaluation records. Thus post-policy Test accuracy is 0%, not 94.55%; the raw
diagnostic accuracy must not be advertised as usable end-to-end accuracy.
Classifier Test results are regression diagnostics from reused protected data,
not fresh independent certification. Outcome Independent Test labels were not opened.

All four artifact hashes and existing reload checks passed. All 43 pre-existing
classification model records and all 16 saved analysis results remained unchanged.
The active classifier is still #43, whose presentation authorization expired on
2026-10-06. Its current readiness is blocked with `presentation_expired`,
`model_not_qualified`, and `scope_policy_not_validated`. No authorization was renewed.

## Outcome Readiness

Frozen audit cutoff: `2026-10-14T08:41:26Z`.

| Check | Current result |
| --- | ---: |
| Active source clips in the three categories | 372 |
| Source channels | 139 |
| Structurally eligible Outcome rows | 0 |
| Rows without confirmed format in production metadata | 372 |
| Rows without confirmed Outcome sampling frame | 372 |
| Rows with no usable observation at the cutoff | 142 |
| Rows with stale successful observations | 13 |
| Rows declared partial rather than full-video transcript | 77 |
| Rows failing the production transcript contract | 66 |
| Accepted Calibration clips | 0 |
| Accepted independent Outcome Test clips | 0 |

These issue counts overlap, and are not additive new-acquisition requirements.
Existing format evidence in audit files is not absent: it simply has not been
approved and persisted in the production metadata used by the Outcome builder.
The old nine unresolved formats already have an owner Shorts confirmation; do
not ask the owner to repeat that confirmation.

The existing data-use decision record still has unverified training/serving
permission and no confirmation evidence. Agents must not assert this permission
for the owner. This is a statement about the current project record, not a new
legal determination. Fixing clip counts alone cannot bypass that gate.

`build_outcome_dataset.py` returned `blocked_data_use`, created no manifest, and
confirmed its audit did not write to the database. `train_outcome_model.py` then
returned blocked with `phase2_frozen_manifest_missing`, created no artifact, and
did not open Independent Test labels.

## Conditional Collection Budget

The count-only plan combines the existing 172-format audit, the scoped owner
confirmation for the nine Shorts, and the owner's regular-video confirmation for
the new 67. It preserves current roles, excludes the three quality holds, and
does not count protected records as Fit/Tuning. Current regular-video development
count candidates are Phone 59, Camera 39, Laptop 44, distributed across age bands.

The following is ONE illustrative restricted scope based on coverage, not on
Test outcomes. It has not been frozen or approved as product scope. Age is the
video's age when an actual new statistics observation is collected, not the
upload age of a user's unpublished clip. Counts below project a successful refresh
at the audit cutoff; they are not fabricated observations or qualified benchmarks.

| Context, regular videos only | Existing Fit / channels | Existing Tuning | Additional Fit | Additional Tuning toward 10/category | Calibration plan | Independent Test | Total slots |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Phone, 90 to <365 days | 15 / 6 | 6 | 5 | 4 | 10 | 10 | 29 |
| Camera, >=365 days | 14 / 9 | 4 | 6 | 6 | 10 | 10 | 32 |
| Laptop, 90 to <365 days | 20 / 3 | 1 | 2 | 9 | 10 | 10 | 31 |
| Total | 49 | 11 | 13 | 19 | 30 | 30 | 92 |

Laptop's two extra Fit clips must supply two additional Fit channels, not two
more clips from its existing three channels. Required channels across partitions
must also be met without creator overlap. The Tuning minimum is 30 overall;
10/category is the balanced collection plan, not an added protocol requirement.
Calibration needs at least 30 assessed examples because its three calibration
bins need at least ten each, even though its partition minimum alone is 20.

**92 is a conditional slot budget, NOT a proven minimum number of brand-new
transcripts and NOT a guarantee of activation.** For logistics, approximately
100-110 candidates would provide a modest buffer above that scenario, not a
statistical sample-size guarantee. Repairs or accepted existing data can reduce
new acquisitions; inadequate topic/label support, channel independence, sampling,
transcript completeness, or evaluation results can increase them. The Camera
count still includes some uncorrected new-batch files declared full in the DB;
their actual completeness must be checked before giving them credit.

The old high-response sampling and the new 67's mixed/unknown selection do not
become representative independent probability-evaluation data by having longer
transcripts. Do not retrospectively declare them randomly sampled. Do not select
new clips by desired high/low outcome labels to force balance or a passing metric.
Both labels, calibration bins, topic support, and independent-evaluation confidence
intervals still need to pass under the frozen protocol.

## Next Actions, in Order

1. Resolve the owner data-use evidence and approve/persist the already documented
   format and honest sampling metadata. Do not fetch another unscoped batch first.
2. Repair the three held transcripts and inspect completeness of remaining old
   summaries/partial text; no back-translation or invented timestamps.
3. Review the classifier's Laptop Train/Validation hard cases and Unknown policy
   with development evidence. Do not tune from Test or lower the 80% gate.
4. Confirm the intended regular-video age contexts, then reserve URLs, channels,
   creators, and roles BEFORE requesting transcription. Screen cheap metadata and
   identity overlap first. Keep Calibration/Test out of reference recommendation
   data and all development workflows. Do not force an assigned channel to a new role.
5. Collect using a documented outcome-independent rule that allows both ordinary
   and high-response clips. Confirm source/coverage/language. Collect authorized
   real observations; do not manufacture historical observations.
6. Freeze and build Outcome data, fit baselines/candidate, tune and calibrate,
   then evaluate the frozen candidate on independent data. Activation remains a
   separate approval after every gate, including runtime classification readiness.

## Verification and Evidence

Commands run with `CONTENT_AI_SKIP_DB_BOOTSTRAP=1`:

```powershell
py -X utf8 -m unittest discover -s tests -p test_classification_training.py -v
py -X utf8 -m unittest tests.test_outcome_data_preparation tests.test_outcome_dataset tests.test_outcome_training tests.test_outcome_prediction_readiness -v
```

13 classification tests and 39 Outcome tests passed, 52 total. These are software
tests, not claims that the real models passed. Reload/hash checks on all four real
classification artifacts also passed. Training finished and no worker remains active.

Operation evidence: `artifacts/retraining/20261014-corrected-transcripts/`:

- `before.json`: full pre-run datasets, old classifier rows, saved results.
- `quarantined.json`: post-hold rows, with unchanged text and split.
- `classification-readiness.json`, `run.json`: actual 306-example start state.
- `outcome-preflight/`: blocked build report, exclusions and feature schema.
- `outcome-training/preflight-report.json`: actual blocked real training attempt.
- `outcome-count-plan.json`: IDs, evidence hashes and all 15 age/category cells;
  no outcome labels or values were exported for collection planning.
- `verified-results.json`: independent DB read-back and artifact checks.
- `start_run.py`, `audit_gaps.py`, `verify_run.py`: scoped reproducible operation code.

Actual classification report:
`artifacts/classification_training/web-20261014T084115-f12b91c2/training_report.json`.
Worker log:
`artifacts/classification_training/worker_logs/f12b91c2-1682-4379-ae0e-304c23a64e50.log`.

The live statistics collector updated some statistics while training was running.
Those external changes were preserved and recorded, not reverted. Transcript
hashes, identity and splits remained unchanged across every dataset. Do not
restore the entire backup over newer statistics; any future hold recovery should
restore only reviewed eligibility/quality fields after a valid source repair.
