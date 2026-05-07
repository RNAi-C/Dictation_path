#Requires -Version 5.1
<#
.SYNOPSIS
    Build the PathDictate_Portable offline package.

.DESCRIPTION
    Run this script ONCE on the BUILD machine (requires internet for FFmpeg
    download only; Python and models must already be present).

    What it does:
      1. Copies the full Python 3.11 runtime (including Tcl/Tk for the GUI).
      2. Copies installed site-packages from the existing venv.
      3. Flattens the Whisper model HuggingFace cache into clean model folders.
      4. Downloads FFmpeg (static build, ~120 MB) if not already present.
      5. Copies all application source files.
      6. Writes start_app.bat, config files, and tool scripts.
      7. Generates SHA-256 checksums for the entire package.

.PARAMETER OutputDir
    Where to create the portable folder. Defaults to .\PathDictate_Portable.

.PARAMETER IncludeLargeV3
    If set, also package the large-v3 model (~1.5 GB, GPU recommended).

.EXAMPLE
    .\package_portable_offline.ps1
    .\package_portable_offline.ps1 -OutputDir "D:\Deploy\PathDictate_Portable"
    .\package_portable_offline.ps1 -IncludeLargeV3
#>
param(
    [string]$OutputDir     = "",
    [switch]$IncludeLargeV3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Paths ─────────────────────────────────────────────────────────────────────
$ScriptDir  = $PSScriptRoot
if (-not $OutputDir) { $OutputDir = Join-Path $ScriptDir "PathDictate_Portable" }
$VenvDir    = Join-Path $ScriptDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# Discover the base Python installation the venv was built from
$PythonHome = (& $VenvPython -c "import sys; print(sys.base_prefix)").Trim()
if (-not (Test-Path $PythonHome)) {
    Write-Error "Cannot find Python installation at: $PythonHome"
}

# ── Banner ────────────────────────────────────────────────────────────────────
function Write-Banner([string]$msg) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "[+] $msg" -ForegroundColor Yellow
}

function Write-OK([string]$msg)   { Write-Host "    OK  $msg" -ForegroundColor Green  }
function Write-Warn([string]$msg) { Write-Host "    !!  $msg" -ForegroundColor Magenta }

Write-Banner "PathDictate Portable — Build Script"
Write-Host "Source project : $ScriptDir"
Write-Host "Python home    : $PythonHome"
Write-Host "Output folder  : $OutputDir"

# ── 0. Confirm / clean output ─────────────────────────────────────────────────
Write-Step "0. Preparing output directory"
if (Test-Path $OutputDir) {
    $confirm = Read-Host "  Output folder already exists. Delete and rebuild? [y/N]"
    if ($confirm -ne "y") { Write-Host "Aborted."; exit 0 }
    Remove-Item $OutputDir -Recurse -Force
    Write-OK "Deleted old output"
}

$Dirs = @(
    "$OutputDir\app",
    "$OutputDir\runtime\python",
    "$OutputDir\models",
    "$OutputDir\ffmpeg\bin",
    "$OutputDir\config",
    "$OutputDir\data",
    "$OutputDir\audio",
    "$OutputDir\logs",
    "$OutputDir\tools",
    "$OutputDir\checksums"
)
foreach ($d in $Dirs) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
Write-OK "Directory structure created"

# ── 1. Copy Python runtime ────────────────────────────────────────────────────
Write-Step "1. Copying Python runtime  ($PythonHome)"

$PythonDest   = "$OutputDir\runtime\python"
$ExcludedDirs = @("Doc", "Tools", "include", "libs", "NEWS.txt", "LICENSE.txt")

# Copy everything except excluded dirs/files
Get-ChildItem $PythonHome | Where-Object { $_.Name -notin $ExcludedDirs } | ForEach-Object {
    $src  = $_.FullName
    $dest = Join-Path $PythonDest $_.Name
    if ($_.PSIsContainer) {
        # Skip Lib\test (large, not needed at runtime)
        if ($_.Name -eq "Lib") {
            Copy-Item $src $dest -Recurse -Force
            # Remove test directories to save space
            $testDirs = @("test", "tests", "unittest\test", "lib2to3\tests",
                          "email\test", "sqlite3\test", "tkinter\test",
                          "distutils\tests", "importlib\test", "xmlrpc\test")
            foreach ($td in $testDirs) {
                $tdPath = Join-Path $dest $td
                if (Test-Path $tdPath) {
                    Remove-Item $tdPath -Recurse -Force
                }
            }
        } else {
            Copy-Item $src $dest -Recurse -Force
        }
    } else {
        Copy-Item $src $dest -Force
    }
}
Write-OK "Python runtime copied"

# ── 2. Copy venv site-packages into bundled Python ───────────────────────────
Write-Step "2. Copying site-packages from venv"

$SrcSitePackages  = Join-Path $VenvDir "Lib\site-packages"
$DestSitePackages = Join-Path $PythonDest "Lib\site-packages"

# Merge — don't wipe the stdlib's site-packages entirely
Copy-Item "$SrcSitePackages\*" $DestSitePackages -Recurse -Force

# Also copy Scripts from venv (entry-point executables) only for packages that need them
# (not needed for the app; skip to keep package lean)

Write-OK "Site-packages copied  (~$('{0:N0}' -f ((Get-ChildItem $DestSitePackages -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB)) MB)"

# ── 3. Copy application source files ─────────────────────────────────────────
Write-Step "3. Copying application source files"

$AppFiles = @(
    "gui_app.py",
    "config.py",
    "transcriber.py",
    "audio_recorder.py",
    "clipboard_handler.py",
    "hotkey_manager.py",
    "terminology_corrector.py",
    "pathology_dictation_app.py",
    "app_icon.ico"
)
foreach ($f in $AppFiles) {
    $src = Join-Path $ScriptDir $f
    if (Test-Path $src) {
        Copy-Item $src (Join-Path "$OutputDir\app" $f) -Force
        Write-OK $f
    } else {
        Write-Warn "Not found: $f  (skipped)"
    }
}

# ── 4. Flatten Whisper model cache ────────────────────────────────────────────
Write-Step "4. Flattening Whisper model cache"

function Copy-WhisperModel {
    param([string]$CacheDir, [string]$DestName)

    $snapshotsDir = Join-Path $CacheDir "snapshots"
    if (-not (Test-Path $snapshotsDir)) {
        Write-Warn "No snapshots directory in $CacheDir — skipping"
        return $false
    }

    # Get the first (only) snapshot hash folder
    $snapshot = Get-ChildItem $snapshotsDir -Directory | Select-Object -First 1
    if (-not $snapshot) {
        Write-Warn "Empty snapshots directory in $CacheDir — skipping"
        return $false
    }

    $destDir = "$OutputDir\models\$DestName"
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null

    # Read each file through .NET (follows symlinks transparently)
    $modelFiles = @("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
    foreach ($fname in $modelFiles) {
        $src = Join-Path $snapshot.FullName $fname
        $dst = Join-Path $destDir $fname
        if (Test-Path $src) {
            # ReadAllBytes follows NTFS symlinks; handles both real symlinks and copies
            [System.IO.File]::Copy($src, $dst, $true)
        } else {
            Write-Warn "Missing $fname in $($snapshot.Name)"
        }
    }

    $sizeMB = (Get-ChildItem $destDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-OK "$DestName  ($('{0:N0}' -f $sizeMB) MB)"
    return $true
}

$ModelsSourceDir = Join-Path $ScriptDir "models"

# Base model (fast, good for CPU)
$baseSrc = Join-Path $ModelsSourceDir "models--Systran--faster-whisper-base"
if (Test-Path $baseSrc) {
    Copy-WhisperModel $baseSrc "faster-whisper-base" | Out-Null
} else {
    Write-Warn "faster-whisper-base not found in $ModelsSourceDir"
    Write-Warn "Run the app once to download it, then re-run this script."
    Write-Warn "Package will continue but may have no default model."
}

# Large-v3 (optional, GPU recommended)
if ($IncludeLargeV3) {
    $lgSrc = Join-Path $ModelsSourceDir "models--Systran--faster-whisper-large-v3"
    if (Test-Path $lgSrc) {
        Copy-WhisperModel $lgSrc "faster-whisper-large-v3" | Out-Null
    } else {
        Write-Warn "faster-whisper-large-v3 not in cache — skipping"
    }
}

# ── 5. FFmpeg ─────────────────────────────────────────────────────────────────
Write-Step "5. FFmpeg"

$FfmpegDest = "$OutputDir\ffmpeg\bin\ffmpeg.exe"
# Check if user already put ffmpeg in the project
$FfmpegLocal = Join-Path $ScriptDir "ffmpeg\bin\ffmpeg.exe"
if (Test-Path $FfmpegLocal) {
    Copy-Item $FfmpegLocal $FfmpegDest -Force
    Write-OK "FFmpeg copied from project folder"
} else {
    Write-Host "    Downloading FFmpeg static build for Windows x64 ..."
    $FfmpegZipUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $TmpZip = Join-Path $env:TEMP "ffmpeg_tmp.zip"
    $TmpDir = Join-Path $env:TEMP "ffmpeg_tmp_extract"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $FfmpegZipUrl -OutFile $TmpZip -UseBasicParsing
        Expand-Archive $TmpZip -DestinationPath $TmpDir -Force
        # The zip contains a top-level folder; find ffmpeg.exe inside bin/
        $ExtractedExe = Get-ChildItem $TmpDir -Recurse -Filter "ffmpeg.exe" |
                        Where-Object { $_.FullName -like "*\bin\ffmpeg.exe" } |
                        Select-Object -First 1
        if ($ExtractedExe) {
            Copy-Item $ExtractedExe.FullName $FfmpegDest -Force
            Write-OK "FFmpeg downloaded and placed"
        } else {
            throw "ffmpeg.exe not found in archive"
        }
    } catch {
        Write-Warn "FFmpeg download failed: $_"
        Write-Warn "App will still work for microphone dictation without FFmpeg."
        Write-Warn "To add manually: place ffmpeg.exe in ffmpeg\bin\ inside the portable folder."
    } finally {
        if (Test-Path $TmpZip) { Remove-Item $TmpZip -Force }
        if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    }
}

# ── 6. Config files ────────────────────────────────────────────────────────────
Write-Step "6. Config and dictionary files"

Copy-Item (Join-Path $ScriptDir "config\config.yaml")                   "$OutputDir\config\config.yaml" -Force
Copy-Item (Join-Path $ScriptDir "config\pathology_replacements.json")   "$OutputDir\config\pathology_replacements.json" -Force
Write-OK "config.yaml"
Write-OK "pathology_replacements.json"

# ── 7. Tool scripts ────────────────────────────────────────────────────────────
Write-Step "7. Tool scripts"

foreach ($t in @("verify_offline_ready.py","generate_checksums.py","verify_checksums.py")) {
    $src = Join-Path $ScriptDir "tools\$t"
    if (Test-Path $src) {
        Copy-Item $src "$OutputDir\tools\$t" -Force
        Write-OK $t
    }
}

# ── 8. Write start_app.bat ────────────────────────────────────────────────────
Write-Step "8. Writing start_app.bat"

$StartBat = @'
@echo off
setlocal EnableDelayedExpansion

:: ── Portable root ─────────────────────────────────────────────────────────────
set "PORTABLE_DIR=%~dp0"
:: Remove trailing backslash
if "!PORTABLE_DIR:~-1!"=="\" set "PORTABLE_DIR=!PORTABLE_DIR:~0,-1!"

set "PYTHON_DIR=!PORTABLE_DIR!\runtime\python"

:: ── Offline guards ────────────────────────────────────────────────────────────
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_DATASETS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "TOKENIZERS_PARALLELISM=false"
set "NO_COLOR=1"

:: ── Portable mode flags (read by config.py) ───────────────────────────────────
set "PATHDICTATE_PORTABLE=1"
set "PATHDICTATE_ROOT=!PORTABLE_DIR!"

:: ── Python environment ────────────────────────────────────────────────────────
set "PYTHONHOME=!PYTHON_DIR!"
set "PATH=!PYTHON_DIR!;!PYTHON_DIR!\DLLs;!PORTABLE_DIR!\ffmpeg\bin;%PATH%"

:: ── Run the app ───────────────────────────────────────────────────────────────
cd /d "!PORTABLE_DIR!\app"
start "" "!PYTHON_DIR!\pythonw.exe" "!PORTABLE_DIR!\app\gui_app.py"

endlocal
'@

$StartBat | Out-File -FilePath "$OutputDir\start_app.bat" -Encoding ASCII

# Also write a console version for debugging
$DebugBat = @'
@echo off
setlocal EnableDelayedExpansion

set "PORTABLE_DIR=%~dp0"
if "!PORTABLE_DIR:~-1!"=="\" set "PORTABLE_DIR=!PORTABLE_DIR:~0,-1!"

set "PYTHON_DIR=!PORTABLE_DIR!\runtime\python"

set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_DATASETS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "TOKENIZERS_PARALLELISM=false"
set "PATHDICTATE_PORTABLE=1"
set "PATHDICTATE_ROOT=!PORTABLE_DIR!"
set "PYTHONHOME=!PYTHON_DIR!"
set "PATH=!PYTHON_DIR!;!PYTHON_DIR!\DLLs;!PORTABLE_DIR!\ffmpeg\bin;%PATH%"

cd /d "!PORTABLE_DIR!\app"
echo Running with Python: !PYTHON_DIR!\python.exe
echo Portable root      : !PORTABLE_DIR!
echo.
"!PYTHON_DIR!\python.exe" "!PORTABLE_DIR!\app\gui_app.py"
echo.
echo App exited with code: %ERRORLEVEL%
pause

endlocal
'@

$DebugBat | Out-File -FilePath "$OutputDir\start_app_debug.bat" -Encoding ASCII
Write-OK "start_app.bat"
Write-OK "start_app_debug.bat  (shows console output for troubleshooting)"

# Also write the verify / checksum runner
$VerifyBat = @'
@echo off
setlocal EnableDelayedExpansion
set "PORTABLE_DIR=%~dp0"
if "!PORTABLE_DIR:~-1!"=="\" set "PORTABLE_DIR=!PORTABLE_DIR:~0,-1!"
set "PYTHONHOME=!PORTABLE_DIR!\runtime\python"
set "PATH=!PORTABLE_DIR!\runtime\python;!PORTABLE_DIR!\runtime\python\DLLs;%PATH%"
set "PATHDICTATE_PORTABLE=1"
set "PATHDICTATE_ROOT=!PORTABLE_DIR!"
set "HF_HUB_OFFLINE=1"
"!PORTABLE_DIR!\runtime\python\python.exe" "!PORTABLE_DIR!\tools\verify_offline_ready.py"
pause
endlocal
'@
$VerifyBat | Out-File -FilePath "$OutputDir\verify_install.bat" -Encoding ASCII
Write-OK "verify_install.bat"

# ── 9. README ─────────────────────────────────────────────────────────────────
Write-Step "9. Writing README_OFFLINE_PORTABLE.md"

$ReadmePath = Join-Path $ScriptDir "README_OFFLINE_PORTABLE.md"
if (Test-Path $ReadmePath) {
    Copy-Item $ReadmePath "$OutputDir\README_OFFLINE_PORTABLE.md" -Force
    Write-OK "README_OFFLINE_PORTABLE.md"
} else {
    Write-Warn "README not found in project — skipping"
}

# ── 10. Generate checksums ────────────────────────────────────────────────────
Write-Step "10. Generating checksums"

$ChecksumScript = "$OutputDir\tools\generate_checksums.py"
if (Test-Path $ChecksumScript) {
    & (Join-Path $PythonDest "python.exe") $ChecksumScript
    Write-OK "checksums/SHA256SUMS.txt written"
} else {
    Write-Warn "Checksum script not found — skipping"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Banner "Build Complete"

$TotalMB = (Get-ChildItem $OutputDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ""
Write-Host "  Output      : $OutputDir"
Write-Host ("  Total size  : {0:N0} MB" -f $TotalMB)
Write-Host ""
Write-Host "  NEXT STEPS"
Write-Host "  1. Copy the entire folder to the target computer."
Write-Host "  2. Double-click  start_app.bat  to launch."
Write-Host "  3. Optional: run  verify_install.bat  to confirm everything is OK."
Write-Host ""
Write-Host "  No internet required on the target computer." -ForegroundColor Green
Write-Host ""
