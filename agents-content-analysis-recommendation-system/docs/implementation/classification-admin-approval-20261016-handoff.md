# Classification Admin Approval and Result UI Handoff

Updated: 2026-10-16 (Asia/Bangkok).

Follow-up: [Result Reference Responses](reference-response-result-handoff.md) supersedes the section-3 UI described below. The user approved real saved reference statistics as the fallback while qualified Outcome percentages remain unavailable; model approval and historical plans are unchanged.

## User Decision

- Remove the classification 80% deployment gate; Admin reviews measured percentages and chooses the deployed model.
- Remove selection checkboxes and the revision planner from the result screen without deleting existing plans.
- Rename section 3 to Predict. A causal engagement-improvement probability is not supported by the current Outcome model/data; do not fabricate one or substitute classification confidence.

## Completed

- Added persistent `admin_approved` deployment, separate from historical `qualified` evaluation. No minimum performance percentage or presentation expiry applies to this approval.
- Admin confirmation, role checks, current-active conflict detection, evaluated-artifact SHA, artifact reload/inference checks and per-clip Unknown rejection remain enforced.
- Approval creates an immutable derived artifact and registry row. Source artifacts, scores, saved analyses and Dataset splits stay unchanged. Old Test scores are not copied onto a potentially different operating point.
- Existing Validation-selected operating points are preserved. Otherwise selection uses the frozen Validation grid: mean of in-scope macro F1 and Unknown recall, then minimum category recall, Unknown recall and lower cutoffs. No Test input or 80% floor.
- Historical qualification reports remain diagnostics, not activation gates. Future evaluated candidates with usable artifacts and Validation evidence can use the same Admin workflow.
- Active classifier is **#58**, `taxonomy-tfidf-linear-svm-calibrated-approved`, version `admin-20261016T115419-03ae10ad`, derived from #57 (trained source #55). Activated through the actual Admin UI.
- #58 preserves the fitted estimator and operating point: confidence 0.6, similarity 0.2, contrast 0.0. No retraining or Test-driven retuning in this task.
- Validation: 42/49 correct (85.71%); Phone 14/18 (77.78%), Camera 19/21 (90.48%), Laptop 9/10 (90%); Unknown rejected 8/10 (80%). These are not engagement probabilities.
- Admin displays measured scores and non-expiring approval. Success messages identify the newly activated model, not the source ID.
- Result screen no longer mounts `ClipRevisionPlanner`. Removed selection/save-plan controls and unsaved-plan navigation guards. Advice, copy-example controls and expandable evidence remain.
- Revision-plan APIs/data and historical revision comparisons are retained for compatibility. Content #40's existing plan was verified unchanged.
- Section 3 is `3. Predict: ประเมินผลตอบรับ`. Unavailable assessments show no percentage or fake zero; unavailable scenario controls are hidden. Available-state semantics remain above-reference-median views, not causal uplift.

## Evidence

Root: `artifacts/classification-admin-approval/20261016/`.

- Read-only audit: 663 Dataset rows, 433 classification-eligible samples, 96 structurally eligible Outcome rows.
- Backend full suite: **628 tests, OK**, exit 0, `backend-tests-verified.log`. An earlier run reported 628 OK but PowerShell returned wrapper exit 1 for native stderr; rerun explicitly propagated Python's exit code.
- Frontend full suite: **171 tests passed**. Release web build succeeded; existing Cupertino font-family warning remains, Material icons rendered in inspected screenshots.
- After adding an actual reload/inference probe to the approval service: **15 tests, OK**, `approval-tests.log`.
- `regression.json`: reused real Whisper-medium ASR, not fresh held-out evaluation. Camera/Laptop/Phone classified correctly with 3/2/2 advice; Headphone/Keyboard rejected with no category advice. Existing Dataset rows and analyses unchanged.
- `browser/activation.json`, `approved-model.json`: UI approval #57 -> #58; same Validation operating point, content #40 and its plan unchanged. That run later failed a screenshot assertion because it stopped scrolling at the Predict heading before the paragraph; not counted as a complete browser pass.
- `browser-verified/verification.json`: corrected capture; routes and results passed at 1440/1000/390 px, no JS errors/API 5xx, temporary session logged out. Screenshots inspected for Admin scores, wrapping and the unavailable Predict state.
- `camera-upload.json`: new real upload of `videos/review_camera.mp4` through Whisper medium, #58 classification, recommendations, save and API reopen passed. Content **#41**, Camera, category confidence 0.971817 (not an outcome probability), three advice items, no presentation-expiry warning. Outcome remains unavailable.
- `restart.json`: actual owned-server restart completed; #58 still accepts predictions, saved #41 identical, upload limit 300 seconds / Whisper medium / Hook 60 seconds preserved. No manual trend-refresh request in this check.
- `final-integrity.json`: all 663 protected Dataset rows and 26 previous analyses unchanged; source #57 artifact hash unchanged; #58 is the sole active classifier; no unfinished training runs; Outcome registry remains 0. The scheduled collector updated 305 statistics rows, each verified against its real complete observation. Existing plan #40 is still revision 1 with one selected advice item.

## Outcome Still Unavailable

- Latest audit: 96 structurally eligible clips, Fit 72 / Tuning 24; eligible Calibration 0 / Independent Test 0. Structural validity does not authorize training or establish calibrated probabilities.
- Owner confirmed no data-use evidence. `docs/implementation/outcome-prediction-data-use-v1.json` remains unverified with training/serving disabled. This is the documented project gate, not a legal conclusion that every transcript is prohibited.
- Required rights evidence: permission/license or reviewed applicable basis covering intended training and evidence-display uses. Source URLs establish provenance, not permission by themselves. Do not mark confirmed without actual evidence.
- Independent evaluation uses held-out clips not used to fit, select thresholds or debug the Outcome model; calibration separately checks probability reliability. Do not relabel reused classification/debug clips as fresh independent Outcome Test.
- The existing target estimates relative-view group membership at observation time, not the probability that following advice causes engagement improvement. The latter requires appropriate intervention/outcome evidence, not only a new UI label.
- No Outcome model was trained/activated; no rights, calibration or evaluation gates were changed, and no percentage was fabricated.

## Access

- Web: `http://127.0.0.1:8080/#/dashboard`
- Admin: `http://127.0.0.1:8080/#/admin-training`
- Start/stop: `scripts/start_demo.ps1` / `scripts/stop_demo.ps1`, hidden owned processes.
- Old saved results retain their original model snapshot and warnings. New analyses use #58; deployment does not rewrite history.
- Open the newest `review camera` result **#41** in history to inspect the new model snapshot without the old presentation warning.
