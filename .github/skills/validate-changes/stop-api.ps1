# Stop the API process
# Usage: .\stop-api.ps1

$ApiDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$ApiDir = Join-Path $ApiDir "api"
$PidFile = Join-Path $ApiDir ".api-pid"

# Try to stop by saved PID first
if (Test-Path $PidFile) {
    $pid = Get-Content $PidFile
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "✅ Stopped API process (PID: $pid)"
    } catch {
        Write-Host "⚠️ Process $pid not found, may have already stopped"
    }
    Remove-Item $PidFile -Force
}

# Also kill any stray uvicorn processes
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        if ($cmdLine -like "*uvicorn*main:app*") {
            Stop-Process -Id $_.Id -Force
            Write-Host "✅ Killed stray uvicorn process (PID: $($_.Id))"
        }
    } catch {
        # Ignore errors for processes we can't inspect
    }
}

Write-Host "✅ Cleanup complete"
