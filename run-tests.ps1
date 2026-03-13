<#
.SYNOPSIS
    Run the ContextuAI Solo test suite (backend + frontend).

.DESCRIPTION
    Runs backend pytest tests (607+) and/or frontend Playwright E2E tests (118+).
    By default runs both. Use -Backend or -Frontend to run only one.

.PARAMETER Backend
    Run only backend tests (pytest).

.PARAMETER Frontend
    Run only frontend E2E tests (Playwright). Requires dev servers running.

.PARAMETER Filter
    Test name filter. Passed to pytest -k (backend) or playwright --grep (frontend).

.PARAMETER File
    Specific test file to run (works for both backend and frontend).

.PARAMETER Verbose
    Show full tracebacks / detailed output.

.EXAMPLE
    .\run-tests.ps1                              # Run all tests (backend + frontend)
    .\run-tests.ps1 -Backend                     # Backend only
    .\run-tests.ps1 -Frontend                    # Frontend E2E only
    .\run-tests.ps1 -Backend -Filter "sqlite"    # Backend tests matching "sqlite"
    .\run-tests.ps1 -Backend -File "tests/test_repositories.py"
    .\run-tests.ps1 -Frontend -Filter "chat"     # Frontend tests matching "chat"
#>

param(
    [switch]$Backend,
    [switch]$Frontend,
    [string]$Filter = "",
    [string]$File = "",
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# If neither flag is set, run both
$runBackend = $Backend -or (-not $Backend -and -not $Frontend)
$runFrontend = $Frontend -or (-not $Backend -and -not $Frontend)

$backendFailed = $false
$frontendFailed = $false

# ===================================================================
# Backend Tests (pytest)
# ===================================================================
if ($runBackend) {
    Write-Host "`n====================================" -ForegroundColor Cyan
    Write-Host "  Backend Tests (pytest)" -ForegroundColor Cyan
    Write-Host "====================================`n" -ForegroundColor Cyan

    Push-Location "$projectRoot\backend"
    try {
        # Check Python
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
            $backendFailed = $true
        } else {
            Write-Host "Python: $(python --version)" -ForegroundColor Gray

            # Install test deps if needed
            $null = python -m pytest --version 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Installing test dependencies..." -ForegroundColor Yellow
                python -m pip install pytest pytest-asyncio --quiet
            }

            # Build args
            $pytestArgs = @()

            if ($File) {
                $pytestArgs += $File
            } else {
                $pytestArgs += "tests/"
            }

            $pytestArgs += "-v"
            $pytestArgs += "--tb=$(if ($Verbose) { 'long' } else { 'short' })"

            if ($Filter) {
                $pytestArgs += "-k"
                $pytestArgs += $Filter
            }

            Write-Host "pytest $($pytestArgs -join ' ')`n" -ForegroundColor Gray
            python -m pytest @pytestArgs

            if ($LASTEXITCODE -ne 0) {
                $backendFailed = $true
            }
        }
    }
    finally {
        Pop-Location
    }
}

# ===================================================================
# Frontend Tests (Playwright)
# ===================================================================
if ($runFrontend) {
    Write-Host "`n====================================" -ForegroundColor Cyan
    Write-Host "  Frontend Tests (Playwright E2E)" -ForegroundColor Cyan
    Write-Host "====================================`n" -ForegroundColor Cyan

    Push-Location "$projectRoot\frontend"
    try {
        # Check Node
        $node = Get-Command node -ErrorAction SilentlyContinue
        if (-not $node) {
            Write-Host "ERROR: Node.js not found in PATH" -ForegroundColor Red
            $frontendFailed = $true
        } else {
            Write-Host "Node: $(node --version)" -ForegroundColor Gray

            # Check if node_modules exists
            if (-not (Test-Path "node_modules")) {
                Write-Host "Installing dependencies..." -ForegroundColor Yellow
                npm install
            }

            # Build args
            $playwrightArgs = @()

            if ($File) {
                $playwrightArgs += $File
            }

            if ($Filter) {
                $playwrightArgs += "--grep"
                $playwrightArgs += $Filter
            }

            # Note: Playwright needs dev servers running
            Write-Host "NOTE: Frontend tests require both servers running:" -ForegroundColor Yellow
            Write-Host "  - Backend:  cd backend && uvicorn app:app --port 18741" -ForegroundColor Yellow
            Write-Host "  - Frontend: cd frontend && npm run dev`n" -ForegroundColor Yellow

            Write-Host "npx playwright test $($playwrightArgs -join ' ')`n" -ForegroundColor Gray
            npx playwright test @playwrightArgs

            if ($LASTEXITCODE -ne 0) {
                $frontendFailed = $true
            }
        }
    }
    finally {
        Pop-Location
    }
}

# ===================================================================
# Summary
# ===================================================================
Write-Host "`n====================================" -ForegroundColor Cyan
Write-Host "  Test Summary" -ForegroundColor Cyan
Write-Host "====================================`n" -ForegroundColor Cyan

if ($runBackend) {
    if ($backendFailed) {
        Write-Host "  Backend:  FAILED" -ForegroundColor Red
    } else {
        Write-Host "  Backend:  PASSED" -ForegroundColor Green
    }
}

if ($runFrontend) {
    if ($frontendFailed) {
        Write-Host "  Frontend: FAILED" -ForegroundColor Red
    } else {
        Write-Host "  Frontend: PASSED" -ForegroundColor Green
    }
}

Write-Host ""

if ($backendFailed -or $frontendFailed) {
    exit 1
}
