# Phase 4: Current Trend Ideas

## User-facing result

- `ประเด็นจากคลิปอ้างอิง`: existing transcript-backed keyword gaps from eligible same-category reference clips.
- `ไอเดียจากกระแสล่าสุด`: a separate, conservative set of product comparison ideas from recently collected public metadata. These are not missing transcript keywords, virality scores, or promises of engagement growth.
- Each idea includes matching words actually found in the user's transcript, supporting sources, observation/publication times, a source link, and snapshot run/item IDs.

This version supports Phone, Laptop, and Camera. The active classifier remains the only category decision. Unknown and other categories abstain. A filename is never a substitute for missing speech.

## Data flow

1. The existing trend collector stores public YouTube/Google metadata in `trend_snapshot_runs` and `trend_snapshot_items`.
2. `app/services/current_trend_ideas.py` reads the latest available attempt for each platform/ranking scope. Opening/analyzing a clip does not call external trend APIs or perform a web search.
3. Recognized product-family patterns preserve model names/numbers; new model numbers do not require classifier retraining. Controlled aspect aliases connect source metadata with the actual user transcript.
4. A source must match the classifier category AND share a content aspect (battery, display, cooling, etc.) or a specific product family already mentioned by the user. Category membership alone is insufficient.
5. `app/services/recommendation.py` attaches a separate `current_trend_ideas` object. Existing reference keyword/hook/duration outputs are not mixed with metadata evidence.
6. `app/routes/analyze.py` supplies the real cleaned transcript. `save_video_analysis_result()` stores the entire recommendation, including evidence, policy and method version, in `analysis_results.summary` alongside the analysis settings.
7. The Flutter result screen displays the two sections separately. Existing saved results are not silently rewritten with today's trends.

## Freshness policy, version 1

These are explicit conservative product choices, not experimentally proven optimal windows:

| Gate | Requirement |
| --- | --- |
| Collection | Completed/partial live provider success observed within 24 hours |
| YouTube | Actual publication date within 7 days |
| Google | Provider's recorded query publication/start date within 48 hours |
| Timestamps | Missing/future timestamps are not replaced by today's date |
| Failure | Latest failed/empty/mock scope does not fall back to an older successful scope |
| Geography | Configured region, currently shared with the trend collector |
| Membership | Rank 1-50 in a selected global or category snapshot |

Publication date does not prove a new product launch or rising search volume. The UI claims only that the cited item was found in a recent source. An old video that remains popular may be excluded intentionally from this new-idea lane; this does not mean it has stopped being popular.

An idea expires at the earliest source expiry: observation plus 24 hours, YouTube publication plus 7 days, or Google query date plus 48 hours. The browser rechecks expiry every 30 seconds and on opening a saved result. Expired suggestions are hidden with an explicit expired message, rather than labeled current.

## Evidence and safety checks

- Prefer a relevant title/query. A music video with a phone advertisement in its description is not considered a phone idea.
- Descriptions are limited to the first 600 characters, stopping before outbound links and common promotional footer markers.
- Shared aspects must occur in the same sentence/paragraph as the candidate product. A real-source check caught a news description mentioning a different foldable device in a later paragraph; its display term must not be transferred to the product in the title.
- Titles about cases, chargers, mice and similar accessories are excluded from device ideas.
- Phone camera reviews do not become standalone Camera ideas; phone gaming does not become Laptop.
- Already-mentioned normalized product names are not suggested again. Product-family normalization is deliberately narrower than semantic similarity.
- Thai aspect matching preserves exact spans. The ambiguous short word `จอ` uses PyThaiNLP token boundaries to avoid matching `จอง`.
- A YouTube video present in global and category rankings counts once per idea. Google query evidence is labeled separately, never counted as another spoken-video transcript.
- `metadata_fields`, `topic_span`, and `related_evidence` retain the exact strings/offsets used; `user_evidence` points to the transcript supplied to the service.
- Sources retain timestamps, URLs, rank scope, run ID and item ID. Copying these fields into the saved result preserves the cited excerpt even after snapshot retention removes the original row.
- Database read failure returns `unavailable`; it does not prevent existing reference recommendations from being returned.
- No topics or empty-source examples are invented to fill the section.

## Limitations

The first implementation uses explicit product-family patterns and controlled feature aliases, not an unrestricted entity model. It can miss Thai transliterations, unfamiliar product families, abstract topics, and sparse titles. It intentionally shows at most four ideas, ordered by shared-aspect count and unique supporting-source count. This ordering is not a popularity or accuracy score.

An association with source metadata cannot establish that adding a topic causes more views/likes/comments. A comparison suggestion is an idea to investigate, not an assertion that the user has tested that new product or that a product is better.

This lane does not change Phase 3 title-only graph counts or combine descriptions into those historical graphs. No trend-topic registry migration, classifier retraining, paid model, new API key, or scraping plugin is needed.

## Verification

Backend tests cover freshness, unknown/missing speech, category boundaries, repeated products/videos, source field offsets, database failure, response serialization, and persistence after opening a new database session:

```powershell
python -m unittest tests.test_current_trend_ideas tests.test_phase18_unified_classification_pipeline tests.test_phase19_thai_keyword_extraction tests.test_phase20_keyword_gap_evidence tests.test_phase21_recommended_duration tests.test_full_clip_analysis tests.test_analysis_settings -q
```

Flutter tests cover old payload compatibility, current/expired states, source labels/timestamps, and reference/result regressions:

```powershell
cd frontend_flutter
flutter test test/current_trend_ideas_test.dart test/recommendation_result_test.dart test/widget_test.dart
```

`scripts/browser/verify_current_trend_ideas.cjs` tests the built web app with a temporary local admin session. It gets a fresh recommendation for an owned saved transcript through the real API, then overlays only the browser's content-detail response to preview the new UI without replacing historical database results. Populated, expired, unrelated and legacy states are explicitly browser-only fixtures; populated examples are labeled `UI fixture`, never inserted into the database. Screenshots and the verification report go under `artifacts/browser/current-trend-ideas/`; server logs go under `artifacts/logs/current-trend-ideas/`. This is UI/API verification, not an independent recommendation-accuracy evaluation.

The September 26 check of the existing Phone transcript correctly abstained after excluding a display term about a different product in a later paragraph. An empty current-ideas section can therefore be an expected evidence decision, not a failed recommendation request. Backend regression suite: 58 tests; focused Flutter suite: 14 tests. Static analysis of the changed result/model/widget files and the web build also passed.
