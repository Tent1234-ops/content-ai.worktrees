[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$WebPort = 8080,
    [int]$WaitSeconds = 90
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $Root 'runtime_artifacts\demo-launcher'
$StatePath = Join-Path $RuntimeDir 'state.json'
$BuildDir = Join-Path $Root 'frontend_flutter\build\web'

function Test-ListeningPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        return $task.Wait(750) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Stop-OwnedProcess($ProcessInfo) {
    if ($null -eq $ProcessInfo) { return }
    $process = Get-Process -Id ([int]$ProcessInfo.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return }
    $actualStart = $process.StartTime.ToUniversalTime().ToString('o')
    if ($actualStart -ne [string]$ProcessInfo.started_at_utc) {
        throw "Refusing to stop PID $($ProcessInfo.pid): process identity changed."
    }
    Stop-Process -Id $process.Id -Force
    $null = $process.WaitForExit(10000)
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (Test-Path -LiteralPath $StatePath) {
    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    $backendAlive = Get-Process -Id ([int]$state.backend.pid) -ErrorAction SilentlyContinue
    $webAlive = Get-Process -Id ([int]$state.web.pid) -ErrorAction SilentlyContinue
    if ($backendAlive -and $webAlive -and
        (Test-Endpoint "http://127.0.0.1:$BackendPort/health") -and
        (Test-Endpoint "http://127.0.0.1:$WebPort")) {
        [pscustomobject]@{ status = 'already_running'; backend = $BackendPort; web = $WebPort } |
            ConvertTo-Json -Compress
        exit 0
    }
    if ($backendAlive -or $webAlive) {
        throw "Launcher state is inconsistent. Run scripts\stop_demo.ps1 before starting again."
    }
    Remove-Item -LiteralPath $StatePath -Force
}

foreach ($port in @($BackendPort, $WebPort)) {
    if (Test-ListeningPort $port) {
        throw "Port $port is already in use. No process was stopped. Choose another port or close its owner."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $BuildDir 'index.html'))) {
    throw 'Release web build is missing. Run flutter build web --release first.'
}

$python = (Get-Command python -ErrorAction Stop).Source
$backendOut = Join-Path $RuntimeDir 'backend.stdout.log'
$backendErr = Join-Path $RuntimeDir 'backend.stderr.log'
$webOut = Join-Path $RuntimeDir 'web.stdout.log'
$webErr = Join-Path $RuntimeDir 'web.stderr.log'

$backend = $null
$web = $null
try {
    $backend = Start-Process -FilePath $python -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr
    $web = Start-Process -FilePath $python -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -ArgumentList @('-m', 'http.server', "$WebPort", '--bind', '127.0.0.1', '--directory', $BuildDir) `
        -RedirectStandardOutput $webOut -RedirectStandardError $webErr

    # A previously running service could answer readiness while a new process is
    # still failing to bind. Verify the processes we own before trusting URLs.
    Start-Sleep -Seconds 1
    $backend.Refresh()
    $web.Refresh()
    if ($backend.HasExited) { throw "Backend exited early. See $backendErr" }
    if ($web.HasExited) { throw "Web server exited early. See $webErr" }

    $state = [ordered]@{
        schema_version = 'content-ai-demo-launcher-v1'
        root = $Root
        backend_port = $BackendPort
        web_port = $WebPort
        started_at = (Get-Date).ToUniversalTime().ToString('o')
        backend = [ordered]@{
            pid = $backend.Id
            started_at_utc = $backend.StartTime.ToUniversalTime().ToString('o')
            executable = $python
        }
        web = [ordered]@{
            pid = $web.Id
            started_at_utc = $web.StartTime.ToUniversalTime().ToString('o')
            executable = $python
        }
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatePath -Encoding utf8

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        if ($backend.HasExited) { throw "Backend exited early. See $backendErr" }
        if ($web.HasExited) { throw "Web server exited early. See $webErr" }
        if ((Test-Endpoint "http://127.0.0.1:$BackendPort/health") -and
            (Test-Endpoint "http://127.0.0.1:$WebPort")) {
            [pscustomobject]@{
                status = 'ready'
                backend_url = "http://127.0.0.1:$BackendPort"
                web_url = "http://127.0.0.1:$WebPort/#/dashboard"
                state = $StatePath
            } | ConvertTo-Json -Compress
            exit 0
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Readiness timed out after $WaitSeconds seconds."
} catch {
    try { Stop-OwnedProcess $web } catch {}
    try { Stop-OwnedProcess $backend } catch {}
    Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
    throw
}
