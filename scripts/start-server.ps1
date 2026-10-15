# Server startup script with port listener cleanup
param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

Write-Host "Checking for existing processes on port $Port..." -ForegroundColor Cyan
$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

if ($connections) {
    foreach ($conn in $connections) {
        $pidToKill = $conn.OwningProcess
        if ($pidToKill -and $pidToKill -ne 0) {
            Write-Host "Stopping process on port $Port (PID: $pidToKill)..." -ForegroundColor Yellow
            try {
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 500
            } catch {
                Write-Warning ("Could not stop PID $pidToKill : " + $_.Exception.Message)
            }
        }
    }
} else {
    Write-Host "Port $Port is free." -ForegroundColor Green
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting uvicorn server on http://${HostAddress}:${Port}..." -ForegroundColor Cyan
python @uvicornArgs
