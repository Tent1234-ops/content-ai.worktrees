# Performance Clustering Handoff - 2026-10-19 / 2026-10-20

## Scope

User brief: K-Means (K=2) using reference Views/Likes, shared-space TF-IDF/Cosine for user text, Result Evidence UI, grounded suggestions and tests. No classifier/training pipeline changes, no split moves, no invented KPIs/probabilities, no database migration.

## Implemented

- `app/services/performance_clustering.py`: existing eligibility/taxonomy/NLP/statistics/alias APIs; latest 24h observation; explicit missing/failure handling; dedup; log1p/scaler/sklearn KMeans; centroid-based naming; equal Top-K similarity and abstention; quoted High-group evidence.
- `app/schemas/performance_clustering.py`: versioned API response and bounded similarity values.
- `app/routes/contents.py`: owner-scoped GET `/contents/{id}/performance-clustering`, optional `minimum_views` (0..2^53-1).
- `app/core/config.py`: environment default `PERFORMANCE_MINIMUM_VIEWS=25000`.
- Flutter model/repository/panel/result: lazy Evidence-tab request, 30s timeout/retry, live-data label, validated metrics, threshold, scatter/tooltips, Low/High averages+medians, similarity bars, grounded topics, paginated All/Low/High references. Existing saved evidence remains separate.
- `tests/test_performance_clustering.py`: 15 calculation + SQLite/API integration tests, actual ownership and no saved-analysis mutation.
- `frontend_flutter/test/performance_clustering_test.dart`: parser, 8 responsive/theme cases, filters, tooltip content, threshold, inconclusive, retry, disposal.
- Updated Result workspace tests to mock the new endpoint and assert lazy loading without altering existing expectations.
- `scripts/verification/performance_clustering_audit.py`: database writes rejected during actual-content audit.
- `scripts/browser/verify_performance_clustering.cjs`: actual authenticated saved content/API checks, screenshot matrix and threshold changes; only history navigation is filtered to ID41, no mock KPI/analysis response.
- `docs/presentation/system-walkthrough-th.md` chapter20: data/tables, formulas, policy, real result, live-vs-saved distinction, limitations and presentation narrative.

## Verified So Far

- Backend relevant regression: **91 passed**, including 15 new tests, reference statistics, topic comparisons, evidence, saved payloads, category pipeline, acceptance and holdout protections.
- Read-only actual audit: `artifacts/performance-clustering/20261019/audit.json`, `actual-response.json`; no saved analysis writes.
- #41 Camera: 110 candidates, 61 eligible (39 Low /22 High), minimum25k; 3 insufficient transcripts,46 below threshold. Similarity10.1395%/7.6262%, K5, `inconclusive` (gap2.51pp <3pp). Do not change thresholds to force a group.
- First complete Flutter regression exposed an obsolete Result test double: new request was not mocked and timed out. Corrected test double without weakening assertions.
- Final complete Flutter regression: **308 passed**, `artifacts/performance-clustering/20261020/flutter-tests-final.txt`. Focused panel/Result run:32 passed, `flutter-focused.txt` in the same directory.
- Final analyzer: **No issues found**, `artifacts/performance-clustering/20261020/analyze.txt`.
- Final release build: `frontend_flutter/build/performance-clustering`, `artifacts/performance-clustering/20261020/build-final.txt`. Earlier full compile had the pre-existing unused CupertinoIcons font warning; Material icons render normally.
- Fixed chart accessibility boundary and overlapping-point tooltip identity. Tooltip now identifies the actual point by index, not the first row with matching coordinates; covered in all8 chart layout/theme tests.

## Browser Verification Pending

- Full actual Edge8-layout/theme run and final pixel-check report are in progress. Earlier partial runs verified4 mobile/tablet cases; harness fixes scroll offscreen Flutter semantics before waiting, and uses a45s response wait around navigation (the application still has30s request timeout). Do not use partial verification reports as a full pass.

## Runtime

- Web: `http://127.0.0.1:8082/#/history` (login, open a saved result, Evidence tab).
- API: `http://127.0.0.1:8011/health`. The previously owned API PID7252 was identity-checked and replaced, not duplicated.
- API PID16812, start `2026-10-19T15:24:11.0627357Z`; web PID1008, start `2026-10-19T15:27:14.9193893Z`. Verify identity/health before stopping/restarting. Runtime state/logs: `runtime_artifacts/performance-clustering/`.
- Old web8081 remains available with its previous UI build. Use8082 to inspect this feature.
- No source videos were uploaded or ASR rerun in this task; browser tests use actual saved content41. Temporary browser sessions are logged out after each completed run; the interrupted initial run was not used as verification evidence.

## Design Boundaries / Risks

- Relative, descriptive groups within an already selected sample above threshold, not universal performance labels.
- Cumulative Views/Likes are not age-, channel- or format-controlled. Does not replace the separate controlled historical comparisons.
- Similarity heuristics0.10/min margin0.03 are uncalibrated, versioned, independent of classifier thresholds. Equal K removes direct sum bias, not all candidate-pool bias.
- Reference space only, no user KPI, one vectorizer; empty/weak/tied/partial inputs abstain. No outcome probability or guaranteed uplift.
- Low/High is from centroid score(mean standardized log KPI); inverse centroid is not arithmetic average.
- New comparison is live/read-only with data fingerprint and observation IDs, not frozen into saved analyses. Original evidence snapshots remain untouched.
- Data use follows existing reference eligibility; this does not assert new rights or resolve the separate Outcome data-use/evaluation contract.
- Existing Git worktree pointer is broken (`Z:/content-ai/.git/worktrees/...` missing). No reset/repair/revert performed.
