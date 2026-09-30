# Phase 6: UI consistency and admin data care

## Screens

- `/result`: findings, suggestions, then reasons. Raw and cleaned transcripts,
  per-topic Dataset evidence and analysis settings are expandable. Empty results
  do not imply that a clip already covers every useful topic. Classification
  confidence is not presented as a clip quality score.
- `/admin-datasets`: metadata checks on each row, existing readiness and
  reference-statistics tabs, plus a trash tab with confirmed restoration.
- `/admin-analysis-settings`: the existing trend settings tab also shows stored
  source collection outcomes. No extra admin console was added.

`frontend_flutter/lib/ui/app_theme.dart` provides shared typography, color,
input, button, table and panel defaults. `AppShell` constrains large web layouts
to 1600 pixels. Existing Material icons and actual content images are retained.
The analysis report uses full-width sections with optional evidence, rather than
an always-expanded evidence card. No classifier or recommendation scores are
retrained or recalculated by this presentation change.

## Dataset lifecycle

Deletion remains a soft delete. Before disabling a row, the server saves its
active, training, keyword-reference and duration-reference flags in
`dataset_contents.deletion_state_json`. The existing startup schema migration
adds that nullable column without rewriting existing Dataset contents.

Admin endpoints:

- `GET /admin/datasets?trashed=true` lists archived rows.
- `DELETE /admin/datasets/{id}?confirmation_id={id}` archives an active row.
- `POST /admin/datasets/{id}/restore?confirmation_id={id}` restores an archived
  row after checking the current training contract.

Transcript, hash, category, split, channel and audit evidence stay intact.
Mutations lock the row and commit the change and success log together. Failure
rolls back both. A repeated restore returns 404 rather than creating another
success event. Frontend mutation responses must confirm the requested ID and
state before showing success.

Older deletions have no prior flag backup. Restoring them enables visibility but
does not infer training or recommendation eligibility. The normal review and
eligibility rules still apply. Neither deleting nor restoring a row changes an
already trained model artifact; that requires training and activation again.

Quality labels reuse the existing readiness checks. They describe metadata
completeness and declared eligibility, not transcript correctness, engagement
quality or model accuracy. Legacy trend-only rows are identified separately.

## Source health

`GET /admin/sources/health` is admin-only. It reads `trend_history_attempts`,
separately for the configured region, global YouTube, global Google and each
configured YouTube category. It reports last attempt, last successful sample,
run ID, sample count and success/failure counts over 24 hours.

The UI distinguishes missing history, a failed collection, an empty response,
mock data and samples older than 24 hours. This is a stored collection status,
not a live connection probe. Opening the page makes no provider API calls and
does not expose credentials. A failed page request is not shown as healthy.

## Persistence and user feedback

The upload flow still persists analyses through its existing API. The result
screen only claims an idea is saved when its response includes a saved flag and
content ID. The old local-only Save action and the history action that merely
removed an item from the screen have been removed; no unsupported operation
claims database success. Existing history items still open their saved results.

The Dataset editor handles Cancel without a dialog result type error, validates
numeric fields, and stays open when an update fails. Loading, retry and empty
states are explicit on the result, Dataset and source-health views.

## Verification

Backend regression coverage:

```powershell
python -m unittest tests.test_admin_dataset_correction tests.test_scope_completion tests.test_source_health tests.test_dataset_readiness tests.test_analysis_settings tests.test_current_trend_ideas tests.test_reference_statistics -q
```

Frontend tests include isolated API acknowledgement checks, failed and successful
restores, editor cancellation, source-health retry, compact light/dark result
layouts and expandable evidence. Run `flutter test` in `frontend_flutter`.

`scripts/browser/verify_phase6_ui.cjs` checks real saved results and admin read
endpoints at desktop and compact web widths. It creates a short-lived local
authenticated verification session but does not mutate Dataset rows. Browser
screenshots and its report go into `artifacts/browser/phase6/`; tokens are not
included. Delete/restore persistence and commit failures are exercised against
isolated test databases, not the user's live Dataset.
