# Download all topic-scoped clustering files from the review branch with backups.
# Run from agents-content-analysis-recommendation-system project root.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path '.').Path
if (-not (Test-Path (Join-Path $root 'app/services/performance_clustering.py')) -or
    -not (Test-Path (Join-Path $root 'frontend_flutter/pubspec.yaml'))) {
    throw 'Run this command from the agents-content-analysis-recommendation-system project root.'
}
$branch = 'feat/topic-scoped-performance-clustering'
$prefix = 'https://raw.githubusercontent.com/Tent1234-ops/content-ai.worktrees/' + $branch + '/agents-content-analysis-recommendation-system/'
$files = @(
    'app/services/performance_clustering_topics.py',
    'app/services/performance_clustering.py',
    'app/routes/contents.py',
    'app/schemas/performance_clustering.py',
    'frontend_flutter/lib/repositories/content_repository.dart',
    'frontend_flutter/lib/models/reference_response.dart',
    'frontend_flutter/lib/widgets/performance_clustering_panel.dart',
    'frontend_flutter/lib/screens/result_screen.dart',
    'frontend_flutter/test/performance_clustering_test.dart',
    'frontend_flutter/test/result_workspace_test.dart',
    'tests/test_performance_clustering_topics.py'
)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $root ('artifacts/topic-clustering-backup-' + $stamp)
$staging = Join-Path $env:TEMP ('content-ai-topic-clustering-' + $stamp)
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
    # Download everything first. A network failure leaves all project files untouched.
    foreach ($relative in $files) {
        $url = $prefix + $relative
        $target = Join-Path $staging $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
        if ((Get-Item $target).Length -eq 0) { throw ('Empty downloaded file: ' + $url) }
    }
    # Save existing files before applying updates.
    foreach ($relative in $files) {
        $dest = Join-Path $root $relative
        if (Test-Path $dest) {
            $old = Join-Path $backup $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $old) | Out-Null
            Copy-Item -LiteralPath $dest -Destination $old -Force
        }
    }
    foreach ($relative in $files) {
        $dest = Join-Path $root $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        Copy-Item -LiteralPath (Join-Path $staging $relative) -Destination $dest -Force
    }
    Write-Host ('Applied ' + $files.Count + ' files. Backups: ' + $backup) -ForegroundColor Green
    Write-Host 'Restart the FastAPI and Flutter development servers, then run backend/Flutter tests.'
} finally {
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}
