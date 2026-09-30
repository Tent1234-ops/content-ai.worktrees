[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$root = (Resolve-Path -LiteralPath (Join-Path $project 'artifacts')).Path

function Assert-ArtifactPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside artifacts: $full"
    }
    $ancestor = $full
    while ($ancestor -and $ancestor -ne $root) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing link/reparse point: $ancestor"
            }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
    return $full
}

if ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The artifacts directory must not be a link.'
}
$protected = @('phase2-persistence.json', 'topic-phase1-api.stderr.log', 'topic-phase1-api.stdout.log',
    'phase2-web.stderr.log', 'phase2-web.stdout.log', 'trend-scheduler.stderr.log', 'trend-scheduler.stdout.log')
$plan = @()
foreach ($file in Get-ChildItem -LiteralPath $root -File) {
    if ($protected -contains $file.Name) { continue }
    $kind = switch ($file.Extension.ToLowerInvariant()) {
        '.png' { 'screenshots' }
        '.log' { 'logs/archive' }
        '.json' { 'reports' }
        '.txt' { 'reports' }
        default { $null }
    }
    if (-not $kind) { continue }
    $feature = ($file.BaseName -split '-')[0]
    $destination = Assert-ArtifactPath (Join-Path $root "$kind/$feature/$($file.Name)")
    $source = Assert-ArtifactPath $file.FullName
    $plan += [pscustomobject]@{ source = $source; destination = $destination; directory = $false }
}
$bundle = Join-Path $root 'trend-topics/phase1-20260925'
if (Test-Path -LiteralPath $bundle) {
    $plan += [pscustomobject]@{
        source = (Assert-ArtifactPath $bundle)
        destination = (Assert-ArtifactPath (Join-Path $root 'trend-topics/evaluation/phase1-20260925'))
        directory = $true
    }
}
foreach ($entry in $plan) {
    if (Test-Path -LiteralPath $entry.destination) { throw "Destination exists: $($entry.destination)" }
}
if (-not $Apply) {
    $plan | ConvertTo-Json -Depth 4
    exit 0
}
$journalDir = Join-Path $root 'organization'
New-Item -ItemType Directory -Path $journalDir -Force | Out-Null
$journal = Join-Path $journalDir ((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '.json')
$results = @()
foreach ($entry in $plan) {
    $files = if ($entry.directory) { @(Get-ChildItem -LiteralPath $entry.source -File -Recurse) } else { @(Get-Item -LiteralPath $entry.source) }
    $checks = @($files | ForEach-Object {
        Assert-ArtifactPath $_.FullName | Out-Null
        [pscustomobject]@{ relative = $_.FullName.Substring($entry.source.Length).TrimStart('\'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    New-Item -ItemType Directory -Path (Split-Path -Parent $entry.destination) -Force | Out-Null
    $status = 'moved'
    try { Move-Item -LiteralPath $entry.source -Destination $entry.destination -ErrorAction Stop }
    catch {
        if (Test-Path -LiteralPath $entry.destination) { throw }
        $status = 'kept_unavailable'
    }
    if ($status -eq 'moved') {
        foreach ($check in $checks) {
            $target = if ($entry.directory) { Join-Path $entry.destination $check.relative } else { $entry.destination }
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $check.sha256) { throw "Hash mismatch: $target" }
        }
    }
    $results += [pscustomobject]@{ source = $entry.source; destination = $entry.destination; status = $status; checks = $checks }
    ConvertTo-Json -InputObject $results -Depth 6 | Set-Content -LiteralPath $journal -Encoding UTF8
}
[pscustomobject]@{ moved = @($results | Where-Object status -eq 'moved').Count; kept = @($results | Where-Object status -ne 'moved').Count; journal = $journal } | ConvertTo-Json
