# Dashboard History

The public Dashboard now includes three charts, independent of AI training and
recommendations. Guests and signed-in users see the same public data.

## Charts

- Rank history: select a video or Google search topic and a 24-hour, 5-day,
  7-day, 30-day, or 90-day window. Rank 1 is at the top. An item missing from a successful Top 50
  response has no rank point; it is not assigned rank 0 or 51.
- YouTube category presence: select a category to see its share of the observed
  **global** ranking. Share = category count / total observed entries * 100.
  This is not YouTube audience market share, view growth, or search volume.
  Category-specific charts are never pooled for this calculation.
- YouTube view growth: a bar at an interval's ending time shows the selected
  video's average added views per hour. Actual delta, duration, counters and
  source IDs are available in the tooltip/evidence table. No such chart is
  manufactured for Google. See [Phase 5 decisions](dashboard-decisions-phase5.md).
- The table button exposes exact observation timestamps, selected ranks/counts,
  and original run IDs. Those IDs remain provenance even after raw run deletion.

## Data Flow

1. Existing scheduled collectors create `trend_snapshot_runs` and items.
2. In the same transaction, `archive_snapshot_run` stores the first and last
   successful live observation per UTC hour, region, platform, and ranking scope
   in `trend_history_buckets`. It retains the actual observation times and ranks,
   not averages or interpolated values.
   It also preserves available YouTube view counters, metric versions and item
   IDs. Same-run backfill can add missing fields from retained raw snapshots;
   missing counters whose source rows have been deleted remain missing.
3. Raw snapshot retention remains unchanged. Before raw deletion, archive both
   hourly observations and per-scope attempt statuses. Both archives are kept
   for 90 days; neither has a cascading FK to raw runs.
4. On startup, only real snapshots still retained from the past 90 days are
   backfilled. The process is idempotent. Deleted/offline history cannot be restored.
5. `GET /dashboard/public/history?platform=youtube&days=5` reads the archive.
   `video_category_id=20` selects only Gaming ranks. Google has no category series.
   This endpoint neither calls providers nor writes notifications.
6. The existing Dashboard polling refreshes graphs after new snapshots arrive.
   Changing filters also reads the database, not external APIs.

## Limitations

- Sampling first/last observations can miss movements between those observations.
  The page states the sampling and the actual available time range.
- More than 90 minutes between observations, or a known failed attempt between
  observations, breaks a line. A stale last sample is explicitly marked. Failure
  and mock responses never become rank/count zero. Attempt status is retained;
  hours without any observation are distinct from known provider failures.
- Successful empty responses are kept as observations with no rank points and no
  percentage denominator. A missing category in a nonempty global response is 0%.
- Google lines show the feed's order, not proof of the most searched phrase.
  Search-volume buckets are not accumulated across repeated snapshots.
- Opening a 5-day window does not imply 5 days of continuous data are available.
  History only grows while the collector is running and providers return data.

## Code And Tests

- `app/services/trend_history.py`: archive, bounded backfill and chart queries.
- `app/database/models.py`: `TrendHistoryBucket` and `TrendHistoryAttempt`.
- `app/routes/dashboard.py`: unauthenticated read-only history route.
- `frontend_flutter/lib/widgets/trend_history_panel.dart`: charts, controls, table.
- `tests/test_trend_history.py`: archive retention, gaps, scope/region separation,
  live-only data, public access, invalid filters, and actual denominators.
- `frontend_flutter/test/trend_history_test.dart`: plot values/gaps, async response
  races, period selection, empty/error states, table, and compact browser layout.

See [Phase 2 statistics history](statistics-history-phase2.md) for reference-video
counter observations, growth calculations and quota-aware collection settings.
