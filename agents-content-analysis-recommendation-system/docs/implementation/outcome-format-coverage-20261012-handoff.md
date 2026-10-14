# Outcome Format and Coverage Audit: 2026-10-12

## Owner Update: 2026-10-13

The owner confirms that **all nine previously unresolved videos are Shorts**.
The scoped, dated evidence is saved in
`outcome-format-owner-confirmation-20261013.json`, including all Video IDs and the
original audit-report hash. This is an owner statement, not agent live-player
verification. No DB fields, old reports, or split assignments were changed.

| Category | Regular, policy inference | Shorts, original source or owner statement | Unresolved |
|---|---:|---:|---:|
| Phone | 48 | 12 | 0 |
| Camera | 25 | 33 | 0 |
| Laptop | 33 | 21 | 0 |
| Total | 106 | 66 | 0 |

The regular Fit/Tuning counts and gaps below do not improve: the newly resolved
videos are all Shorts. The earlier unresolved-status discussion below is retained
as the historical audit, superseded by this update. Do not ask the owner to
confirm these nine again.

For the illustrative restricted contexts Phone 30 to <90 days, Camera >=365 days,
and Laptop 90 to <365 days, the **count-only unfilled slots** are:

| Role | Target within these contexts | Existing count candidates | Missing slots before accepting additional data |
|---|---:|---:|---:|
| Fit | 60 (20 per category/context) | 39 (15 + 7 + 17) | 21 (5 + 13 + 3) |
| Tuning | 30 | 7 (4 + 3 + 0) | 23 |
| Calibration | 30 effective minimum | 0 accepted | 30 |
| Independent Test | 30 | 0 accepted | 30 |
| Total | 150 | 46 count candidates | 104 |

**104 is not a confirmed new-acquisition requirement**, nor a globally optimal
scope. It is a conditional count budget for this particular example, before
crediting acceptable files from the new 67 or repairing eligible existing data.
The illustrated scope has not been approved, frozen, or applied to the product.
All old roles stay unchanged; data outside this example are not deleted or moved.
The labels, rights, sampling, channel separation, and model-evaluation gates still
apply. Laptop's three additional Fit slots require three new Fit channels.

Do not announce either 21 or 104 as the exact number of new transcripts to find.
The exact number remains undetermined because no subset of the 67 is yet accepted
into the required roles/contexts. In particular, mixed/unknown sampling cannot
silently become a valid independent probability-evaluation sample. The next
useful action is to resolve those files and their provenance, not collect another
unscoped batch. No thresholds have been changed and no training was performed.

## Scope and Result

Inspected the frozen cohort of 172 existing development candidates. Preserved
all existing Train/Validation/Test identities and the existing Outcome Fit/Tuning
mapping. This is a read-only audit, not an import, training run, or activation.

**163 candidates have usable format evidence for planning; 9 remain unresolved.**
No category/age context currently reaches both Fit count minimums for regular
videos. No probability-qualified context is claimed.

The owner's confirmations remain separate:

- Old collection: selected mainly for high engagement; includes Shorts.
- New 67: regular videos according to the owner, but mixed/unknown selection
  criteria. This does not establish sampling, rights, or transcript completeness.
- A high-selected collection is not a representative sample of all YouTube videos.

## Evidence and Limits

| Category | Candidates | Regular, policy inference | Shorts, original source evidence | Unresolved |
|---|---:|---:|---:|---:|
| Phone | 60 | 48 | 7 | 5 |
| Camera | 58 | 25 | 29 | 4 |
| Laptop | 54 | 33 | 21 | 0 |
| Total | 172 | 106 | 57 | 9 |

Regular: fresh YouTube API duration exceeds 180 seconds, combined with the
[official maximum Shorts duration](https://support.google.com/youtube/answer/15424877?hl=en)
reviewed on 2026-10-12. This is an explicitly labelled policy inference, not a
direct `isShort` flag or a claim that the agent watched each video.

Shorts: the original Markdown contains an explicit `/shorts/<video_id>` source
URL; both the Video ID and normalized transcript hash match the DB candidate.
Live API identity/duration is also checked. This is documented original-source
evidence, not independent live-player confirmation. Conflicting evidence abstains.

Duration at or below 180 seconds, a `watch` URL, or a `youtu.be` link cannot by
itself establish format. The public
[video resource](https://developers.google.com/youtube/v3/docs/videos) used here
does not expose an `isShort` field. All DB format fields remain unchanged.

Original local files were exported through the existing Dart parser: 253 files,
252 parsed and 1 invalid. Format matching is restricted to the frozen 172 IDs,
not every file in the export. Source paths, URLs, hashes, metadata capture time,
duration, and evidence status are included per candidate in `format-review.csv`.

Public-page spot checks encountered HTTP 429 / a Google restriction page. Probing
stopped; no bypass, proxy, or private player endpoint was used. The nine remaining
formats require manual source review rather than further assumptions.

## Actual Observation Coverage

Regular-video candidates retain these roles:

| Category | Fit | Tuning |
|---|---:|---:|
| Phone | 38 | 10 |
| Camera | 17 | 8 |
| Laptop | 33 | 0 |
| Total | 88 | 18 |

All seven old Laptop Tuning candidates are Shorts. Do not move old Fit clips into
Tuning to fix this. Shorts still have potential value in their own contexts;
they cannot fill the regular-video minimums.

Age below uses `observed_at - published_at` from the actual existing observation,
not today's age substituted for the outcome measurement. New-batch ages are only
planning estimates at the audit time, not new outcome observations. Metric
versions are kept separate using their stored identifiers; this audit does not
revalidate the collector's metric-definition policy.

The frozen protocol requires at least 20 Fit videos and 5 Fit channels per
category/format/age/metric context, plus at least 5 videos of each outcome label.
The following gaps address **counts only**. Labels and joint topic support have
not been evaluated; counts alone do not authorize training or probability output.

| Category | Age in days | Fit videos/channels | Tuning videos | New 67 in this age band | Fit slots missing |
|---|---|---:|---:|---:|---:|
| Phone | 0 to <7 | 0/0 | 0 | 5 | 20 |
| Phone | 7 to <30 | 5/4 | 0 | 3 | 15 |
| Phone | 30 to <90 | 15/7 | 4 | 1 | 5 |
| Phone | 90 to <365 | 13/5 | 5 | 8 | 7 |
| Phone | >=365 | 5/4 | 1 | 6 | 15 |
| Camera | 0 to <7 | 0/0 | 0 | 1 | 20 |
| Camera | 7 to <30 | 2/2 | 0 | 1 | 18 |
| Camera | 30 to <90 | 2/2 | 0 | 0 | 18 |
| Camera | 90 to <365 | 6/6 | 5 | 8 | 14 |
| Camera | >=365 | 7/5 | 3 | 11 | 13 |
| Laptop | 0 to <7 | 0/0 | 0 | 3 | 20 |
| Laptop | 7 to <30 | 1/1 | 0 | 1 | 19 |
| Laptop | 30 to <90 | 9/2 | 0 | 1 | 11 |
| Laptop | 90 to <365 | 17/2 | 0 | 7 | 3 |
| Laptop | >=365 | 6/4 | 0 | 11 | 14 |

For Laptop 90 to <365, the three missing videos must also supply **three new Fit
channels**. For Laptop 30 to <90, the eleven additional videos must include at
least three new Fit channels. All role/creator separation rules still apply.

Earlier provisional all-format counts, including Camera 25 Fit videos aged
>=365 days, cannot be used as regular-video support. After format separation,
Camera has only 7 regular Fit videos in that age band.

### What the New Gaps Mean

The smallest Fit count gap per category is Phone 30 to <90: 5, Camera >=365: 13,
Laptop 90 to <365: 3. Their sum, 21, is **not a new collection quota** and is not
an automatically selected product scope. These are different age contexts; the
product must disclose any supported contexts and abstain elsewhere.

Across all age contexts there are 18 regular Tuning candidates, 12 below its
global minimum of 30. Unsupported contexts cannot be counted as evaluable Tuning
cases. For example, if only the three contexts above were eventually supported,
only 7 current Tuning candidates match them, leaving at least 23 Tuning slots.
Do not add the global gap of 12 to the restricted-context Fit gap of 21.

Calibration still needs at least 30 usable videos to satisfy three calibration
bins of 10, and Independent Test needs at least 30 with 10 per qualified category.
The separate channel, label, freshness, rights, and sampling gates also remain.
These are usable-role targets, **not an instruction to collect another 60 now**.

The new 67 have not yet supplied accepted Calibration/Test clips. They include
3 duplicate videos and 50 videos from existing channels, with overlap between
those counts. Only 17 have new IDs and no old-channel overlap; even those are not
automatically independent or complete. Camera's 21 transcripts need completeness
review, one Laptop file contains a missing-caption notice, and one Phone file
needs language/translation review. See the preceding incoming-batch Handoff.

Some remaining Fit slots may be filled by reviewing the nine unresolved formats,
repairing eligible old partial transcripts, or reviewing new files assigned to
compatible roles in a separately approved manifest. Do not silently repurpose
new holdout candidates or any old protected split.

**Exact new-collection total is intentionally null** until the nine formats,
new transcript quality, sampling frame, rights, supported scope, and identities
are resolved. Then compute missing unique eligible videos/channels per role and
context, subtracting only accepted candidates in that same role/context.

## Nine Formats Requiring Manual Review

Record source-page format, review date, reviewer, and evidence per Video ID.
Short duration alone is insufficient. These source URLs remain unresolved:

| Dataset ID | Category | Seconds | Source |
|---|---|---:|---|
| 204 | Phone | 120 | https://youtu.be/vi4uy6yjGXg |
| 206 | Phone | 60 | https://youtu.be/85zf2ZUwQAE |
| 210 | Phone | 76 | https://youtu.be/RoKt0bynSJY |
| 222 | Phone | 43 | https://youtu.be/W7lkc2Sw4Ig |
| 224 | Phone | 82 | https://youtu.be/Wga67pznHYc |
| 262 | Camera | 61 | https://youtu.be/-tljIpc7VY0 |
| 269 | Camera | 180 | https://youtu.be/T69bHRJ4Uac |
| 272 | Camera | 173 | https://youtu.be/yIPyaK4425A |
| 278 | Camera | 23 | https://youtu.be/2M5k4OWSN3c |

Seven retain Fit roles; two retain Tuning roles. Even the scenario where all nine
prove regular does not currently make any Fit context count-supported. The
scenario is exported separately and is never added to confirmed planning counts.

## Implementation and Verification

- Added `scripts/audit_outcome_format_coverage.py`, reusing the existing metadata
  client, transcript normalization, source-record construction, protocol and
  audit-permission checks, CSV protection, and SQL write guard.
- Retrieved only `snippet` and `contentDetails` in four successful API batches
  for the 172 IDs. No fresh `statistics`, labels, or Test performance requested.
- Preserved source files and all previous artifacts. Cached reruns avoid further
  API calls; output directories cannot overwrite an existing run.
- Added 12 focused tests, including unresolved-only contexts, identity/hash
  mismatch, conflicting format evidence, metric isolation, and unchanged inputs.
- Ran all 30 format/incoming/preparation tests successfully. These are software
  tests, not model-accuracy or manual-transcript-completeness results.
- Independently recomputed all 15 coverage cells from saved inputs after the
  final code change: identical to the saved report. Confirmed 172 unique IDs and
  unchanged source splits.
- No DB mutation, split reassignment, import, approval, training, activation,
  classifier extension, protocol reduction, or new outcome observation.

Audit time: `2026-10-12T16:26:59.247524+00:00` (23:26:59 Asia/Bangkok).
DB counts before/after: 472 dataset rows, 26,387 reference-statistic rows,
171 reference-statistics runs, 43 classification models. Identity hash:
`6c4e05674c48b5aaf9f85aa07d368f70f39901751a3d8d99ef837829c261e591`.
Protocol hash:
`ef3a7475e2a005b5dda4f9311eec6740570277b82204847a32114d6bdae6e12b`.

Evidence root: `artifacts/outcome-prediction/format-coverage/20261012T161912Z/`.

- `source-export.json`: original parser export, local research use only.
- `coverage-v2/report.json`: current full report and input hashes.
- `coverage-v2/format-review.csv`: evidence for all 172 candidates.
- `coverage-v2/unresolved-format.csv`: the nine pending candidates.
- `coverage-v2/regular-video-coverage.csv`: all age/context counts and scenarios.
- `coverage-v2/metadata-no-outcomes.json`: actual cached API metadata.
- `tests-stdout.log`: 30 passing tests.
- `coverage-recheck.log`: saved-count reproducibility check.

```powershell
$env:CONTENT_AI_SKIP_DB_BOOTSTRAP='1'
py -X utf8 -m unittest tests.test_outcome_format_coverage tests.test_outcome_incoming_audit tests.test_outcome_data_preparation -v
```

## Next Authorized Review Work

1. Resolve the nine formats manually without modifying old splits.
2. Audit/repair the new transcripts, recover selection evidence where possible,
   and verify data-use permissions. Keep unknown sampling unknown.
3. Agree the supported contexts using development evidence, not Test outcomes or
   whichever context maximizes a prediction. Freeze the role/channel manifest.
4. Recalculate acquisition needs from accepted candidates only. Seek separate
   approval before DB format updates, import, training, or activation.

Probability output remains blocked. Readiness work is not evidence that adding
a recommended topic causes more views.
