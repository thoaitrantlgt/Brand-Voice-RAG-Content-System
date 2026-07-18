$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $root ".runtime\processes.json"
if (-not (Test-Path -LiteralPath $processFile)) {
    Write-Host "No ContentOS process file found."
    exit 0
}

$saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
foreach ($name in @("frontend", "worker", "api")) {
    $processId = [int]$saved.$name
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -ne $process -and $process.ProcessName -in @("python", "node", "npm", "cmd")) {
        taskkill.exe /PID $processId /T /F | Out-Null
        Write-Host "Stopped $name ($processId)"
    }
}
Remove-Item -LiteralPath $processFile -Force
