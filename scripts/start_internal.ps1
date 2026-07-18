param([switch]$AllowInsecureLocal)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$runtime = Join-Path $root ".runtime"
$logs = Join-Path $runtime "logs"
$standalone = Join-Path $frontend ".next\standalone"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend virtual environment is missing: $python"
}
if (-not (Test-Path -LiteralPath (Join-Path $backend ".env"))) {
    throw "Create backend/.env from backend/.env.example before starting."
}
$envText = Get-Content -LiteralPath (Join-Path $backend ".env") -Raw
$authEnabled = $envText -match '(?im)^\s*AUTH_ENABLED\s*=\s*true\s*$'
if (-not $authEnabled -and -not $AllowInsecureLocal) {
    throw "AUTH_ENABLED must be true. Use -AllowInsecureLocal only for local development."
}
if ($authEnabled -and $envText -notmatch '(?im)^\s*INTERNAL_ACCESS_TOKENS\s*=\s*\{.+\}\s*$') {
    throw "INTERNAL_ACCESS_TOKENS must contain at least one configured token."
}
if (-not (Test-Path -LiteralPath (Join-Path $standalone "server.js"))) {
    throw "Production frontend build is missing. Run npm.cmd run build from frontend/."
}

New-Item -ItemType Directory -Force -Path $logs | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $standalone ".next") | Out-Null
Copy-Item -LiteralPath (Join-Path $frontend ".next\static") `
    -Destination (Join-Path $standalone ".next\static") -Recurse -Force
if (Test-Path -LiteralPath (Join-Path $frontend "public")) {
    Copy-Item -LiteralPath (Join-Path $frontend "public") `
        -Destination (Join-Path $standalone "public") -Recurse -Force
}

$api = Start-Process -FilePath $python -ArgumentList "run.py" -WorkingDirectory $backend `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs "api.out.log") `
    -RedirectStandardError (Join-Path $logs "api.err.log")
$worker = Start-Process -FilePath $python -ArgumentList "worker.py" -WorkingDirectory $backend `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs "worker.out.log") `
    -RedirectStandardError (Join-Path $logs "worker.err.log")
$web = Start-Process -FilePath "node.exe" -ArgumentList "server.js" -WorkingDirectory $standalone `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs "frontend.out.log") `
    -RedirectStandardError (Join-Path $logs "frontend.err.log")

@{
    api = $api.Id
    worker = $worker.Id
    frontend = $web.Id
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime "processes.json") -Encoding UTF8

Write-Host "ContentOS started"
Write-Host "Frontend: http://127.0.0.1:3000"
Write-Host "API:      http://127.0.0.1:8000"
Write-Host "Ready:    http://127.0.0.1:8000/ready"
