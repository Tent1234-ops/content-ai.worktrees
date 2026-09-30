# Phase 3: Persistent Topic Evidence

## What Is Counted

Only human-approved catalog topics are counted. Phase 2 discovery proposals and
semantic similarity scores are NOT approved topics or popularity measurements.
The worker uses the context-aware title matcher from Phase 2. It needs no YouTube
request, transcript, KeyBERT inference, model download or paid API. New discovery
still runs separately using `discover_trend_topics.py`; the 659 proposals are not
silently promoted into this registry.

One video contributes at most one count to a topic in one observed ranking scope.
Repeated aliases in the same title do not add counts. Two different videos with
the same title ARE two videos in a chart (unlike deduplication for discovery).
Topics can overlap: a title mentioning two objects contributes to both, so the
sum of topic counts need not equal the number of videos. This is title coverage
within the collected ranking, not total searches, all YouTube videos, engagement,
virality, or causation. Global and category rankings are never added together.

## Tables

| Table | Purpose |
|---|---|
| `trend_topics` | Stable topic IDs; never reuse an ID for a different concept |
| `trend_topic_versions` | Immutable catalog, rule/code hashes, library versions |
| `trend_topic_definitions` | Display name and kind for each topic in each version |
| `trend_topic_aliases` | Approved alias and its context/exclusion rules per version |
| `trend_topic_configs` | Active version pointer, not mutable historical rules |
| `trend_topic_observations` | Preserved original titles/ranks/time/source run and hash |
| `trend_topic_jobs` | Durable queue, attempts, lease, error and completed state |
| `trend_topic_evidence` | Exact title, Video ID, rank, alias/context spans or unknown |
| `trend_topic_counts` | Distinct supporting videos and eligible denominator per job/topic |

These are additive tables created through the existing `Base.metadata.create_all`
startup. No existing table or historical row is deleted/relabelled. Raw snapshot
IDs are provenance references, not foreign keys, so pruning the original snapshot
does not cascade into topic evidence. Topic observations have no automatic
retention deletion yet; monitor database size before continuous production use.

## Data Flow

1. The snapshot transaction archives real provider results and writes immutable
   per-scope topic observations plus pending jobs. Failed/mocked fetches are kept
   as source states, not successful zero-count observations.
2. Commit makes the queue visible. An independent backend worker polls every five
   seconds and performs title matching; Dashboard reads never invoke extraction.
   The Windows collector also drains up to 100 jobs after its collection check,
   including when no new collection is due. No web server is needed for this path.
3. A conditional database update claims a job with a five-minute lease and token.
   Expired jobs are reclaimable after restart; an old worker cannot publish after
   ownership changes. Transient failures retry up to three times; source/build
   integrity errors fail explicitly. Job status exposes the reason.
4. Evidence, all topic counts (including legitimate zeros), and completed status
   commit atomically. Unique source/scope and observation/version constraints make
   collection replays, repeated backfill and multiple workers idempotent.
5. API reads join ONE requested version only. If any observed source in the period
   still lacks completed results for that version, no mixed/partial series is
   returned: status is `recalculation_required` with queue coverage.

Sources missing a verified Video ID/title/rank are `insufficient_source` for chart
purposes. Failed collections, removed intermediate snapshots and source gaps are
null, not zero. A confirmed empty provider response is a real observed zero.
Only real timestamps are returned; `gap_seconds_before` exposes intervals and
consumers must not interpolate or forward-fill them. Archived first/last hourly
samples cannot reconstruct the missing intermediate titles. A `missing_source`
entry records that a collection happened but its titles are no longer retained.

## Run And Inspect

```powershell
# Add tables, backfill retained real inputs, and process up to 1000 jobs.
python scripts/process_trend_topics.py --backfill --max-jobs 1000

# Read state without NLP, provider calls or mutations (tables must exist).
python scripts/process_trend_topics.py --status

# Read-only check that stored counts equal distinct evidence and spans match titles.
python scripts/audit_trend_topic_evidence.py

# Resume queued work, including expired leases from a prior process.
python scripts/process_trend_topics.py --max-jobs 1000

# A manually reviewed revised catalog creates a NEW immutable version.
# Keep IDs for renames; change alias version and never recycle IDs for new objects.
python scripts/process_trend_topics.py --catalog data/trend_topics/catalog.v2.json --activate --backfill --max-jobs 1000
```

`catalog.v2.json` is an example filename, not a shipped or automatically generated
catalog. To correct a mistaken merge, revise aliases/topics in a new catalog.
Old definitions, evidence and counts remain available by their old version ID.
To retire/merge an ID, omit it from the new catalog and explicitly reassign only
reviewed aliases; record the reason in the catalog metadata or Admin request.
Do not merge names only because their embeddings are similar.

An extractor code/library change also creates a new version, even with identical
aliases. Restart the backend/worker, then use `--activate --backfill` after such a change. Old-build jobs refuse to
run under changed code; historical completed results remain readable. Rollback
to an old catalog under new code means registering that catalog with the current
build and recomputing, not pretending the old code was used.
Activation marks unfinished older-version jobs `superseded` and fences their
workers, preserving their audit rows and completed results. It never copies
their counts to the new version.

## API

- `GET /dashboard/public/topics/history?region=TH&scope=global&days=5`
- `GET /dashboard/public/topics/history?scope=category:20&days=5&version_id=<hash>`
- `GET /dashboard/public/topics/evidence/<job_id>`
- `GET /admin/trend-topics/status` (Admin login required)
- `POST /admin/trend-topics/versions` with `{catalog: {...}, reason: "..."}`
- `POST /admin/trend-topics/versions/<hash>/activate`

Registration alone does not activate a version. Activation queues all preserved
observations for that version; the worker calculates them in the background.
Registry changes and processing errors appear in `system_logs`. Public evidence
contains only public source titles, URLs, ranks and extraction evidence, never
user-uploaded files or private analysis results.

No new public chart or Admin review screen is part of this phase. This API is the
prepared read surface for the next chart phase. Human evaluation labels remain
untouched and no accuracy percentage is inferred from topic counts. Production
counting may process test-set video IDs as ordinary frozen-rule inference; such
outputs must not be used to tune the rules or claim independent evaluation.

## Verification

```powershell
python -m unittest tests.test_trend_topic_storage tests.test_trend_topics tests.test_trend_topic_preparation tests.test_trend_history tests.test_live_trend_snapshots tests.test_trend_scheduler tests.test_reference_statistics -q
```

Tests cover immutable replays, exact evidence, ID deduplication, scope separation,
unknown titles, version changes, incomplete-period gating, null gaps, leases,
transaction rollback, source/code integrity, raw deletion, persisted restart and
public-read/Admin-access boundaries.
