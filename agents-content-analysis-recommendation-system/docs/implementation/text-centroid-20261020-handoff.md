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

## Verification

- Backend regression: **105 tests passed** in 34.936s, including signed distances, full-text coverage, token/clip weighting, abstention, missing-model fallback, fixed KPI groups, owner authorization, eligibility and existing reference/classification logic.
- Log: `artifacts/performance-clustering/20261020/text-centroid-backend-tests.txt`.
- Flutter full-suite attempt: **311 passed, 1 compilation failure** in the existing unused `automatic_performance_clustering_test.dart`/panel draft. It expects `getAutomaticPerformanceOverview`, which the repository does not expose, and its comparison override lacks `comparisonMethod`. This is not reported as an all-green full suite.
- That draft's backend service also calls unsupported private `_content`/`_reference_rows` parameters, and its test imports an absent `PerformanceOverviewResponse`. Do not wire this draft into Result without completing its separate contract.
- Full-suite log: `artifacts/performance-clustering/20261020/text-centroid-flutter-tests.txt`.
- Active-path focused tests, analyzer, release build and browser verification: pending final run below.

## Remaining Limitations

- Descriptive content comparison only; no independently measured predictive accuracy or calibrated outcome probability.
- Mean centroids can hide subtopics and channel imbalance. The existing cohort may already exclude lower-view clips, so Low is relative to that selected cohort, not all YouTube clips.
- Local cached model is required; absence is reported rather than automatically downloading.
- First-time encoding is slower than cached requests. References are cached, user embeddings are recomputed.
- The unused automatic-overview draft remains incomplete as described above. No attempt was made to hide its test failure or remove its files.
