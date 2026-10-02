[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$StatePath = Join-Path $Root 'runtime_artifacts\demo-launcher\state.json'

if (-not (Test-Path -LiteralPath $StatePath)) {
    [pscustomobject]@{ status = 'not_running'; state = $StatePath } | ConvertTo-Json -Compress
    exit 0
}

$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$stopped = @()
foreach ($entry in @($state.web, $state.backend)) {
    $process = Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { continue }
    $actualStart = $process.StartTime.ToUniversalTime().ToString('o')
    if ($actualStart -ne [string]$entry.started_at_utc) {
        throw "Refusing to stop PID $($entry.pid): process identity changed. State file was preserved."
    }
    Stop-Process -Id $process.Id -Force
    $null = $process.WaitForExit(10000)
    $stopped += $process.Id
}

Remove-Item -LiteralPath $StatePath -Force
[pscustomobject]@{ status = 'stopped'; pids = $stopped } | ConvertTo-Json -Compress
