# Run smoke tests against running API
# Usage: .\smoke-test.ps1

$BaseUrl = "http://localhost:8000"
$AllPassed = $true

function Test-Endpoint {
    param (
        [string]$Path,
        [string]$Description
    )

    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl$Path" -UseBasicParsing -TimeoutSec 10
        $status = $response.StatusCode
        $content = $response.Content

        if ($status -eq 200) {
            Write-Host "✅ $Path - $Description"
            Write-Host "   Response: $($content.Substring(0, [Math]::Min(100, $content.Length)))..."
            return $true
        } else {
            Write-Host "❌ $Path - Status: $status"
            return $false
        }
    } catch {
        Write-Host "❌ $Path - Error: $_"
        return $false
    }
}

Write-Host "`n=== Smoke Test Results ===`n"

$AllPassed = $AllPassed -and (Test-Endpoint "/health" "Basic health check")
$AllPassed = $AllPassed -and (Test-Endpoint "/ready" "Readiness check")
$AllPassed = $AllPassed -and (Test-Endpoint "/openapi.json" "OpenAPI schema (validates all routes)")

Write-Host "`n=== Summary ===`n"

if ($AllPassed) {
    Write-Host "✅ All smoke tests passed!"
    exit 0
} else {
    Write-Host "❌ Some smoke tests failed"
    exit 1
}
