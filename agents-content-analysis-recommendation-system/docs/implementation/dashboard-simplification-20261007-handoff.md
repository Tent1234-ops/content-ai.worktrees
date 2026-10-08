# Dashboard / Admin simplification handoff - 2026-10-07

## Scope and completion

- Removed the latest rank-movement section from Dashboard (YouTube and the shared Google layout). Ranking metadata and snapshot collection remain intact.
- Removed public history collection diagnostics, coverage bars, hour-status dialogs, point counts, decision-summary blocks and raw evidence tables. The seven-day period, clip/category selectors, chart labels, measurement tooltips, loading/error/empty states remain. Null values and `breakBefore` still split series; missing data is never filled with zero.
- Added an unframed responsive category donut using existing `fl_chart`. Input is the selected platform's overall top-50 snapshot only, not per-category samples. It excludes non-YouTube/category-scope/out-of-range rows, deduplicates keys and calculates percentages from the actual available count. It is hidden for Google and category-filtered rankings.
- History no longer offers sorting. It preserves newest-first ordering from `/contents/my`; category filtering preserves that order. The backend currently orders by `UserContent.created_at.desc()`.
- Trend settings offers only start/end hours for daily hourly collection. All saves send `hourly_window`, with 3600-second intervals. A legacy configuration is not presented as already saved: until saving, the UI explains that the old configuration remains effective.
- Used the real Admin UI to persist the requested daily mode, preserving enabled state and existing hours. Database was independently read afterward: enabled=true, mode=hourly_window, hours=14..23 Asia/Bangkok, both intervals=3600. Ten rounds daily. Existing backend interval support remains for compatibility; it is not an option on the web form.
- Dataset quality/planning, reference statistics/growth and trash moved from always-visible tabs into the three-dot menu. Each view has a return-to-list button. No backend tool, record, soft-delete history or restore permission was removed. This follows the user's explicit allowance to retain important tools with an explanation; the optional clarification was unanswered.
- Wrote a Thai training/import guide, including Train/Validation/Test, channel isolation, CV, metrics, model artifacts, activation, import collection strategy and why the Dataset tools remain useful.

## Files

- `frontend_flutter/lib/screens/dashboard_screen.dart`
- `frontend_flutter/lib/widgets/trend_category_donut.dart` (new)
- `frontend_flutter/lib/widgets/trend_history_panel.dart`
- `frontend_flutter/lib/screens/history_screen.dart`
- `frontend_flutter/lib/widgets/trend_settings_panel.dart`
- `frontend_flutter/lib/screens/admin_datasets_screen.dart`
- Tests: `trend_category_donut_test.dart`, `history_order_test.dart` (new), updated `trend_history_test.dart`, `dashboard_screen_test.dart`, `scope_completion_test.dart`, `admin_surfaces_test.dart`
- `scripts/browser/verify_dashboard_simplification.cjs` (new)
- `docs/presentation/current-system/06-training-import-explained.md` (new), linked from that directory's README

## Verification

1. Flutter targeted suite: **42 passed**.

```powershell
C:\flutter\bin\cache\dart-sdk\bin\dart.exe C:\flutter\bin\cache\flutter_tools.snapshot test --no-pub test/trend_category_donut_test.dart test/trend_history_test.dart test/dashboard_screen_test.dart test/scope_completion_test.dart test/admin_surfaces_test.dart test/history_order_test.dart
```

Run from `frontend_flutter`. Covers actual donut values, percentages, duplicate/scope exclusion, partial/empty samples, 360/1000/1440px layouts, removed movement panel, graph gaps, API reload, newest-first filtering, daily settings/pause/validation/error persistence, Dataset restore failures and delete confirmation.

2. Backend `python -X utf8 -m unittest tests.test_trend_scheduler tests.test_scope_completion -q`: **31 passed**. Backend logic was not modified; these check real schedule persistence and collector behavior with isolated test databases.
3. `flutter_tools.snapshot analyze --no-pub`: **no issues**.
4. `flutter_tools.snapshot build web --release --no-pub`: **passed**. Existing Cupertino font tree-shaking warning remains; the release build completed successfully.
5. Real Playwright web/API check: **6 groups passed**, no captured browser exceptions, temporary Admin session revoked. Viewports 1440, 1000, 390 px. Opened trash through the new menu and returned to the list without changing datasets; saved the daily configuration through the real form and verified it through GET and an independent database session.

Latest passing evidence: `artifacts/dashboard-simplification-20261007/browser-v5/verification.json`.
Screenshots in the same directory: `donut-*`, `history-graph-*`, `ideas-*`, `datasets-*`, `datasets-menu-*`, `schedule-*`.
Inspected desktop/mobile donut, mobile history, mobile datasets, and mobile scheduling screenshots visually: no observed text overlap and charts are rendered.
`schedule-before.json` / `schedule-after.json` record the real setting transition; `training-overview.json` captures the read-only model status.

Earlier browser directories are failed/interrupted harness attempts, not final acceptance evidence. Fixes were to Flutter accessibility selectors, full-document navigation when injecting temporary auth, screenshot framing, and guarding localStorage initialization on `about:blank`. Final v5 passed all checks.

The browser harness is read-only except creation/revocation of its temporary session and an explicit `--save-daily` flag. No new ASR, training, model activation, dataset import/deletion, or analysis-result rewrite occurred.

## Important remaining limitations

- This task simplifies visualization; it does not reconstruct missing historical snapshots or certify AI quality.
- Model #43 is still registry-active but `presentation_only` and readiness=blocked (`presentation_expired`, `model_not_qualified`, `scope_policy_not_validated`). Its old grant expired 2026-10-06 23:42 Asia/Bangkok. No extension was requested in this UI task, so none was made.
- The two import choices describe collection strategy, not exclusive usage permissions. Both approved paths use `dataset_contents`; pending NotebookLM candidates are collection artifacts tracked by `dataset_collection_runs`. Training/reference eligibility, review and holdout exclusions still control actual use.
- Existing user-created results, including any incorrect historical classifications, are unchanged. The UI smoke test does not certify their predictions.
- No full application regression suite or fresh video analysis was run for this UI-only request. Targeted results above are the exact verification scope.
- Final health check: database and Whisper small ready; YouTube and Google providers report `ok`; the aggregate health status remains `degraded` because the legacy hidden TikTok provider reports error. That unrelated backend health aggregation was not changed. Static web returned HTTP 200.
- Git inspection remains unavailable because the worktree's `.git` points to missing `Z:/content-ai/.git/worktrees/agents-content-analysis-recommendation-system`. No Git repair/reset was attempted.

Web available at `http://127.0.0.1:8080/#/dashboard`; API at `http://127.0.0.1:8000`. Existing hidden dev processes remain running; no additional console windows were intentionally opened.
