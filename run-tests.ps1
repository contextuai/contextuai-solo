<#
.SYNOPSIS
    Run the ContextuAI Solo test suite (backend + frontend).

.DESCRIPTION
    Runs backend pytest tests (607+) and/or frontend Playwright E2E tests (118+).
    By default runs both. Use -Backend or -Frontend to run only one.
    For frontend tests, the script automatically starts/stops the backend and
    frontend dev servers — no manual setup needed.

.PARAMETER Backend
    Run only backend tests (pytest).

.PARAMETER Frontend
    Run only frontend E2E tests (Playwright).

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

# Track server processes we start so we can clean them up
$startedBackend = $false
$startedFrontend = $false
$backendProcess = $null
$frontendProcess = $null

function Test-ServerReady {
    param([string]$Url, [int]$TimeoutSeconds = 30, [string]$Label = "Server")
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    Write-Host "  TIMEOUT: $Label not ready at $Url after ${TimeoutSeconds}s" -ForegroundColor Red
    return $false
}

function Stop-ServerProcesses {
    if ($script:backendProcess -and -not $script:backendProcess.HasExited) {
        Write-Host "  Stopping backend server (PID $($script:backendProcess.Id))..." -ForegroundColor Gray
        Stop-Process -Id $script:backendProcess.Id -Force -ErrorAction SilentlyContinue
        # Also kill any child uvicorn processes on port 18741
        Get-NetTCPConnection -LocalPort 18741 -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
    if ($script:frontendProcess -and -not $script:frontendProcess.HasExited) {
        Write-Host "  Stopping frontend server (PID $($script:frontendProcess.Id))..." -ForegroundColor Gray
        Stop-Process -Id $script:frontendProcess.Id -Force -ErrorAction SilentlyContinue
        # Also kill any child node processes on port 1420
        Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
}

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

            # -----------------------------------------------------------
            # Auto-start backend server if not already running
            # -----------------------------------------------------------
            $backendUrl = "http://127.0.0.1:18741/health"
            $backendAlreadyRunning = $false
            try {
                $r = Invoke-WebRequest -Uri $backendUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($r.StatusCode -eq 200) { $backendAlreadyRunning = $true }
            } catch {}

            if ($backendAlreadyRunning) {
                Write-Host "  Backend already running on port 18741" -ForegroundColor Green
            } else {
                Write-Host "  Starting backend server..." -ForegroundColor Yellow
                $venvPython = "$projectRoot\backend\.venv\Scripts\python.exe"
                if (-not (Test-Path $venvPython)) {
                    $venvPython = "python"
                }

                $env:CONTEXTUAI_MODE = "desktop"
                $backendProcess = Start-Process -FilePath $venvPython `
                    -ArgumentList "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "18741" `
                    -WorkingDirectory "$projectRoot\backend" `
                    -WindowStyle Hidden -PassThru
                $startedBackend = $true

                if (-not (Test-ServerReady -Url $backendUrl -TimeoutSeconds 30 -Label "Backend")) {
                    Write-Host "ERROR: Backend failed to start" -ForegroundColor Red
                    $frontendFailed = $true
                    Stop-ServerProcesses
                    Pop-Location
                    return
                }
                Write-Host "  Backend ready (PID $($backendProcess.Id))" -ForegroundColor Green
            }

            # -----------------------------------------------------------
            # Auto-start frontend dev server if not already running
            # -----------------------------------------------------------
            $frontendUrl = "http://localhost:1420"
            $frontendAlreadyRunning = $false
            try {
                $r = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($r.StatusCode -eq 200) { $frontendAlreadyRunning = $true }
            } catch {}

            if ($frontendAlreadyRunning) {
                Write-Host "  Frontend already running on port 1420" -ForegroundColor Green
            } else {
                Write-Host "  Starting frontend dev server..." -ForegroundColor Yellow
                $frontendProcess = Start-Process -FilePath "cmd.exe" `
                    -ArgumentList "/c", "npm run dev" `
                    -WorkingDirectory "$projectRoot\frontend" `
                    -WindowStyle Hidden -PassThru
                $startedFrontend = $true

                if (-not (Test-ServerReady -Url $frontendUrl -TimeoutSeconds 30 -Label "Frontend")) {
                    Write-Host "ERROR: Frontend dev server failed to start" -ForegroundColor Red
                    $frontendFailed = $true
                    Stop-ServerProcesses
                    Pop-Location
                    return
                }
                Write-Host "  Frontend ready (PID $($frontendProcess.Id))" -ForegroundColor Green
            }

            Write-Host ""

            # Build Playwright args
            $playwrightArgs = @()

            if ($File) {
                $playwrightArgs += $File
            }

            if ($Filter) {
                $playwrightArgs += "--grep"
                $playwrightArgs += $Filter
            }

            Write-Host "npx playwright test $($playwrightArgs -join ' ')`n" -ForegroundColor Gray
            npx playwright test @playwrightArgs

            if ($LASTEXITCODE -ne 0) {
                $frontendFailed = $true
            }
        }
    }
    finally {
        # Stop servers we started (leave pre-existing ones alone)
        Stop-ServerProcesses
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
