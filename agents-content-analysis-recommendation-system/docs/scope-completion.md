# Remaining Web Scope: Statistics, Interests, Dataset Deletion, Trend Schedule

## Where To Find It

| Feature | Web location | API |
| --- | --- | --- |
| Personal daily/monthly statistics | My Ideas & History | `GET /contents/statistics?year=2026&month=9` |
| All-user statistics | Admin Users, statistics icon | `GET /admin/usage-statistics?year=2026` |
| Follow YouTube categories and choose notification mode | Dashboard, below trend lists, signed-in only | `/follows/topic`, `/follows/topics`, `/follows/preferences` |
| Remove a dataset from use | Admin Datasets, trash icon and confirmation | `DELETE /admin/datasets/{id}?confirmation_id={id}` |
| Automatic trend schedule | Admin Analysis Settings, second tab | `GET/PUT /admin/trend-settings` |

## Data Rules

### Statistics

- Count saved `analysis_results`, joined to `user_contents` for ownership. These are NOT upload attempts, failed jobs, or page visits.
- A `month` parameter selects daily buckets. Omitting it selects 12 monthly buckets for the year.
- Bucket boundaries use Asia/Bangkok (UTC+7); SQL filters use the corresponding UTC interval, including the start and excluding the end.
- Days/months with zero saved results remain visible. Unknown classifications have their own category.
- Personal statistics never accept another user's ID. The all-user endpoint is admin-only.
- History's list remains the latest 50 saved contents; the statistics cover the entire selected period, not just the currently loaded list.

### Interests And Notifications

- Categories use the 12 configured YouTube category IDs, not the Phone/Camera/Laptop classifier taxonomy.
- `followed_topics.platform` scopes a follow to a provider. Existing title/keyword follows default to `all` for compatibility.
- Category matching uses provider category ID, with the provider category title as fallback for older global snapshots.
- Existing keyword follows match title metadata only. They do not claim to read a trending video's transcript.
- `system_configs.trend_notification_mode` on the user's row is `all`, `following`, or `off`.
- Category notifications compare successful snapshots of that same category. Failed snapshots do not replace its comparison baseline.
- The first snapshot establishes a baseline, not 50 new alerts. New follows do not replay events captured before the follow.
- Changing notification mode moves the cursors to current snapshots, avoiding a backlog from a disabled period.
- A trend appears at most once per watch session, even when found in both global and category rankings.
- This is the existing signed-in, Dashboard-polling notification workflow. There is no offline push notification delivery in this change.

### Dataset Removal

- Deletion sets `dataset_contents.deleted_at`, turns off `is_active`, and clears all three training/recommendation eligibility flags.
- Admin and source dataset lists exclude deleted rows. Training, out-of-scope evaluation and recommendation queries also exclude them.
- Saved analysis foreign keys, review evidence and previously generated model artifacts stay intact.
- Updates and review approvals cannot reactivate an archived row. Duplicate provenance identifiers remain reserved.
- Already-trained models do not forget a row automatically: train and activate a replacement to change their learned behavior. An already-running job may retain its captured input.
- The audit event is `admin_dataset_delete`. This is removal from active use, not permanent destruction of historical evidence.

### Trend Schedule

- The global `system_configs` row stores enabled/paused state, global refresh seconds and YouTube category refresh seconds.
- Both intervals allow 60 through 86400 seconds. Until first saved, existing environment defaults apply.
- The fetcher re-reads configuration every five seconds and starts provider requests only when due. In-flight requests are not cancelled.
- It re-checks the configuration before each job. Pausing during a slow global request prevents the next category request; a failed global request does not starve category refreshes.
- Scheduling uses the most recent persisted attempt per snapshot kind and region, including failed attempts, so failures/restarts do not reset the rate limit.
- Browser polling remains 60 seconds and reads stored snapshots; it does not request YouTube again.
- The switch pauses automatic fetching only. Deliberate manual refresh actions retain their existing rate limits.
- This scheduler is designed for the existing single-backend-process deployment, not multiple independent API workers.
- NotebookLM import and training data durations are unaffected.

## Main Implementation Files

- `app/services/usage_statistics.py`: ownership filtering and calendar buckets.
- `app/services/follows.py`: validated follows, preferences and metadata matching.
- `app/services/category_interest_notifications.py`: category-specific snapshot comparisons.
- `app/services/live_trend_notifications.py`: shared session and notification deduplication.
- `app/services/admin_report.py`: archive operation and admin list/update guards.
- `app/services/trend_settings.py`: persisted configuration and due calculations.
- `app/services/trending_fetcher.py`: polling persisted settings and executing due jobs.
- `app/database/migrations.py`: additive, repeatable `migrate_scope_completion_schema`, invoked during API initialization.

## Verification

```powershell
python -m unittest tests.test_scope_completion tests.test_live_trend_snapshots tests.test_admin_dataset_correction tests.test_analysis_settings tests.test_user_management tests.test_model_management tests.test_public_dashboard_access
cd frontend_flutter
flutter test --reporter expanded
flutter build web --dart-define=API_BASE_URL=http://127.0.0.1:8001
```

`artifacts/verify_scope_browser.cjs` exercises the live local web/API using disposable records. It restores the effective schedule, removes its own test records and expires its temporary admin session in cleanup. Screenshots and the final check report are generated under `artifacts/scope-*`.

### Verified 2026-09-19

- 75 targeted backend regression tests passed.
- All 62 Flutter tests passed; web release build passed.
- Edge browser checks passed for daily/monthly statistics, saved category follows, notification preferences, persisted intervals, dataset deletion preserving history and admin statistics.
- Inspected screenshots at 1440px and 850px browser widths. No browser page errors were reported.
- Flutter analyzer reports only five pre-existing informational findings in `lib/main.dart` (deprecated theme properties and const constructors).
- Live API schema initialization reports `ok`. Original global/category intervals were restored to 60 seconds after browser verification.
