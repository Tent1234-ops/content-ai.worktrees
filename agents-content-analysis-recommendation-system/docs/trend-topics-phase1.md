# Trend Topics Phase 1: Source Readiness

This phase prepares evidence and a human evaluation set. It does not extract
topics, claim an accuracy result, change AI classification, or add public charts.

Thai annotation instructions: [คู่มือระบุหัวข้อ](trend-topic-labeling-th.md).

## Run

From the project root:

```powershell
python scripts/prepare_trend_topics.py export --days 90 --size 200 --test-size 100
python scripts/prepare_trend_topics.py validate --bundle artifacts/trend-topics/evaluation/EXPORT_DIRECTORY
python scripts/prepare_trend_topics.py validate --bundle artifacts/trend-topics/evaluation/EXPORT_DIRECTORY --require-complete
```

The export reads the existing database; it does not collect new videos or write
data rows. This CLI disables import-time schema bootstrap with
`CONTENT_AI_SKIP_DB_BOOTSTRAP=1`; the normal server default is unchanged.
A fresh timestamped directory is used and existing sets cannot be
overwritten. Export again only to make a new evaluation version, not to improve
a score by repeatedly changing the held-out sample.

## Outputs

- `audit.md`: source coverage, missing metadata, split sizes and limitations.
- `audit.json`: machine-readable per-platform/per-scope audit and hourly intervals.
- `observations.jsonl`: deduplicated raw/archive evidence, actual titles and ranks.
  This contains held-out evidence too; it is NOT a development/training input.
- `development/samples.jsonl`, `test/samples.jsonl`: frozen source/provenance rows.
- `development/labels.csv`, `test/labels.csv`: initially blank HUMAN annotations.
- `manifest.json`: source hashes, fixed assignment, seed and extraction contract.
- `heldout_video_ids.json`: denylist for future discovery/tuning, without test titles.
- `ANNOTATION_GUIDE.md`: labeling instructions and how to protect the held-out set.

Label CSV statuses are pending, labeled, no_topic, or ambiguous. Topic and evidence
columns contain parallel JSON arrays. Evidence must be an exact title excerpt;
completed rows need an annotator. No-topic and ambiguous rows have empty arrays.
Ambiguity requires a note. Pending labels are not usable ground truth.

## Contract

`trend-topics-title-only-v1` permits ONLY the original title as extraction input.
Hashtags appearing in the title are part of that title. Description, separate tags,
category, thumbnail, channel, rank and counters are not additional model features.
Category is used only for sampling coverage. Human annotators must not watch the
linked video or infer missing topics from the description.

Input titles are not spell-corrected or domain-normalized. NFKC, whitespace and
case normalization are used only for duplicate-title fingerprints. Original
titles and their SHA-256 hashes are retained. Annotation CSV protects titles
beginning with spreadsheet formula prefixes without changing original JSONL.

## Sources And Identity

Read `trend_snapshot_runs/items`, `trend_history_buckets` and
`trend_history_attempts`. Exclude known mock and failed observations. Merge raw
and archived copies by platform, ranking scope and run ID, within one region.
Keep the archive's original title/rank when both exist. Audit both raw and archived
sample counts: retained raw rows include intrahour samples absent from the archive.

The legacy archive stored a SHA-1 trend key, not a recoverable Video ID. Resolve
old identities only via an unambiguous key-to-valid-YouTube-URL lookup from retained
evidence. Never guess a URL from a title or case-fold a YouTube Video ID. Exclude
unresolved identities from evaluation and report them. Matching descriptive
metadata may only come from the SAME observation, not a later video version.

New archived observations also preserve source URL and channel title. Startup
backfill can enrich still-retained raw observations; already deleted source data
cannot be recreated. No schema migration is needed for these optional JSON fields.

Coverage separates each platform and ranking scope. Hourly intervals distinguish
observed, partial (observation plus failure), failed, and no_observation. Missing
hours include offline time, periods before collection began and inactive schedule
hours; they are not automatically errors. Fewer than 50 returned rows does not by
itself mean an API failure. No zeroes or intermediate rankings are invented.

## Sampling And Holdout

Select up to 200 verified unique YouTube Video IDs, balanced across available
categories, with a soft preference for diverse channel titles. Small categories
remain small; redistribute available capacity and report any final shortfall.
Use one latest observed title per video. Avoid selecting another video sharing
any normalized title variant with an already selected video.

Deterministically allocate approximately half per category to development and
half to test. The default target is exactly 100/100 when 200 distinct examples
are available. Both splits share a contract but never a Video ID or title variant.
Do not use test titles, their aliases or annotations to tune discovery. This is
a video/title-held-out benchmark, NOT a channel- or future-time-held-out benchmark.
The balanced set is not representative enough to estimate platform popularity.

Freeze candidate extraction, aliases and model settings using development only.
Have a human annotate/review the test set independently where possible. Report
precision, recall and abstentions only AFTER annotation and frozen-rule evaluation.
Source hashes are accidental-change checks, not a security boundary.

## Tests

```powershell
python -m unittest tests.test_trend_topic_preparation tests.test_trend_history -q
```
