# Dashboard Refresh Handoff - 2026-10-03

## Scope

Newest user request supersedes the earlier delivery freeze: seven-day history,
hide the paused TikTok integration, move personal lists into top-right dialogs,
and make three real Whisper models selectable. No classifier, training dataset,
recommendation policy or subsequent project phase was changed.

## Diagnosis

- The persisted collection window is 14:00-23:00 Asia/Bangkok, hourly, ten rounds
  per day. It is not a 24-hour collection schedule.
- Database inspection found ten observed global hours per platform on Sep 30,
  Oct 1 and Oct 2. Sep 27 and Sep 29 had seven. Collection continued on Oct 3.
- An initial rolling-seven-day query returned 63 observations, but the default
  newest rank-1 video appeared in only 13. A missing video and a missing
  collection are different causes of blank chart regions.
- The current calendar-seven-day API returned 58 observed hours at 17:00 on
  Oct 3. The new initial video had 45 observations. Counts will keep changing.
- Overnight/offline observations cannot be recreated by requesting today's
  provider ranking. No timestamps, ranks, view counts or backdated rows were
  invented. Actual failed attempts and line breaks remain visible.

## Implemented

- Dashboard history uses seven Bangkok calendar dates including today. Removed
  24-hour, five-day, 30-day and 90-day UI choices. Legacy explicit API periods
  remain compatible; API/repository defaults are seven days.
- Added daily observed-hour coverage, failed-attempt counts and the current
  collection window. The current window is not retroactively treated as the
  schedule of old dates. Today's coverage is partial; future hours are not gaps.
- Initial graph selection prefers the most-observed video/query still in the
  latest ranking. The ranking list is unchanged. Explicit selection wins, and
  each selector item displays its observation count.
- A single valid rank observation now appears as a point instead of being
  hidden behind an insufficient-data placeholder. It cannot establish movement.
- TikTok removed from Dashboard tabs, displayed platform lists, manual sync
  list, default scheduled collection and new notification comparison. Legacy
  payload fields, stored rows and explicit provider APIs remain compatible.
- Notification bell opens a scrollable inbox with individual/batch read actions.
  Bookmark button opens followed topics with removal and an expandable category
  preferences section. The former inline sections are removed from Dashboard.
- Dialogs load current data, retain rows on failed writes, show retry errors,
  refresh Dashboard after close, and hide private data after logout/user change.
- Downloaded actual `medium` and `large-v3` weights beside existing `small` in
  `models_cache/faster_whisper/`. Admin still enables only installed options.
  Kept the persisted default `small`; no settings/model activation was faked.
- Added `--verify-load` to `scripts/setup_faster_whisper.py`: optionally loads
  weights and runs a brief local inference smoke test after readiness checking.

## Verification

- `python -m unittest discover -s tests`: 487 passed.
- Flutter full test suite: 126 passed.
- Flutter analyze: no issues.
- Flutter release build: passed, API base `http://127.0.0.1:8000`.
- `python scripts/setup_faster_whisper.py --model medium --verify-only --verify-load`:
  passed local loading and inference.
- Same command with `large-v3` and `small`: passed local loading and inference.
- These ASR smoke tests verify executable models, not transcription accuracy.
- Real API/DB check: seven daily coverage records, real graph observations and
  default selection with more historical evidence.
- Browser checks passed at 1440x1000 and 1000x850 against the real API/Database:
  YouTube/Google tabs, seven-day coverage, notification/followed-topic dialogs,
  and three enabled Whisper choices. No rendering/overflow errors recorded.
  Final evidence: `artifacts/dashboard-refresh/2026-10-03T10-45-15-919Z/verification.json`.
  All 14 screenshots captured. Visually checked the actual rank/growth charts,
  coverage at compact web width, both personal dialogs and enabled model menu.
  An earlier browser run failed to locate Flutter's merged semantics; the test
  locator was corrected. That failed artifact was preserved, not counted as a pass.

## Try the Updated Build

- Web: `http://127.0.0.1:8080/#/dashboard`
- API: `http://127.0.0.1:8000/health`
- Both servers were started hidden with `scripts/start_demo.ps1` and responded
  HTTP 200. They are intentionally left running for the user.
- Use `scripts/stop_demo.ps1` to stop the launcher-owned demo servers.

## Remaining Limits

- Continuous overnight history requires an always-on collector host. Windows
  Scheduler cannot collect while the machine/database/network is unavailable.
- Collection cadence was not increased; provider quota is not spent to invent
  missing history. No automatic replay of old slots was introduced.
- Real data can still have gaps. The chart never connects known collection
  failures or absence of the selected item to imply uninterrupted measurement.
- Previously published release manifests/backups describe the old release.
  A delivery machine must provision the newly added model directories separately
  or run the existing setup command for each model.
- Git status is unavailable because the worktree points to missing
  `Z:/content-ai/.git/worktrees/agents-content-analysis-recommendation-system`.
  This unrelated Git metadata was not altered.
