# ═══════════════════════════════════════════════════════════
# Lumas Android — Setup Script
# ═══════════════════════════════════════════════════════════
# Run this script to prepare the Android build environment:
#   1. Clones/updates llama.cpp source for NDK compilation
#   2. Downloads a sample GGUF model for testing
#   3. Verifies the Android SDK/NDK are available
# ═══════════════════════════════════════════════════════════

param(
    [string]$ModelUrl = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AndroidDir = $PSScriptRoot
$LlamaCppDir = Join-Path $PSScriptRoot ".." "llamacpp"

Write-Host "=== Lumas Android Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check Android SDK/NDK ────────────────────────
$androidHome = $env:ANDROID_HOME
if (-not $androidHome) {
    $androidHome = $env:ANDROID_SDK_ROOT
}
if (-not $androidHome) {
    Write-Host "[WARN] ANDROID_HOME not set. Set it to your Android SDK path." -ForegroundColor Yellow
    Write-Host "       e.g. `$env:ANDROID_HOME = 'C:\Users\you\AppData\Local\Android\Sdk'" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Android SDK: $androidHome" -ForegroundColor Green
}

# ── Step 2: Clone/Update llama.cpp ───────────────────────
$llamacppExists = Test-Path (Join-Path $LlamaCppDir "ggml.c")
if (-not $llamacppExists -or $Force) {
    if (Test-Path $LlamaCppDir) {
        Write-Host "[INFO] Updating llama.cpp..." -ForegroundColor Yellow
        Push-Location $LlamaCppDir
        try {
            git pull
        } catch {
            Write-Host "[WARN] Git pull failed, continuing..." -ForegroundColor Yellow
        }
        Pop-Location
    } else {
        Write-Host "[INFO] Cloning llama.cpp..." -ForegroundColor Yellow
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git $LlamaCppDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to clone llama.cpp" -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "[OK] llama.cpp source ready" -ForegroundColor Green
} else {
    Write-Host "[OK] llama.cpp already present" -ForegroundColor Green
}

# ── Step 3: Download GGUF model ──────────────────────────
$ModelDir = Join-Path $AndroidDir "app" "src" "main" "assets"
$ModelPath = Join-Path $ModelDir "lumas-model.gguf"
$modelExists = Test-Path $ModelPath

if (-not $modelExists -or $Force) {
    if ($ModelUrl) {
        Write-Host "[INFO] Downloading model from $ModelUrl ..." -ForegroundColor Yellow
        if (-not (Test-Path $ModelDir)) {
            New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
        }
        Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to download model" -ForegroundColor Red
            exit 1
        }
        Write-Host "[OK] Model downloaded: $ModelPath" -ForegroundColor Green
    } else {
        Write-Host "[WARN] No model URL provided." -ForegroundColor Yellow
        Write-Host "       The app will work in connected API mode without a bundled model." -ForegroundColor Yellow
        Write-Host "       To bundle a model, run: .\setup.ps1 -ModelUrl <download-url>" -ForegroundColor Yellow
        Write-Host "       Or place your GGUF file at: $ModelPath" -ForegroundColor Yellow

        # Create placeholder
        if (-not (Test-Path $ModelDir)) {
            New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
        }
        if (-not $modelExists) {
            Set-Content -Path $ModelPath -Value "PLACEHOLDER - Replace with actual GGUF model file" -NoNewline
        }
    }
} else {
    $size = (Get-Item $ModelPath).Length
    Write-Host "[OK] Model present: $ModelPath ($($size / 1MB) MB)" -ForegroundColor Green
}

# ── Step 4: Copy shared JS modules to assets ─────────────
$SharedSource = Join-Path $ProjectRoot "lumas" "frontend" "shared"
$SharedDest = Join-Path $AndroidDir "app" "src" "main" "assets" "shared"

if (Test-Path $SharedSource) {
    if (-not (Test-Path $SharedDest) -or $Force) {
        Write-Host "[INFO] Copying shared JS modules..." -ForegroundColor Yellow
        if (-not (Test-Path $SharedDest)) {
            New-Item -ItemType Directory -Path $SharedDest -Force | Out-Null
        }
        Copy-Item -Path (Join-Path $SharedSource "*.js") -Destination $SharedDest -Force
        Write-Host "[OK] Shared JS modules copied" -ForegroundColor Green
    } else {
        Write-Host "[OK] Shared JS modules already in assets" -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] Shared JS source not found: $SharedSource" -ForegroundColor Yellow
}

# ── Summary ──────────────────────────────────────────────
Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Open $AndroidDir in Android Studio" -ForegroundColor White
Write-Host "  2. Sync Gradle (File > Sync Project with Gradle Files)" -ForegroundColor White
Write-Host "  3. Run on an emulator or device" -ForegroundColor White
Write-Host ""
Write-Host "Note: The first NDK build will take several minutes" -ForegroundColor Yellow
Write-Host "      as it compiles llama.cpp from source." -ForegroundColor Yellow
