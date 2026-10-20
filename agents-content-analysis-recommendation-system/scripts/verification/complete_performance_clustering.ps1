# Reproducible Windows closeout for Content AI performance clustering.
# Existing API/Web processes are only read, never stopped or restarted.
[CmdletBinding()]
param(
    [string]$OutputDir = 'artifacts/performance-clustering/final-verification',
    [switch]$SkipBuild,
    [switch]$SkipBrowser,
    [switch]$QuickBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$FrontendRoot = Join-Path $ProjectRoot 'frontend_flutter'
$ReportRoot = if ([IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $ProjectRoot $OutputDir }
$BrowserRoot = Join-Path $ReportRoot 'browser'
New-Item -ItemType Directory -Path $ReportRoot -Force | Out-Null

$Results = [ordered]@{
    generated_at = (Get-Date).ToString('o')
    project_root = $ProjectRoot
    steps = @()
    browser_complete = $false
    passed = $false
}
$Failure = $null

function Add-Result([string]$Name, [string]$Status, [string]$Detail) {
    $script:Results.steps += [ordered]@{ name = $Name; status = $Status; detail = $Detail }
}

function Run-Step([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory) {
    $logFile = Join-Path $ReportRoot (($Name -replace '[^a-zA-Z0-9_-]', '-') + '.log')
    Write-Host ('>>> ' + $Name) -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    $beforePreference = $ErrorActionPreference
    try {
        # Windows PowerShell may treat native stderr as errors. Check exit codes instead.
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments 2>&1 | Out-String -Stream | Tee-Object -FilePath $logFile
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $beforePreference
        Pop-Location
    }
    if ($exit -ne 0) {
        Add-Result $Name 'failed' ("exit code $exit; see $logFile")
        throw "$Name failed (exit code $exit). Log: $logFile"
    }
    Add-Result $Name 'passed' $logFile
}

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Require-LocalService([string]$Name, [string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
        if ($response.StatusCode -ne 200) { throw "HTTP $($response.StatusCode)" }
    } catch {
        throw "$Name at $Url is unreachable. This script intentionally does not start/stop any existing process. $($_.Exception.Message)"
    }
}

try {
    Require-Command 'py'
    Require-Command 'flutter'

    Run-Step 'backend-clustering-tests' 'py' @(
        '-X','utf8','-m','pytest','-q',
        'tests/test_performance_clustering.py',
        'tests/test_recommendation_evidence.py',
        'tests/test_phase20_keyword_gap_evidence.py',
        'tests/test_phase12_ai_evidence.py'
    ) $ProjectRoot
    Run-Step 'flutter-all-tests' 'flutter' @('test') $FrontendRoot
    Run-Step 'flutter-analyze' 'flutter' @('analyze') $FrontendRoot

    if ($SkipBuild) {
        Add-Result 'flutter-web-release-build' 'skipped' 'SkipBuild requested'
    } else {
        Run-Step 'flutter-web-release-build' 'flutter' @(
            'build','web','--release','--output','build/performance-clustering'
        ) $FrontendRoot
    }

    if ($SkipBrowser) {
        Add-Result 'browser-eight-layouts' 'skipped' 'SkipBrowser requested; closeout is incomplete'
    } else {
        Require-Command 'node'
        $playwright = Join-Path $ProjectRoot 'artifacts/browser-tools/node_modules/playwright'
        if (-not (Test-Path $playwright)) {
            throw "Edge verification requires existing Playwright dependencies at $playwright."
        }
        Require-LocalService 'FastAPI' 'http://127.0.0.1:8011/health'
        Require-LocalService 'Flutter Web' 'http://127.0.0.1:8082/'
        Write-Warning 'Ensure the web server on port 8082 serves the current clustering build. No services are restarted by this script.'
        New-Item -ItemType Directory -Path $BrowserRoot -Force | Out-Null
        $browserArgs = @('scripts/browser/verify_performance_clustering.cjs', $BrowserRoot)
        if ($QuickBrowser) { $browserArgs += '--quick' }
        Run-Step 'browser-layout-verification' 'node' $browserArgs $ProjectRoot

        $verificationPath = Join-Path $BrowserRoot 'verification.json'
        if (-not (Test-Path $verificationPath)) { throw "Missing browser report $verificationPath" }
        $verification = Get-Content $verificationPath -Raw | ConvertFrom-Json
        if ($verification.passed -ne $true -or
            $verification.saved_data_unchanged -ne $true -or
            $verification.temporary_session_ended -ne $true) {
            throw "Browser safety checks failed: $verificationPath"
        }
        if ($QuickBrowser) {
            Add-Result 'browser-eight-layouts' 'partial' 'Only 390px/light was verified'
        } else {
            if (@($verification.checks).Count -ne 8 -or
                $verification.threshold_empty_and_restored -ne $true) {
                throw "Expected 8 responsive/theme checks and threshold restoration: $verificationPath"
            }
            Add-Result 'browser-eight-layouts' 'passed' $verificationPath
            $Results.browser_complete = $true
        }

        Run-Step 'chart-pixel-verification' 'py' @(
            '-X','utf8','scripts/verification/performance_chart_pixels.py', $BrowserRoot
        ) $ProjectRoot
        $pixels = Get-Content (Join-Path $BrowserRoot 'pixel-checks.json') -Raw | ConvertFrom-Json
        $expectedCharts = if ($QuickBrowser) { 1 } else { 8 }
        if ($pixels.passed -ne $true -or @($pixels.checks).Count -ne $expectedCharts) {
            throw "Pixel checks did not verify $expectedCharts chart(s)."
        }
    }

    $Results.passed = -not ($SkipBrowser -or $QuickBrowser -or $SkipBuild)
    if ($Results.passed) {
        Write-Host 'All closeout checks passed, including 8 actual browser layouts.' -ForegroundColor Green
    } else {
        Write-Warning 'Some stages were skipped: this is not full release verification.'
    }
} catch {
    $Failure = $_.Exception.Message
    $Results.passed = $false
    Write-Error $Failure -ErrorAction Continue
} finally {
    $Results['failure'] = $Failure
    $reportFile = Join-Path $ReportRoot 'closeout-summary.json'
    $Results | ConvertTo-Json -Depth 8 | Set-Content -Path $reportFile -Encoding UTF8
    Write-Host "Closeout report: $reportFile"
}
if (-not $Results.passed) { exit 1 }
