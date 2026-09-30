# Phase 2: Reference Statistics And Long-Term Trend History

## Admin And Scheduling

Admin Datasets > Statistics and Growth (Thai UI) shows cumulative counts,
observed differences, timestamps, source links, collection runs, and settings.
Settings persist in `reference_statistics_configs`. Default: enabled, hourly,
100 videos.list requests per Thai calendar day for this collector only.
The existing backend worker and Windows scheduler both invoke it. Automatic work
respects the trend pause and the configured daily window (currently 14:00-23:00).
No web page GET makes a YouTube request. Manual refresh queues a background job.
There is no new transcript, label, channel split or classifier training step.

`videos.list(part=statistics,id=...)` batches at most 50 IDs. The collector requests
all Phase 1 reference-eligible clips, not just the upper-performance group. Held-out
clips and overlapping evaluation channels remain excluded. Calls are reserved in
the database before network I/O, including failures, and serialized across workers
with a MySQL named lock. Pauses/settings are re-read before each batch.

The daily cap belongs to this collector, not Google's project-wide quota meter.
An effective interval is increased when the configured cap cannot cover the
requested rounds. When only part of a pool fits, oldest-observed clips go first
on the next collection. A provider quota error pauses this collector for 24 hours
(a conservative cooldown, not a claim about the exact provider reset time).
Manual refresh also obeys the cap/cooldown and a 60-second minimum retry interval.

For 117 eligible clips, a complete refresh is 3 requests; ten hourly rounds are
about 30 units/day, before failures/manual jobs. The current 12 category charts
plus one global YouTube chart add about 130 videos.list calls for ten rounds,
plus category discovery/cache misses and other application usage. Google Trends
HTTP requests do not consume YouTube quota. These are estimates, not measured
remaining Google Cloud quota. See the official [videos.list reference](https://developers.google.com/youtube/v3/docs/videos/list)
for the request parameters and 1-unit request cost.

## Persistent Tables

- `reference_statistics_configs`: enabled state, interval, daily cap, cooldown.
- `reference_statistics_runs`: attempts, statuses, actual requests reserved,
  candidate count and sanitized failure reason; persists after restarts.
- `reference_video_statistics`: append-only observations with Dataset ID, Video
  ID, source URL, collection time, metric version and nullable counters.
- `trend_history_buckets`: existing first/last actual observation each hour;
  retention increased from 7 to 90 days. Ranks are not averaged.
- `trend_history_attempts`: successful/failed/excluded attempts per provider,
  region and ranking scope; no FK to raw snapshots, retained 90 days.

New tables are created by the existing startup/standalone schema initialization.
An idempotent MySQL migration widens dataset views/likes/comments to BIGINT.
It does not delete data or change transcripts. Complete fresh counter bundles
also update the existing Dataset fields used by recommendations. Partial bundles
stay in history and do not mix new views with old likes under one new timestamp.
Historical saved analysis evidence is not rewritten.

## What Growth Means

For consecutive compatible observations:

`increase = later count - earlier count`

`average increase/hour = increase / actual elapsed hours`

Example: 1,000 to 1,600 views in two hours means +600, averaging 300/hour.
This is different from cumulative views or lifetime average views/day. It does
not prove that a keyword caused higher engagement or that growth was constant.
A long elapsed interval is reported as such, never presented as realtime growth.

One observation: insufficient evidence. Missing/hidden fields: null, not zero.
Failed or unavailable video: preserve the failure and break the growth chain.
Counter decreases: retain the signed difference but do not label a negative rate
as ordinary growth. Different Video IDs or incompatible metric versions cannot
be compared. Zero increase is displayed only after two real compatible counts.
Statistics history starts with new collection; no historical values are invented
from the current total. The import's latest-value row is not relabeled as a new
API observation. No external search/download/transcription is used.

## Trend Gaps And Retention

Before deleting raw snapshots, archive their first/last hourly samples and
attempt status in the same transaction. Failed scopes never contribute rank 0
or a category count of 0. Confirmed successful empty responses are distinct.
Charts support 1/5/7/30/90 days; missing hours are `no_observation`, not provider
failure. Those hours can include a switched-off PC or hours outside the schedule.
Known failed attempts are explicitly recorded and break chart lines, even for
failures less than 90 minutes apart. Scope/category/platform/region never mix.
Restart backfill uses only raw snapshots that still exist, including failures.
Already-deleted older history cannot be recovered or manufactured.

## Verification

Focused tests cover batching, quota/cooldown, restarting sessions, holdout
isolation, partial/missing/corrected counters, metric changes, unchanged
transcripts, archive-before-delete, retained failures, chart gaps and admin-only
access. Flutter tests cover missing/growth states, settings, source history and
error retry. Live API results depend on provider availability; a successful
database write must never be confused with a successful provider response.
