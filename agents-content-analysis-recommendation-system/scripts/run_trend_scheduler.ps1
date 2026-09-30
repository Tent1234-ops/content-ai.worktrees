[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$PythonPath)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = (Resolve-Path -LiteralPath $PythonPath).Path
$collector = Join-Path $PSScriptRoot 'collect_trend_snapshots.py'
$logs = Join-Path $root 'artifacts'
if (-not (Test-Path -LiteralPath $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }
try {
    $process = Start-Process -FilePath $python -ArgumentList @('-B', '-X', 'utf8', ('"{0}"' -f $collector)) `
        -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
        -RedirectStandardOutput (Join-Path $logs 'trend-scheduler.stdout.log') `
        -RedirectStandardError (Join-Path $logs 'trend-scheduler.stderr.log')
    exit $process.ExitCode
} catch {
    Write-Error 'Cannot start trend collector. Check Python, workspace and database availability.'
    exit 1
}
