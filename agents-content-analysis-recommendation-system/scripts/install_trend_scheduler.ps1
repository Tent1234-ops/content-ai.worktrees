[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [switch]$ConfigureDaily,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = (Resolve-Path -LiteralPath $PythonPath).Path
$collector = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'collect_trend_snapshots.py')).Path
$runner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_trend_scheduler.py')).Path
$legacyRunner = Join-Path $PSScriptRoot 'run_trend_scheduler.ps1'
$digest = [System.Security.Cryptography.SHA256]::Create()
try { $hash = [BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant()))).Replace('-', '').Substring(0, 10) }
finally { $digest.Dispose() }
$name = "ContentAI-Trends-$hash"
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Count -ne 1 -or $existing.Actions[0].WorkingDirectory -ne $root -or
    (-not $existing.Actions[0].Arguments.Contains('"' + $runner + '"') -and
     -not $existing.Actions[0].Arguments.Contains('"' + $legacyRunner + '"')))) {
    throw 'A task with this name belongs to a different action. It was not changed.'
}
if ($Uninstall) {
    if ($existing) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }
    Write-Output "Removed task $name. Database history and settings were not deleted."
    exit 0
}
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    throw 'pythonw.exe was not found beside Python. No task was changed; install the windowless Python executable first.'
}
& $python -B -X utf8 $collector --status
if ($LASTEXITCODE -ne 0) { throw 'Collector preflight failed; no Windows task was registered.' }
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -WorkingDirectory $root -Argument (
    '-B -X utf8 "{0}"' -f $runner)
# Only the database window decides whether an hourly/logon check collects data.
$triggers = @(
    (New-ScheduledTaskTrigger -Once -At ([DateTime]::Today) -RepetitionInterval (New-TimeSpan -Hours 1)),
    (New-ScheduledTaskTrigger -AtLogOn -User $identity)
)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$options = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task = New-ScheduledTask -Action $action -Trigger $triggers -Principal $principal -Settings $options `
    -Description 'Content AI: hourly schedule check; collects only due Asia/Bangkok slots configured in Admin.'
if ($existing) {
    # Upgrading the launcher must not reset triggers or the user's task settings.
    Set-ScheduledTask -TaskName $name -Action $action | Select-Object TaskName, State
} else {
    Register-ScheduledTask -TaskName $name -InputObject $task | Select-Object TaskName, State
}
if ($ConfigureDaily) {
    & $python -B -X utf8 $collector --configure-daily
    if ($LASTEXITCODE -ne 0) { throw 'Task installed, but saving the daily window failed. Check Admin settings.' }
}
Write-Output "Registered windowless task $name for $identity. Requires this account logged on and access to $root and the database."
