$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3000" }
$env:NEXT_PUBLIC_API_URL = if ($env:NEXT_PUBLIC_API_URL) { $env:NEXT_PUBLIC_API_URL } else { "http://127.0.0.1:$apiPort" }
$env:USE_LOCAL_BACKEND = if ($env:USE_LOCAL_BACKEND) { $env:USE_LOCAL_BACKEND } else { "true" }
$env:ELASTICSEARCH_URL = if ($env:ELASTICSEARCH_URL) { $env:ELASTICSEARCH_URL } else { "local://memory" }

$api = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $apiPort -WorkingDirectory "$root\api" -PassThru -WindowStyle Hidden
$web = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev", "--", "--hostname", "127.0.0.1", "--port", $frontendPort -WorkingDirectory "$root\frontend" -PassThru -WindowStyle Hidden

Write-Host "API:      http://127.0.0.1:$apiPort"
Write-Host "Frontend: http://127.0.0.1:$frontendPort"
Write-Host "Press Ctrl+C to stop both processes."

try {
    while ($true) {
        if ($api.HasExited) { throw "API exited with code $($api.ExitCode)" }
        if ($web.HasExited) { throw "Frontend exited with code $($web.ExitCode)" }
        Start-Sleep -Seconds 1
    }
}
finally {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    if (-not $web.HasExited) { Stop-Process -Id $web.Id -Force }
}
