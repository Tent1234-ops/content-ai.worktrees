# Daily Trend Collector

The daily mode collects once per hour from 14:00 through 23:00 Asia/Bangkok,
10 collection rounds per day. Each round collects YouTube/Google global ranks
and the configured YouTube categories. It reuses the existing snapshot/history
pipeline; it does not run training or load speech-to-text models.

## Files

- `scripts/collect_trend_snapshots.py`: one due-slot check and collection, then exit.
- `scripts/install_trend_scheduler.ps1`: register the current user's Windows task.
- `scripts/run_trend_scheduler.py`: windowless Python launcher with stdout/stderr logs.
- `scripts/run_trend_scheduler.ps1`: legacy launcher, no longer used by installed tasks.
- `app/services/trend_scheduler.py`: cross-process lock, slot claim and audit.
- `app/services/trend_settings.py`: persisted schedule and today's slot status.

## Install

From the repository root, specify the Python interpreter containing the project
dependencies. No passwords or API keys are put into the task action.

```powershell
.\scripts\install_trend_scheduler.ps1 -PythonPath 'C:\path\to\python.exe' -ConfigureDaily
```

The installer configures hourly checks and a logon check for the current Windows
user, without administrator run level or wake timers. **A check is not a fetch**:
outside the configured hours it exits without calling providers. Keeping this
fixed check schedule lets Admin change hours without re-registering Windows tasks.
The initial database window is 14:00-23:00; at most one attempt per slot is made.

The Windows user must be logged on. The computer, Internet, workspace drive
(including Z: if used), Python environment, and database must be available.
Closing the browser and Backend does not stop the standalone collector.
Sleep or shutdown still prevents collection. This setup does not start MySQL.

## Windowless Execution And Upgrades

The task starts `pythonw.exe` directly, not PowerShell or a batch file. This avoids
creating a console at startup, rather than hiding one after it appears. The
launcher runs the collector using `CREATE_NO_WINDOW`, redirects stdin/stdout/stderr,
waits for completion and passes its exit code back to Task Scheduler. Collection
failures remain visible in LastTaskResult and the existing diagnostic logs.

To upgrade an existing task, rerun the installer **without** `-ConfigureDaily`:

```powershell
.\scripts\install_trend_scheduler.ps1 -PythonPath 'C:\path\to\python.exe'
```

Only the existing task's action is replaced. Its triggers, principal, enabled
state and settings are preserved, as are the collection hours configured in Admin.
The installer requires `pythonw.exe` beside the supplied interpreter and refuses
to silently fall back to a console launcher. No password or elevated run level
is needed by the scheduled collector. Hiding a task in the Task Scheduler list
alone does not prevent a console window.

A manual diagnostic can run `pythonw.exe -B -X utf8 scripts/run_trend_scheduler.py
--status`. It checks database settings without fetching providers; inspect
`artifacts/trend-scheduler.stdout.log` and `artifacts/trend-scheduler.stderr.log`.

## Admin

Open Analysis Settings > Trend Updates > Daily Schedule. Enable/pause collection
and select the first and last hour. Hours are inclusive, always Asia/Bangkok;
cross-midnight windows are rejected. Save persists changes for both the Backend
and the next external check. Interval mode retains the previous Backend-only
interval settings; the standalone runner does not collect in interval mode.

The panel shows today's slots, actual start time, actor (Backend/Windows), next due
time and the external runner's last database contact. This heartbeat is not a
claim that a Windows task is currently installed or the computer is always on.

## Reliability And History

- Backend and script coordinate using a MySQL connection-level named lock.
  A unique `(region, scheduled_for)` record in `trend_collection_slots` also makes
  the hourly claim persistent across restarts. Non-MySQL development uses a local
  lock plus the unique database claim.
- A failed round is recorded; the next hourly slot is the next automatic attempt.
  There is no rapid retry loop. Individual source failures do not starve other jobs.
- Pausing during a provider request does not undo that request; it stops the next
  part of the round. Partial, failed and interrupted results are not called success.
- Starting at 17:20 can collect the current 17:00 slot, with 17:20 as actual time.
  It does not fabricate or replay 14:00-16:00 snapshots. Graphs use actual times.
- A crashed claim older than 15 minutes is shown as interrupted, not replayed.
  Subsequent hourly slots are still eligible.
- System Logs stores `trend_scheduled_collection` with slot, actor and safe result
  summaries. If the database is unavailable, check Windows LastTaskResult and
  `artifacts/trend-scheduler.stderr.log`; no database log can be written then.
- The wrapper overwrites its two diagnostic log files on each invocation; durable
  collection history remains in the database.

## Manual Checks And Removal

```powershell
python scripts/collect_trend_snapshots.py --status
python scripts/collect_trend_snapshots.py
.\scripts\install_trend_scheduler.ps1 -PythonPath 'C:\path\to\python.exe' -Uninstall
```

The plain command respects pause, hours and already-claimed slots. `--status` never
fetches providers. Exit code 0 includes safe skips; 1 indicates failure or partial
collection. Uninstall only removes this workspace's verified task, not settings
or history. Pause automatic updates in Admin to also stop the Backend collector.
