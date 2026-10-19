# Historical Group Response Summary

Updated: 2026-10-18 (Asia/Bangkok).

## Scope and Status

- Implemented the requested Thai X/N/Y%/Z-channel statement in result section 3.
- Descriptive statistics only. No Outcome training, activation, gate changes, invented Day-7 outcomes, causal uplift, or split reassignment.
- Completed calculation, persistence, label polish, release build and real-data browser verification. No remaining implementation work within this task.

## Calculation

- `group_response_summary.py` consumes the frozen, complete pre-performance-filter topic comparison records. It does not use the top-40% keyword reference examples as the denominator.
- Only explicit `general_protocol_v1`, non-high-performance-selected, Train/reference-eligible records are admitted. Unknown selection provenance, protected splits, incomplete transcripts, invalid/missing identities and observations, unconfirmed formats, unknown metrics and observations outside the 24-hour cutoff are excluded.
- Context cells: category, explicitly confirmed format, age at observation, view metric version. No cross-cell pooling or selection of only positive results.
- Benchmark: existing channel-balanced weighted-median definition, computed across all eligible cell records, whether or not the topic was detected. It is a descriptive benchmark, not a fitted Outcome label/model.
- N: unique videos with transcript evidence of that topic. X: those videos with views strictly above the benchmark. Y: 100*X/N rounded to two decimals. Z: unique channels among N. Ties fail the threshold; genuine zero views and 0% remain valid.
- Minimum topic support is two videos from two channels, matching advice support. This is not an independent-evaluation qualification or a replacement for the unchanged paired-comparison minimums.
- Store policy version, cutoff, threshold, member/passing/benchmark Video IDs, observation time range and fingerprint. Parent comparison records retain Dataset IDs, Observation IDs, quotes and per-source counters; parent evidence fingerprint covers the complete snapshot.

## UI and History

- New analyses persist the summary in `evidence_bundle.topic_comparisons.items[].group_response_summary` through the existing analysis JSON storage. No schema migration is needed for this feature.
- UI checks saved totals against the frozen member records and shows category, confirmed format, age range, threshold, benchmark size and recorded times.
- Expand `คลิปที่ใช้คำนวณ` for the actual denominator members, counters, pass/fail and source links.
- Existing illustrative reference clips remain separate and are explicitly labelled as a different cohort, not the percentage denominator.
- Legacy or insufficient results show an unavailable state, not a fabricated zero. Saved historical results never query today's Dataset to invent a missing summary.
- Only new analyses receive the new field. Old user records were not rewritten by verification.

## Real Data Evidence

- Read-only audit: `artifacts/group-response-summary/20261018/live-audit/`.
- Recalculated the existing `review camera` text (#41), guarded against SQL writes, using current classifier acceptance and current eligible references. Recalculation was exported to artifacts, NOT saved over #41.
- Camera benchmark: 35 regular videos / 35 channels, age >=365 days, threshold >15,126 views, observations 2026-10-17 23:00:40-41 Asia/Bangkok.
- Low light: 4/7 = 57.14%, 7 channels. Stabilization: 5/9 = 55.56%, 9 channels. Handling: 14/24 = 58.33%, 24 channels.
- These are observed proportions in the collected frame, not estimates for all YouTube videos or the user's future outcome. Metadata/ASR mistakes and channel/content confounding remain possible.

## Verification

- Backend: 50 tests passed across group summaries, topic comparisons, actionable advice, evidence and Outcome inference. Includes API schema round-trip and save/reopen after Dataset changes in an isolated test database.
- Flutter: full suite 230 tests passed; final focused summary/reference suite 55 passed after the separate-cohort label adjustment. Analyzer clean before that text-only adjustment.
- Release build succeeded at `frontend_flutter/build/group-response`; existing Cupertino font warning remains, unrelated to the Material icons used here.
- Final browser evidence: `artifacts/group-response-summary/20261018/browser-final/verification.json`, passed at 1440 and 390 pixels. Screenshots inspected, no layout errors, member list accessible; the final build explicitly distinguishes illustrative references from denominator members. The earlier `browser/` run predates that label adjustment.
- Browser uses a test-only response overlay of the real read-only calculation so no old result is overwritten. This is not a claim that a fresh video was transcribed/uploaded in that browser run. It verifies real calculated numbers rendered by the production Flutter widgets. Original saved API response was unchanged; temporary auth session ended.

## Access and Remaining Notes

- New web: `http://127.0.0.1:8081/#/upload`, API: `http://127.0.0.1:8011`.
- Initially the new API used `--lifespan off` alongside existing services. After the user resumed, all four ports (8000, 8080, 8011, 8081) were confirmed stopped and the interrupted final build was rerun successfully. The final API on 8011 was started with its normal lifecycle, including existing background services. API health and web HTTP 200 were confirmed. No existing process was terminated.
- Launcher process identities/logs: `runtime_artifacts/group-response/state.json`. Both processes started hidden.
- No claim of new data-use clearance. Existing Outcome data-use/independent-evaluation blockers remain unchanged; this task implements the requested descriptive evidence feature, not probability serving.
- Git status could not be read because the worktree points at a missing `Z:/content-ai/.git/worktrees/agents-content-analysis-recommendation-system`. No git metadata repair/reset was attempted.

## Follow-up: Natural Thai Narrative

- Replaced the terse X/N sentence with one paragraph combining the reference category/topic, actual cumulative-view threshold, X/N/Y/Z and the saved actionable proposal/condition. Product caveats remain intact; legacy evidence without a saved proposal uses a conditional suggestion only.
- The paragraph describes the reference cohort, not a claim that the user's clip already contains the missing topic. No new clustering, generated specs, invented Day-7 values or causal prediction. Zero-percent cohorts remain visible. Calculation, snapshots and eligibility are unchanged.
- ResultScreen passes saved ActionableAdvice by evidence topic ID; the widget never requests current Dataset text to rewrite historical proposals. Existing member list, context/time labels, limitations and separation of illustrative references remain available.
- Focused Flutter suite: 56 tests passed, including saved proposal/condition, real zero handling, legacy payloads and 390/1440 layout. Analyzer passed. Release build passed with the existing unrelated Cupertino font warning.
- Browser evidence: `artifacts/group-response-summary/20261018/browser-narrative/verification.json`. Uses the existing read-only real-data calculation via test response overlay, not a new transcription or a saved analysis rewrite. Both viewports passed; source list opened, no layout/page errors, old saved result unchanged, temporary session ended. Screenshots inspected.
- Presentation guide section 10.5 now includes a full narrative example and the distinction between topic evidence grouping and classifier/clustering predictions.
- After the final Thai whitespace adjustment, the focused 56 tests, release build and browser verification were rerun successfully. The narrative screenshots/report above are from that final build. No outstanding work within this wording change; existing Outcome Prediction blockers are unchanged.

## Follow-up: Direct View Wording and Presentation Walkthrough

- Removed the Thai pass/fail wording from the historical narrative and member list. The summary now states cumulative views directly; the benchmark is labelled as a reference value and members as above/not above that value. Equality still belongs to not above. Internal saved field names and calculation remain unchanged for compatibility.
- Expanded `docs/presentation/system-walkthrough-th.md` sections 10.2 and 10.4-10.9: pipeline, weighted median algorithm with a labelled hypothetical example, actual X/N/Y/Z example, source tables/code, frozen JSON, unavailable states, presentation script and questions about statistics versus prediction/causality.
- No classifier training, model activation, Dataset writes or historical-result migration. Historical audit counts are explicitly labelled as earlier observations, not a fresh readiness audit.
- Verification: 56 focused Flutter tests passed, analyzer clean, release build succeeded (existing Cupertino font warning unchanged). Browser checks passed at 390/1440 pixels, including reference-value labels and member status text; screenshots inspected without clipping/overlap.
- Evidence: `artifacts/group-response-summary/20261018/browser-direct-views/verification.json`. Same read-only real calculation/test-response-overlay method as earlier, not a fresh upload. Saved result unchanged; temporary auth session ended. Existing web/API on 8081/8011 reused; no process restart or extra collector launched.
- Completed this wording/documentation request. No remaining implementation work for this scope; Outcome Prediction readiness blockers remain as documented, not overridden.

## Follow-up: Six Result-Screen Removals

- Removed the quality-score suffix after classification confidence; support counts beneath recommended/opening keywords; the reason field in result advice; duration sample/minimum counts and the current-trend panel; the reference introduction; and group context/benchmark/time/caveat details plus the denominator-member expander.
- Preserved the main recommendation fields, conditional product guidance, duration median/range, historical X/N/Y/Z paragraph and illustrative reference sources. Empty/error/Unknown handling and probability gates remain unchanged.
- `ActionableAdvicePanel.showReason` defaults to true for other consumers and is false only in AnalysisReport. Trend services/models remain intact; this is display-only removal, not a request to stop collection.
- No Backend or persisted payload changes. Added report-level regression checks for all six requests at 390/1440 widths and kept parser validation tests. Updated walkthrough section 10 to distinguish retained evidence from hidden UI.
- Verification complete: full Flutter suite 233 tests passed, analyzer clean and release build succeeded. Existing unrelated Cupertino font warning remains. Browser checks passed at 390/1440 pixels; screenshots inspected without clipping/overlap. Main summary numbers and illustrative sources remain visible.
- Final evidence: `artifacts/group-response-summary/20261018/browser-simplified-confirmed-id/verification.json`. Browser test now filters only its history response to the audited Content ID and asserts the target response overlay was loaded and the saved-ID label matches. The initial `browser-simplified/` run selected a newer same-title result and is superseded by the ID-confirmed run.
- Final run uses the real read-only calculation exported earlier, not a new transcription or a new saved result. The original API payload stayed unchanged and the temporary session ended. Existing web/API on 8081/8011 reused; no collector restart or changes to reference data.
- All six requested display removals completed; no remaining work in this scope.
