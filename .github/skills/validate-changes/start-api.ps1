# Start API in a separate process that persists
# Usage: .\start-api.ps1

$ApiDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$ApiDir = Join-Path $ApiDir "api"

# Kill any existing API processes first
Get-Process -Name "python" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and (Get-Process -Id $_.Id).CommandLine -like "*uvicorn*main:app*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

# Start new API process
$process = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$ApiDir'; .\.venv\Scripts\Activate.ps1; python -m uvicorn main:app --host 0.0.0.0 --port 8000"
) -PassThru

Write-Host "API started with PID: $($process.Id)"
Write-Host "Waiting for startup..."
Start-Sleep -Seconds 4

# Check if it's running
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ API is healthy: $($response.Content)"
} catch {
    Write-Host "❌ API health check failed: $_"
    exit 1
}

# Save PID for cleanup
$process.Id | Out-File -FilePath "$ApiDir\.api-pid" -Force
Write-Host "PID saved to $ApiDir\.api-pid"
