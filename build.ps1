# ContextuAI Solo — Full Desktop Build Script
# Usage: .\build.ps1
# Builds: Python sidecar (PyInstaller) + Frontend (Vite) + Tauri desktop app (MSI + NSIS)

$root = $PSScriptRoot
$backend = "$root\backend"
$frontend = "$root\frontend"
$sidecar = "$frontend\src-tauri\sidecar"

Write-Host "`n=== ContextuAI Solo Build ===" -ForegroundColor Cyan
Write-Host "Root: $root`n"

# ── Step 1: Build Python sidecar ────────────────────────────────────────
Write-Host "[1/3] Building Python sidecar (PyInstaller)..." -ForegroundColor Yellow

Push-Location $backend
try {
    $env:PYTHONIOENCODING = "utf-8"
    $output = & .venv\Scripts\pyinstaller.exe contextuai-solo-backend.spec `
        --distpath "$sidecar" `
        --workpath .\build `
        --noconfirm 2>&1

    # Show only important lines
    $output | ForEach-Object {
        $line = "$_"
        if ($line -match "completed successfully|ERROR|Building") {
            Write-Host "  $line"
        }
    }

    # PyInstaller COLLECT outputs a subdirectory — flatten it
    $nested = "$sidecar\contextuai-solo-backend"
    if (Test-Path $nested) {
        Remove-Item "$sidecar\contextuai-solo-backend.exe" -ErrorAction SilentlyContinue
        Remove-Item "$sidecar\_internal" -Recurse -ErrorAction SilentlyContinue
        Copy-Item "$nested\*" "$sidecar\" -Recurse -Force
        Remove-Item $nested -Recurse -Force
    }

    $exe = "$sidecar\contextuai-solo-backend.exe"
    if (Test-Path $exe) {
        $size = [math]::Round((Get-Item $exe).Length / 1MB)
        Write-Host "  Sidecar built: $exe ($size MB)" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Sidecar exe not found!" -ForegroundColor Red
        Pop-Location
        exit 1
    }
} catch {
    Write-Host "  ERROR: PyInstaller failed: $_" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# ── Step 2: Build Tauri desktop app ─────────────────────────────────────
Write-Host "`n[2/3] Building Tauri desktop app (TypeScript + Vite + Rust)..." -ForegroundColor Yellow

Push-Location $frontend
try {
    $output = & npm run tauri build 2>&1
    $output | ForEach-Object {
        $line = "$_"
        if ($line -match "built in|Finished|Running (candle|light|makensis)|error|Built application") {
            Write-Host "  $line"
        }
    }
} catch {
    Write-Host "  ERROR: Tauri build failed: $_" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# ── Step 3: Verify outputs ──────────────────────────────────────────────
Write-Host "`n[3/3] Verifying outputs..." -ForegroundColor Yellow

$msi = Get-ChildItem "$frontend\src-tauri\target\release\bundle\msi\*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
$nsis = Get-ChildItem "$frontend\src-tauri\target\release\bundle\nsis\*setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($msi) {
    $msiSize = [math]::Round($msi.Length / 1MB)
    Write-Host "  MSI:  $($msi.FullName) ($msiSize MB)" -ForegroundColor Green
}
if ($nsis) {
    $nsisSize = [math]::Round($nsis.Length / 1MB)
    Write-Host "  NSIS: $($nsis.FullName) ($nsisSize MB)" -ForegroundColor Green
}

if (-not $msi -and -not $nsis) {
    Write-Host "  ERROR: No installers found!" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan
