[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$WebPort = 8080
)

$ErrorActionPreference = 'Stop'
$backend = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 10
$web = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$WebPort" -TimeoutSec 10
$asrReady = [bool]$backend.ai_models.faster_whisper.ready

$result = [ordered]@{
    ready = ($web.StatusCode -eq 200 -and $backend.database.status -eq 'ok' -and $asrReady)
    service_status = $backend.status
    web_status = $web.StatusCode
    database_status = $backend.database.status
    asr_ready = $asrReady
    trend_providers = $backend.live_trends.providers
    backend_url = "http://127.0.0.1:$BackendPort"
    web_url = "http://127.0.0.1:$WebPort/#/dashboard"
}
$result | ConvertTo-Json -Compress
if (-not $result.ready) { exit 1 }
