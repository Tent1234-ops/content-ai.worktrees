# Phase 1: Dataset Roles And Evaluation Boundaries

## Admin

Open Admin Datasets > Quality and Collection Plan (Thai UI). The read-only
`GET /admin/datasets/readiness` endpoint is admin-only. It reads existing tables;
no database split, data deletion, relabeling or model retraining is performed.

Each row shows applicable roles, its assigned split, original source, publication
and statistics capture times, channel, duration, checks and reference exclusions.
Counts overlap: a Train clip can serve classification and recommendation.
An evaluation role means reserved membership, not necessarily quality approval.
The collection plan counts only rows that pass the existing training contract.
English clips remain stored but are excluded by the current Thai-only contract.
Transcript time beyond the recorded duration is reported, never silently fixed.

## Roles

1. Classification: human-reviewed Thai transcripts and canonical category labels
   passing `production_transcript_query`. The classifier learns from transcript,
   not popularity. Both high-response and ordinary clips are useful. Turning off
   keyword/duration recommendation eligibility does not invalidate classification.
2. Reference: a separate query requires Train membership, recommendation permission,
   reviewed provenance, matching YouTube URL/ID, known publication/capture dates
   with `published <= captured <= now`, and nonnegative recorded statistics.
   It does not require classification permission. References are historical
   observations, not automatically current or viral.
3. Current trends: actual live `trend_snapshot_runs/items`, latest successful run
   for each snapshot kind in the configured region. An observation older than
   24 hours is marked stale. This is a project freshness policy, not a claim about
   how long a trend lasts. A Dataset clip matches only by exact YouTube video ID;
   no title or keyword guessing. Google search topics are reported separately,
   never treated as transcript-bearing reference videos. Old `*_live` copies in
   `dataset_contents` alone do not prove a current trend.

## Leakage Protection

- Existing channel-based deterministic import assignment remains unchanged.
- Newly approved Validation/Test imports have recommendation flags disabled from
  the start. Existing rows are protected at query time without rewriting history.
- Validation and Test never enter keyword, Hook or duration reference pools.
- Also exclude Train rows sharing channel ID, creator group, video ID or transcript
  hash with any evaluation row, including archived/disabled evaluation records.
- The generic Admin editor cannot change assigned split, split strategy or group.
  A metadata/transcript correction preserves evaluation membership.
- References include row IDs, URLs, channel IDs, publication and capture times in
  the returned and saved evidence. Old saved analyses/models are not rewritten;
  their past evaluation is not retroactively certified by this change.

## Collection And Evaluation Plan

The initial planning targets are 80-100 reviewed clips/category, at least 10
independent channels, at least 5 Validation and 5 Test examples/category, and at
least 10 upper-pool plus 10 ordinary comparison clips for recommendation research.
These are pilot planning goals, not statistical sample-size calculations, hard
import limits or guarantees of 70% accuracy. A channel share above 40% is a warning,
not a per-channel cap. Existing model activation gates are unchanged.

The report reuses the current reference selector: same category, one compatible
view-metric version, positive performance signals, top 40% with a minimum of 10
selected when available. The remaining cohort is the comparison pool. It does
not reinterpret `collection_strategy=recommendation_high_performance` as proof
of performance, and does not rebalance by moving holdout clips into Train.

Current ranking score is `max(log1p(average_views_per_day) *
(1 + min(engagement_rate * 10, 1)), trend_score, 0)`. This legacy ranking is kept
for Phase 1; it is not a causal estimate or a fair market-wide benchmark. Ties and
small cohorts can put most/all samples in the selected group. The plan then flags
the lack of ordinary comparison clips instead of claiming diverse evidence.

Collect high-response and ordinary clips together within comparable publication
periods, ages, categories and formats; record stats capture dates and source links
for both. Keep their channels grouped from import. No automatic external fetch or
Transcript generation is triggered by this audit screen.

Use Train to fit, Validation/grouped CV to tune, and untouched Test for final
accuracy, macro F1 and per-category precision/recall. Recommendation evaluation
also uses held-out clips and a human rubric (relevance, already-mentioned concepts,
traceable evidence and unsupported claims), not classification confidence alone.
Reserve newly filmed or otherwise unseen clips for an additional external test.
If recommendation rules were repeatedly tuned using the existing Test set, collect
a fresh independent Test set; this phase cannot undo earlier information exposure.

Showing an association is not proof that adding a keyword will increase views,
likes or comments. Stronger matched comparisons and current-language evidence
belong to later phases. Metadata older than 30 days is historical, not refreshed
or disguised as realtime by a new request to this page.

## Tests

`tests/test_dataset_readiness.py` covers holdout/channel isolation, archived
holdouts, independent roles, invalid observation periods, URL mismatches, immutable
split membership, live/stale/mock trend evidence, filtering and serialized provenance.
`tests/test_scope_completion.py` checks authorization and input validation.
`frontend_flutter/test/dataset_readiness_test.dart` checks roles, plans, dates,
filters, empty states and failed reads.
