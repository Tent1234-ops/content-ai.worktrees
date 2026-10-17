# Result Simplification and System Guide Handoff

Date: 2026-10-17 (Asia/Bangkok).

## Requested and Delivered

- Removed the example-sentence copy button from `ActionableAdvicePanel`, including the unused clipboard handler/import. The example sentence itself remains visible/selectable.
- Removed the normalized-transcript display from `AnalysisReport`. Original transcript remains expandable; normalized data remains in the model/API/database.
- Removed the combined evidence/version expansion and its unused result-only helper/imports. Per-advice evidence dialogs and real reference-video responses remain available.
- Preserved previous removal of the planner/selection controls and all historical records. No backend, Dataset, training, model activation or prediction policy changes.
- Added `docs/presentation/system-walkthrough-th.md`: detailed Thai explanation of screens, API flow, algorithms, real vector example, training/Unknown, recommendation/evidence, trend collection/history, tables, Admin workflows, presentation questions and limitations.
- Added a latest-guide pointer to `docs/presentation/current-system/README.md`; older dated explanations remain historical rather than being silently rewritten.

## Documentation Audit

- Inspected implementation routes/services and Flutter router/screens, not only older project plans.
- Read database with `CONTENT_AI_SKIP_DB_BOOTSTRAP=1`; no Dataset/config/model mutations.
- Active classifier #58: `taxonomy-tfidf-linear-svm-calibrated-approved`, status `admin_approved`. Outcome registry count 0. Dataset row count 663.
- Main-category production-eligible query: Phone 108/18/18, Camera 110/21/12, Laptop 93/10/43 (Train/Validation/Test), total 433. The guide distinguishes this query from final training-manifest counts and notes other-category rows separately.
- Settings read: Whisper medium, upload 300 seconds, Hook 60 seconds, max_keywords 10, hourly window 14:00-23:00.
- Actual read-only artifact probe using a clearly identified authored short camera sentence: vector (1, 80000), 228 nonzero values; raw Camera 0.981816, but rejected as Unknown due to support similarity 0.141417 < 0.2. Used as an honest illustration of rejection, not as a held-out evaluation or a new Dataset row.
- Saved #41 example and Validation metrics are attributed to earlier handoff evidence; the guide does not claim a fresh MP4 run or new independent evaluation.
- Checked all 44 local Markdown links: none missing. Later API/formula additions add no further links.

## Verification

- Focused Flutter tests: 51 passed, exit 0.
- Full Flutter suite after changes: 202 passed, exit 0 (`flutter test --no-pub --reporter compact`).
- Flutter analyze: no issues, exit 0.
- Release web build passed. Existing Cupertino font-family warning remains; Material icons used here render correctly.
- Browser script syntax check passed.
- Live API/browser acceptance passed at 1440, 1000 and 390 pixels. Expanded original transcript retained; copy control, cleaned transcript label and combined audit expander absent. Reference counters still match saved evidence; no planner API calls, browser errors or API 5xx in this run. Temporary session logged out successfully.
- Artifacts: `artifacts/classification-admin-approval/20261016/browser-result-simplified-20261017/verification.json` plus screenshots, accessibility snapshots and reference-proof JSON per viewport.
- Visually inspected desktop expanded transcript and mobile result/reference screenshots for wrapping and overlap.

## Remaining / Boundaries

- This is a UI/documentation change. Did not rerun fresh Whisper uploads, retrain classifier/Outcome, or run the full Python backend suite.
- Earlier `/admin/training` overview timeout is still documented, not claimed fixed by this focused result-page check.
- No claim of a validated causal engagement-improvement percentage; reference responses are descriptive, real, frozen evidence.
- Guide describes known limitations, retained legacy code and older documentation discrepancies explicitly.

## Access

- Web remains available at `http://127.0.0.1:8080/#/history` on the existing server. Reopen `review camera`; Ctrl+F5 refreshes a previously loaded old build.
- Start reading `docs/presentation/system-walkthrough-th.md`; sections 5-10 cover the requested Transcript -> Vector -> Classifier -> Output explanation.
