# Outcome Prediction Review Fixes: Handoff

Date: 2026-10-11 (Asia/Bangkok).

Scope: fix R1-R8 from [the 10 October review](outcome-prediction-full-review-20261010.md). This is a software repair and verification pass, not real model qualification or a new roadmap phase.

## Safety and Current Decision

- No real training, real Independent Test opening, activation, rights confirmation, protocol threshold reduction, or live database mutation was performed.
- Training/evaluation and API persistence tests use explicitly synthetic records and temporary SQLite databases. Synthetic qualification never makes a production model eligible.
- Existing saved assessments, original candidate artifacts, and historical review evidence are preserved. No probability or performance improvement is claimed from software tests.
- Real prediction remains **not demonstrated / not qualified**. The last real audit is the 10 October review, not a fresh audit performed in this repair pass.

## Completed Fixes

| Finding | Implementation | Regression evidence |
|---|---|---|
| R1: missing Independent Test evaluator and constant fresh count | New `outcome_independent_evaluation.py` and `evaluate_outcome_candidate.py`: explicit candidate freeze, immutable input hashes, sealed identities, one-shot access ledger, exact pinned observations, frozen estimators/calibrators/Fit benchmarks, all baselines and context decisions, persisted report/artifact/registry/metrics. Readiness accepts a manifest and counts only verified fresh holdout identities. | Synthetic freeze -> evaluation -> persistence without model/calibrator fitting; missing confirmation, changed candidate, changed observation commitment, failed access, reuse, and real-mode synthetic rejection; deterministic positive and negative qualification tests. |
| R2: upload omitted prediction context | `/analyze/settings` returns contexts only from the qualified active artifact. Upload offers explicit format/reference age selection, defaults to opt-out, and revalidates after refreshing settings. Repository sends multipart fields. Backend measures duration and preserves context through job, save, and reopen. | Multipart -> job -> actual assessment -> save/reopen integration with mocked ASR/classification and temporary DB; repository field tests; desktop/mobile widgets; unavailable-model state. |
| R3: explicit data-use denial ignored | Audit/training/serving require their respective explicit permission. Withdrawn permission is rejected. Synthetic permission needs a separate explicit testing opt-in and cannot authorize the live paths. | Missing, false, and withdrawn permissions; synthetic allowed only in isolated fixture mode. Real rights document unchanged. |
| R4: normalized duplicates crossed splits | Frozen identities include normalized transcript hash and human-reviewed near-duplicate group, in addition to video/channel/creator/raw hash. Connected identity groups cannot span roles. Training checks the frozen groups again. Holdout checks also reject reference overlap and changed/unreadable provenance. | Case/punctuation duplicates, transitive connected groups, reviewed near duplicates, reference overlap, and invalid live metadata are rejected. No protected Test is moved into Train. |
| R5: evaluated scope not enforced | `outcome-qualified-scopes-v1` records actual category/format/reference-age/view-metric combinations. Activation, inference, pinned scenario/revision scoring check these contexts and registry/artifact agreement. Legacy dimension-name lists cannot qualify. | Phone-only versus Camera request, empty/failed/legacy scopes, and registry/artifact mismatch. Flutter still reads old lists for display but does not turn them into qualified contexts. |
| R6: evaluation coverage differed from serving | Shared support policy in `outcome_support.py` is used for tuning, calibration, Independent Test, and inference. Baselines compare the same supported population. Overall and per-context coverage include abstentions in their original denominator. | Legacy fixture honestly reports 25 assessed / 30 eligible / 5 abstained, and cannot pass all-category Validation because supported Laptop positives are absent. Separate varied-channel fixture exercises evaluation. Per-context regression verifies 39/40 with 1 abstention, not 39/39. |
| R7: direction contradicted pooled medians | Evidence text describes the within-channel paired difference, its interval in view units, and channel count. Pooled medians are separate descriptive numbers without borrowing the paired direction. Evidence schema is versioned. | Simpson's-paradox fixture and negative comparison; no causal uplift claim. Saved historical wording is not silently regenerated. |
| R8: calibration version mismatch | Registration takes `weighted-platt-sigmoid-v1` from the validation report and verifies artifact agreement. Loading, activation, inference, and saved assessment provenance enforce parity. | Worker round-trip, artifact integrity, inference mismatch rejection, saved assessment tests. |

Additional UI: the Admin model detail shows Independent Test Brier results for all three estimators, assessed/eligible/abstained counts, and qualified context labels. No activation or training success is fabricated.

## Verification

Evidence root: `artifacts/outcome-prediction/review-fixes/20261011-fixes/` (local generated evidence, ignored by Git).

| Check | Result |
|---|---|
| Full backend regression | PASS: 584 tests, 121.692 seconds, exit 0, `backend-tests-final.log`. |
| Full Flutter regression | PASS: 169 tests, `flutter-tests.log`. |
| Flutter analyze | PASS: no issues, 15.2 seconds on the final UI source. |
| Release web build | PASS: `web-build.log`, 62.2 seconds. Non-fatal Cupertino font/Wasm informational warnings remain. |
| Browser | PASS: 1440x900 and 390x900, six screenshots, no JavaScript/RenderFlex errors, `browser-passed/verification.json`. Selected context, unavailable model, and Admin metrics verified. |
| CLI import/argument parser | PASS: `py -X utf8 scripts/evaluate_outcome_candidate.py --help`. This does not open Test. |
| Diff whitespace | PASS: `git diff --check` from workspace parent; only Git LF/CRLF notices. |

An earlier full backend run exposed six fixture expectation failures after enforcing supported category evaluation. These were not fixed by weakening thresholds: the insufficient fixture now must remain experimental, and an explicit varied-channel synthetic fixture covers the evaluation workflow. A subsequent 583-test run passed before the final provenance/coverage regression was added. Keep the initial `backend-tests.log` as debugging history, not final acceptance evidence.

Browser automation uses the release build and intercepts API traffic with explicit synthetic fixtures, with no live backend. Initial failed browser attempts used the wrong Flutter accessibility roles/selectors and attempted fixture localStorage setup on `about:blank`; these harness issues were corrected. Their screenshots are diagnostic evidence, not successful acceptance. The successful run and screenshots are exclusively under `browser-passed/`.

Commands executed for final acceptance (SDK commands run from `frontend_flutter`; backend/browser commands from project root):

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -X utf8 -m unittest discover -s tests -q
C:\flutter\bin\flutter.bat test --no-pub
C:\flutter\bin\flutter.bat analyze --no-pub
C:\flutter\bin\flutter.bat build web --release --no-pub
node scripts/browser/verify_outcome_fixes.cjs artifacts/outcome-prediction/review-fixes/20261011-fixes/browser-passed
```

All eight software findings are addressed. Remaining work below is real-data preparation and real acceptance, not a claimed pass of the real Outcome model.

## Running Independent Evaluation Later

Only after real data-use authorization, a reviewed frozen dataset, a genuinely fresh protected holdout, and a real registered Validation-passed candidate exist:

1. Freeze the exact candidate and inputs. This checks provenance but does not read sealed Test outcomes.

```powershell
py -X utf8 scripts/evaluate_outcome_candidate.py --model-id <ID> --manifest <manifest.json> --features <features.json> --freeze <new-freeze.json> --actor <reviewer> --freeze-only
```

2. Review the freeze before explicitly opening Test once. Output must be a new directory inside `artifacts/outcome-prediction/phase-3/registry/`.

```powershell
py -X utf8 scripts/evaluate_outcome_candidate.py --model-id <same-ID> --manifest <same-manifest.json> --features <same-features.json> --freeze <same-freeze.json> --actor <reviewer> --confirm-open-test --output-dir <new-registry-subdirectory>
```

3. Evaluation records a qualified or experimental result, or a durable evaluation failure. It never activates the model. Activation remains a separate explicit Admin action and applies the qualification/rights/context checks.
4. Back up `artifacts/outcome-prediction/phase-3/independent-test-access/access.sqlite3`, registry artifacts, and the database together. An interrupted or failed run after the access claim consumes that holdout. Do not remove the ledger or rename a candidate to reuse Test for tuning.
5. `scripts/evaluate_outcome_release.py --evaluated-model-id <ID> --phase5-freeze <same-freeze.json>` can incorporate the verified persisted evaluation, alongside its other required evidence arguments. It does not open Test. Human utility and live acceptance remain separate pending release gates.

## Compatibility and Remaining Work

- Newly generated models use `outcome-model-artifact-v2` and validation reports use `outcome-validation-report-v2`. Old v1 Outcome artifacts lacking the repaired support/scope contract are rejected, not silently upgraded or activated.
- Old manifests missing normalized identity require rebuilding from reviewed source metadata before training. Do not label old/previously inspected Test data fresh to satisfy the checker.
- The last real audit found 308 target rows but 0 structurally ready Outcome rows, unverified data-use authorization, and no registered/active Outcome model. Counts may have changed since that audit; rerun the read-only audit before planning collection quantities.
- Confirm format and sampling frame, review full-transcript coverage, obtain valid dated observations, and demonstrate holdout independence. Fix metadata per row where evidence exists; do not invent it or automatically assume all clips must be recollected.
- The earlier audit also found the classification presentation allowance expired. That is separate from Outcome Prediction and must not be bypassed by these repairs.
- A real MP4 -> ASR -> qualified real probability -> human utility acceptance has **not** been run here. The API integration uses synthetic inference with mocked ASR/classification, and browser traffic is intercepted.
- Preview: `http://127.0.0.1:8091`. This is a hidden static release-web server only; the live Backend was intentionally not started, so normal API-dependent pages need the project's Backend to be running separately. Browser fixtures are not embedded in the app.
