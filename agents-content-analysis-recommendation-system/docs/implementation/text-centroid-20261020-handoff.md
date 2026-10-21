# Text Centroid Handoff - 2026-10-20

## Request And Scope

- Keep reference Views/Likes K-Means Low/High unchanged.
- Compare a new clip by SentenceTransformer transcript embedding against the mean text vector of each KPI-labelled group.
- Never supply fabricated `(0, 0)` user KPIs or call text distance a predicted engagement probability.
- Preserve the existing saved-topic/format/age selection, reference eligibility, owner authorization, saved analysis and Train/Validation/Test splits.
- Existing partial embedding and topic-selection work was retained and completed for the active result-screen path. The unrelated automatic-overview draft is not activated.

## Completed

- Default API/repository/result panel comparison is `embedding_centroid`; explicit `tfidf` remains available for comparison, never as a silent fallback.
- Pinned local-only multilingual MiniLM revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 dimensions. No model download or classifier retraining.
- Tokenizer-aware contiguous chunks cover the complete normalized transcript, checking each chunk against the actual 128-token budget. No first-chunk truncation or 12-chunk sampling.
- Token-weighted pooling within a clip, then equal-clip mean pooling within each group, with L2 normalization.
- Signed cosine retained in [-1, 1]; cosine distance = 1 - cosine in [0, 2]. UI uses four-decimal distances, not percentages, for this method.
- Numeric ties, overlapping centroids, small distance margins and nonpositive similarity abstain. Heuristics are recorded, not claimed as validation or confidence.
- Reference vector cache keyed by transcript hash, pinned model and pooling/chunk policy. No raw transcript or user embedding persisted by this cache. Changed inputs invalidate their cache entries.
- Existing grounded High-topic advice now also works with semantic reference ranking; it still requires actual matching quotes from at least two High clips/two channels.
- Model failure preserves valid KPI clustering and reports unavailable text comparison.
- Responsive dropdown overflow fixed; switching comparison methods preserves the selected minimum views in whole-category mode.
- Legacy saved results that contain topic comparisons but predate frozen group summaries now display the explicitly labelled current whole-category comparison. A present-but-invalid summary still withholds the panel; it never broadens the requested topic cohort.
- Thai explanation and presentation narrative updated in `docs/presentation/system-walkthrough-th.md`, chapter 20.

## Real-Data Evidence

Read-only `#41 review camera`, whole Camera category, minimum 25,000 cumulative views:

- 110 candidates, 61 eligible; Low 39 / High 22.
- Distance to Low 0.3767144155; High 0.4169997487.
- Distance margin 0.0402853331; centroid-to-centroid distance 0.0090356412.
- Content closer to Low; this does not predict low engagement.
- All 2,170 reference chunks and 2 user chunks encoded.
- Saved analysis unchanged; no database writes in audit.
- Evidence: `artifacts/performance-clustering/20261020/text-centroid-audit/{audit,actual-response}.json`.
- This whole-category audit is not the denominator/result for every saved-topic cell on the UI.
- Fresh-process warm-cache audit reproduced the same distances and fingerprint in **10.948s**, including model loading: `text-centroid-warm-audit/audit.json`.

## Verification

- Backend regression: **106 tests passed** in 33.443s, including signed distances, full-text coverage, token/clip weighting, cache reuse/invalidation, abstention, missing-model fallback, fixed KPI groups, owner authorization, eligibility and existing reference/classification logic.
- Log: `artifacts/performance-clustering/20261020/text-centroid-backend-tests.txt`.
- Flutter full-suite attempt: **311 passed, 1 compilation failure** in the existing unused `automatic_performance_clustering_test.dart`/panel draft. It expects `getAutomaticPerformanceOverview`, which the repository does not expose, and its comparison override lacks `comparisonMethod`. This is not reported as an all-green full suite.
- That draft's backend service also calls unsupported private `_content`/`_reference_rows` parameters, and its test imports an absent `PerformanceOverviewResponse`. Do not wire this draft into Result without completing its separate contract.
- Full-suite log: `artifacts/performance-clustering/20261020/text-centroid-flutter-tests.txt`.
- Active-path Flutter tests: **37 passed**, including legacy vs invalid frozen-summary regression, 390/768/1280/1600 widths in both themes, method switch, threshold changes, retry, disposal and existing Result workflow. Log: `text-centroid-focused-tests.txt`.
- Analyzer of the active feature/repository/result paths: **no issues** (`text-centroid-analyze.txt`).
- Release build: **passed**, 35.3s (`text-centroid-build.txt`). Existing Cupertino font-family warning remains; this panel uses Material icons, verified visually.
- Real API/Edge browser: **all 8 width/theme combinations passed**. UI distances match API, All/Low/High filters work, original reference evidence remains, threshold empty/recovery works, stored results unchanged, temporary authentication session ended.
- Browser evidence: `artifacts/performance-clustering/20261020/text-centroid-browser-verified/verification.json` and screenshots/API payloads alongside it. No mocked KPI/classification response.
- Pixel checks: **8 charts passed**, with visible plotted points and hover tooltip pixel changes (`pixel-checks.json`). Mobile light, tablet dark and desktop light screenshots inspected for framing/overlap.
- Earlier `text-centroid-browser/` is a failed run that discovered the legacy-summary bug, not the final passing evidence; it is retained for traceability.

## Running Application

- Web: `http://127.0.0.1:8082/#/history`
- API: `http://127.0.0.1:8011`
- Open saved `#41 review camera`, then the reference evidence tab. The comparison method defaults to Text Centroid.
- Background process identities and logs: `runtime_artifacts/performance-clustering/`.

## Remaining Limitations

- Descriptive content comparison only; no independently measured predictive accuracy or calibrated outcome probability.
- Mean centroids can hide subtopics and channel imbalance. The existing cohort may already exclude lower-view clips, so Low is relative to that selected cohort, not all YouTube clips.
- Local cached model is required; absence is reported rather than automatically downloading.
- First-time encoding is slower than cached requests. References are cached, user embeddings are recomputed.
- The unused automatic-overview draft remains incomplete as described above. No attempt was made to hide its test failure or remove its files.
- Before claiming predictive superiority, compare centroid similarity against TF-IDF/nearest-neighbour baselines on genuinely held-out channels, with balanced class metrics. Do not reinterpret distance or a softmax over distances as calibrated success probability.
