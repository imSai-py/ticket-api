# Unified verification script for ticket-api
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$failed = $false

if (-not $FrontendOnly) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "1. Testing Python ticket-api (pytest)..." -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    try {
        python -m pytest tests -v
        if ($LASTEXITCODE -ne 0) { $failed = $true }
    } catch {
        $failed = $true
    }

    Write-Host "`nChecking Python formatting and linting (ruff)..." -ForegroundColor Cyan
    try {
        ruff check .
        if ($LASTEXITCODE -ne 0) { $failed = $true }
    } catch {
        $failed = $true
    }

    Write-Host "`nChecking Python code style (black)..." -ForegroundColor Cyan
    try {
        black --check .
        if ($LASTEXITCODE -ne 0) { $failed = $true }
    } catch {
        $failed = $true
    }
}

if (-not $BackendOnly -and (Test-Path "frontend/package.json")) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "2. Testing Frontend (Vitest & tsc)..." -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Push-Location "frontend"
    try {
        npm test -- --run
        if ($LASTEXITCODE -ne 0) { $failed = $true }
        npm run build
        if ($LASTEXITCODE -ne 0) { $failed = $true }
    } catch {
        $failed = $true
    } finally {
        Pop-Location
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
if ($failed) {
    Write-Host "VERIFICATION FAILED: One or more test suites failed." -ForegroundColor Red
    exit 1
} else {
    Write-Host "VERIFICATION SUCCESS: All tests passed!" -ForegroundColor Green
    exit 0
}
