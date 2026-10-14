# Corrected NotebookLM Transcript Replacement

Date: 2026-10-14 (Asia/Bangkok)

## Request and Outcome

The owner requested replacing previously imported transcripts with corrected
files. Existing rows were updated in place instead of deleting and importing
again, preserving identity, references, statistics, and evaluation splits.

| Input folder | Files | Replaced | Held for review |
| --- | ---: | ---: | ---: |
| `Z:\Ai Content TrainTest Data\phone +20` | 20 | 19 | 1 |
| `Z:\Ai Content TrainTest Data\camera +15` | 15 | 15 | 0 |
| `Z:\Ai Content TrainTest Data\laptop +22` | 22 | 22 | 0 |
| Total | 57 | 56 | 1 |

All 57 files parsed using the production Flutter Markdown parser and matched
existing DatasetContent records by Video ID. No new records were inserted or
deleted. The database still contains 536 dataset rows.

## Remaining Item

- Dataset #529, Phone, Video ID `4TbEACxj1rI`.
- File: `Z:\Ai Content TrainTest Data\phone +20\transcript_4TbEACxj1rI.md`.
- The new body is English, whereas the existing dataset is declared Thai and
  used in the Thai-language pipeline. Its existing transcript was left intact.
- Obtain the original Thai transcript for this source, not an English
  translation or a machine translation back into Thai. Check source identity
  and text quality before replacing it. Do not change the language label merely
  to bypass validation.

Only the supplied 57 records were considered. Missing files from earlier batches,
including `LSDdOvpbj6M`, were not deleted, replaced, or implicitly approved.

## Safeguards and Provenance

- Each replacement retained Dataset ID, Video ID, original title, channel,
  category, Train/Validation/Test split, eligibility flags, license fields,
  original collection provenance, and all engagement statistics.
- Updated splits remained Train 35, Validation 6, Test 15. No split reassignment.
- Five file titles appended the existing channel name; existing database titles
  were retained. `nTU83YjVFuE` used a different title but had matching source IDs
  and the same distinctive opening. Its reviewed exception is bound to the exact
  file hash and dataset #532; this does not certify full-video accuracy.
- Version suffixes in the two Camera filenames were accepted only when the
  embedded Video ID matched the URL and existing row.
- Backed up all 57 existing rows and retained hashed snapshots of all source files.
- Used the existing `update_admin_dataset` service for normalization, hash
  recomputation, validation, and per-row correction logs. Source revision details
  were appended to `raw_metadata_json.transcript_replacements` and review notes.
- The service's per-row commits ran inside savepoints under one outer MySQL
  transaction. Both affected tables were checked for InnoDB support before writes.
- Source hashes, backup hashes, and locked database row fingerprints were checked
  before application. Any failing replacement would roll back the whole batch.
- Scope, timestamp availability, and previous eligibility were preserved, not
  newly certified. No timestamps or independent accuracy claims were invented.
- No source Markdown file was edited. No model was trained or activated.

## Verification

Independent read-back after committing confirmed:

- Exactly 56 dataset rows changed; all other 480 rows were unchanged.
- All new stored text and transcript hashes match the normalized parser output.
- Changes were restricted to transcript text/hash, review timestamp/actor,
  review notes, and appended transcript revision metadata.
- The excluded dataset #529 is unchanged.
- All original source files are unchanged.
- All 43 classification model rows and all 16 saved analysis results are unchanged.
- The Outcome model table remains unchanged (0 rows).
- One batch audit event binds the operation to its plan hash, in addition to
  correction events from the existing admin service.

Tests run with `CONTENT_AI_SKIP_DB_BOOTSTRAP=1`:

```powershell
py -X utf8 -m unittest discover -s tests -p 'test_replace_notebooklm_transcripts.py' -v
py -X utf8 -m unittest discover -s tests -p 'test_admin_dataset_correction.py' -v
```

Results: 7 new tests and 8 existing correction tests passed. Coverage includes
transaction rollback after an intermediate service commit, unchanged identity
and splits, stale-file/database guards, duplicate rejection, wrong-language and
missing-caption rejection, filename versions, and hash-bound title review.
`pytest` is not installed in the current Python environment; unittest was used
instead without installing dependencies.

## Evidence and Recovery

Evidence directory:
`artifacts/dataset-transcript-replacements/20261014-corrected-57/`

- `export.json`: all 57 records from the production Markdown parser.
- `title-reviews.json`: reviewed title exception for dataset #532.
- `operation/plan.json`: per-file checks, expected hashes, split membership,
  source snapshots, and the one exclusion.
- `operation/before.json`: full pre-change rows for all 57 matching datasets.
- `operation/source-snapshots/`: immutable copies identified by SHA-256.
- `operation/applied.json`: committed dataset IDs and post-change row snapshots.
- `operation/verified.json`: initial verification using a reopened connection.
- `operation/baseline-identities.json`: pre-change dataset/model/result fingerprints.
- `operation/final-verification.json`: final unchanged-row/model/result checks.

Do not rerun the applied plan; its result file prevents accidental repeat use.
For any future recovery, compare the current row against the recorded post-change
state before restoring transcript-related fields from the backup. Do not blindly
restore entire rows over newer statistics, reviews, or other owner changes.

Utility: `scripts/replace_notebooklm_transcripts.py`.
Tests: `tests/test_replace_notebooklm_transcripts.py`.

## Next Steps

1. Refresh Admin Dataset to see the new text on the existing records. No duplicate
   import is needed or expected.
2. Supply a Thai transcript for the excluded Phone clip when available.
3. Continue source-level word/coverage checks as required; successful replacement
   is not proof that all ASR errors are fixed or that every file covers the video.
4. Train/evaluate a new model separately when requested. The active model does
   not automatically learn from this database correction. Existing saved analysis
   results were deliberately left unchanged.
