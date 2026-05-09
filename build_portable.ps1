# =============================================================================
# PathDictate v0.2.1 - Portable Package Build Script
# =============================================================================
#
# Run from the project root (PowerShell 5+ required, included with Windows 10/11):
#   powershell -ExecutionPolicy Bypass -File build_portable.ps1
#
# Parameters:
#   -Model   <name>   Whisper model to bundle: small (default), base, large-v3
#   -SkipZip          Build folder only, skip ZIP creation
#   -Clean            Force clean rebuild if output folder already exists
#
# What this script does:
#   1.  Creates  PathDictate_v0.2.1_Portable\  folder structure
#   2.  Downloads Python 3.13.7 embeddable runtime  (~11 MB)
#   3.  Patches embeddable Python with tkinter from local Python 3.13 install
#   4.  Copies required packages from project venv  (excludes scipy/pip/wheel)
#   5.  Copies all app source .py files flat into the package root
#   6.  Downloads faster-whisper-<Model> via HuggingFace Hub  (~245 MB for small)
#       Falls back to local HF cache when internet is unavailable
#   7.  Writes portable  config\config.yaml  and data files
#   8.  Creates  START_PATHDICTATE.bat  launcher
#   9.  Creates  VERSION.txt  and  README_QUICK_START.txt
#  10.  ZIPs everything to  PathDictate_v0.2.1_Portable.zip
#
# Prerequisites (build machine only):
#   - Python 3.13 installed   (auto-detected)
#   - .\venv\  exists with all packages installed
#   - Internet access to download: Python embeddable, faster-whisper model
#     (internet is only needed on the BUILD machine, not on end-user machines)
# =============================================================================

param(
    [string]$Model   = "small",
    [switch]$SkipZip = $false,
    [switch]$Clean   = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Constants ────────────────────────────────────────────────────────────────
$Version    = "0.2.1"
$PyVer      = "3.13.7"
$OutName    = "PathDictate_v${Version}_Portable"
$ScriptRoot = $PSScriptRoot
$OutDir     = Join-Path $ScriptRoot $OutName
$ZipOut     = Join-Path $ScriptRoot "${OutName}.zip"
$EmbedZip   = Join-Path $env:TEMP "python-${PyVer}-embed-amd64.zip"
$EmbedUrl   = "https://www.python.org/ftp/python/${PyVer}/python-${PyVer}-embed-amd64.zip"
$HFRepo     = "Systran/faster-whisper-${Model}"
$ModelDir   = Join-Path $OutDir "models\faster-whisper-${Model}"

# ── Colour helpers ───────────────────────────────────────────────────────────
function Write-Step { param([string]$msg) Write-Host "`n>> $msg" -ForegroundColor Cyan  }
function Write-OK   { param([string]$msg) Write-Host "   OK  $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "   !!  $msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$msg) Write-Host "  ERR  $msg" -ForegroundColor Red   }

# ── Helper: write model placeholder README ───────────────────────────────────
function Write-ModelPlaceholder {
    param([string]$Dir, [string]$ModelName)
    $content = "Place your faster-whisper-${ModelName} model files here.`r`n`r`n" +
               "Required files:`r`n" +
               "  model.bin`r`n" +
               "  config.json`r`n" +
               "  tokenizer.json`r`n" +
               "  vocabulary.json`r`n`r`n" +
               "Download command (run once with internet access):`r`n" +
               "  python -c `"from huggingface_hub import snapshot_download; " +
               "snapshot_download('Systran/faster-whisper-${ModelName}', local_dir='.', local_dir_use_symlinks=False)`"`r`n"
    Set-Content (Join-Path $Dir "PLACE_MODEL_FILES_HERE.txt") $content -Encoding UTF8
    Write-Warn "Model placeholder written to models\faster-whisper-${ModelName}\"
}

# ── Helper: directory size in MB ─────────────────────────────────────────────
function Get-DirMB {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return 0.0 }
    $bytes = (Get-ChildItem $Path -Recurse -File -ErrorAction SilentlyContinue |
              Measure-Object -Property Length -Sum).Sum
    if (-not $bytes) { return 0.0 }
    return [math]::Round($bytes / 1MB, 1)
}

# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  PathDictate v${Version} - Portable Package Builder" -ForegroundColor Cyan
Write-Host "  Model: faster-whisper-${Model}" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ── Phase 0 : Preflight ──────────────────────────────────────────────────────
Write-Step "Phase 0 - Preflight checks"

# Locate Python 3.13
$PyRoot = $null
$PyCandidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313",
    "C:\Python313",
    "C:\Program Files\Python313",
    "C:\Program Files (x86)\Python313"
)
foreach ($c in $PyCandidates) {
    if (Test-Path "$c\python.exe") { $PyRoot = $c; break }
}
if (-not $PyRoot) {
    $pCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pCmd) {
        $candidate = Split-Path $pCmd.Source
        if (Test-Path "$candidate\python313.dll") { $PyRoot = $candidate }
    }
}
if (-not $PyRoot) {
    Write-Fail "Python 3.13 installation not found."
    Write-Fail "Install Python 3.13 from https://python.org and re-run this script."
    exit 1
}
Write-OK "Python 3.13: $PyRoot"

# Locate project venv
$VenvPy = Join-Path $ScriptRoot "venv\Scripts\python.exe"
$VenvSP = Join-Path $ScriptRoot "venv\Lib\site-packages"
if (-not (Test-Path $VenvPy)) {
    Write-Fail "venv not found at .\venv\Scripts\python.exe"
    Write-Fail "Run:  python -m venv venv"
    Write-Fail "Then: venv\Scripts\pip install -r requirements.txt"
    exit 1
}
Write-OK "venv: $VenvPy"

# Clean previous build
if ($Clean -and (Test-Path $OutDir)) {
    Write-Warn "Removing previous build: $OutDir"
    Remove-Item $OutDir -Recurse -Force
}

# ── Phase 1 : Folder structure ───────────────────────────────────────────────
Write-Step "Phase 1 - Creating folder structure"

$Folders = @(
    $OutDir,
    (Join-Path $OutDir "runtime"),
    (Join-Path $OutDir "runtime\DLLs"),
    (Join-Path $OutDir "runtime\Lib"),
    (Join-Path $OutDir "runtime\Lib\site-packages"),
    (Join-Path $OutDir "config"),
    (Join-Path $OutDir "data"),
    (Join-Path $OutDir "models"),
    (Join-Path $OutDir "audio"),
    (Join-Path $OutDir "drafts"),
    (Join-Path $OutDir "autosave"),
    (Join-Path $OutDir "exports"),
    (Join-Path $OutDir "logs")
)
foreach ($f in $Folders) { New-Item -ItemType Directory -Path $f -Force | Out-Null }
Write-OK "Folder tree created"

# ── Phase 2 : Python embeddable runtime ──────────────────────────────────────
Write-Step "Phase 2 - Python $PyVer embeddable runtime"

if (-not (Test-Path $EmbedZip)) {
    Write-Host "   Downloading Python embeddable from python.org..." -ForegroundColor Gray
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $EmbedUrl -OutFile $EmbedZip -UseBasicParsing
        Write-OK "Downloaded: $EmbedZip"
    }
    catch {
        Write-Fail "Download failed: $_"
        Write-Fail "Re-run with internet access, or place the file manually at: $EmbedZip"
        exit 1
    }
} else {
    Write-OK "Using cached embeddable: $EmbedZip"
}

$RuntimeDir = Join-Path $OutDir "runtime"
Expand-Archive -Path $EmbedZip -DestinationPath $RuntimeDir -Force
Write-OK "Embeddable extracted to runtime\"

# Patch python313._pth to enable Lib\ and site-packages
$PthFile    = Join-Path $RuntimeDir "python313._pth"
$PthContent = "python313.zip`n.`nLib`nLib\site-packages`nimport site`n"
[System.IO.File]::WriteAllText($PthFile, $PthContent, [System.Text.Encoding]::ASCII)
Write-OK "python313._pth patched (site-packages enabled)"

# Copy VC runtime DLLs (embeddable already bundles these, but ensure present)
foreach ($dll in @("vcruntime140.dll", "vcruntime140_1.dll")) {
    $src = Join-Path $PyRoot $dll
    $dst = Join-Path $RuntimeDir $dll
    if ((Test-Path $src) -and (-not (Test-Path $dst))) {
        Copy-Item $src $dst -Force
    }
}
Write-OK "VC runtime DLLs ensured"

# ── Phase 3 : Tkinter support ────────────────────────────────────────────────
Write-Step "Phase 3 - Tkinter support"

$TkSrc = Join-Path $PyRoot "Lib\tkinter"
$TkDst = Join-Path $RuntimeDir "Lib\tkinter"
if (Test-Path $TkSrc) {
    Copy-Item $TkSrc -Destination $TkDst -Recurse -Force
    Write-OK "Lib\tkinter\ copied"
} else {
    Write-Warn "tkinter source not found at $TkSrc"
}

$DllsDst = Join-Path $RuntimeDir "DLLs"
foreach ($dll in @("_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "libffi-8.dll")) {
    $src = Join-Path $PyRoot "DLLs\$dll"
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $DllsDst $dll) -Force
        Write-OK "DLLs\$dll"
    } else {
        Write-Warn "$dll not found in $PyRoot\DLLs"
    }
}

$TclSrc = Join-Path $PyRoot "tcl"
$TclDst = Join-Path $RuntimeDir "tcl"
if (Test-Path $TclSrc) {
    Copy-Item $TclSrc -Destination $TclDst -Recurse -Force
    Write-OK "tcl\ scripts copied  ($('{0:N1}' -f (Get-DirMB $TclDst)) MB)"
} else {
    Write-Warn "tcl\ not found at $TclSrc"
}

# ── Phase 4 : Site-packages ──────────────────────────────────────────────────
Write-Step "Phase 4 - Copying site-packages (from venv)"

$PortSP  = Join-Path $RuntimeDir "Lib\site-packages"
$Exclude = @("pip", "setuptools", "wheel", "scipy", "scipy.libs",
             "shellingham", "typer", "_distutils_hack")

$TotalCopied = 0
foreach ($item in (Get-ChildItem $VenvSP)) {
    # Skip explicitly excluded names
    if ($Exclude -contains $item.Name) { continue }
    # Skip .dist-info, .data, .whl
    if ($item.Name -like "*.dist-info") { continue }
    if ($item.Name -like "*.data")      { continue }
    if ($item.Name -like "*.whl")       { continue }

    $dst = Join-Path $PortSP $item.Name
    if ($item.PSIsContainer) {
        Copy-Item $item.FullName -Destination $dst -Recurse -Force
    } else {
        Copy-Item $item.FullName -Destination $dst -Force
    }
    $TotalCopied++
}

# Copy any top-level .pyd extension modules (e.g. _cffi_backend.cp313*.pyd)
foreach ($pyd in (Get-ChildItem $VenvSP -Filter "*.pyd" -ErrorAction SilentlyContinue)) {
    Copy-Item $pyd.FullName (Join-Path $PortSP $pyd.Name) -Force
}

Write-OK "$TotalCopied items copied to runtime\Lib\site-packages\"
Write-OK "site-packages size: $('{0:N1}' -f (Get-DirMB $PortSP)) MB"

# ── Phase 5 : App source files ───────────────────────────────────────────────
Write-Step "Phase 5 - Copying app source files"

$AppFiles = @(
    "gui_app.py", "config.py", "audio_recorder.py", "transcriber.py",
    "terminology_corrector.py", "clipboard_handler.py",
    "rewrite_service.py", "ollama_client.py", "rewriter.py",
    "hotkey_manager.py", "pathology_dictation_app.py"
)
foreach ($f in $AppFiles) {
    $src = Join-Path $ScriptRoot $f
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $OutDir $f) -Force
        Write-OK $f
    } else {
        Write-Warn "$f not found - skipping"
    }
}
$icoSrc = Join-Path $ScriptRoot "app_icon.ico"
if (Test-Path $icoSrc) { Copy-Item $icoSrc (Join-Path $OutDir "app_icon.ico") -Force }

# ── Phase 6 : Config and data ────────────────────────────────────────────────
Write-Step "Phase 6 - Config, data and voice commands"

# Build portable config.yaml
$cfg  = "# PathDictate v${Version} Portable Edition - Runtime Configuration`r`n"
$cfg += "# ----------------------------------------------------------------`r`n"
$cfg += "# Paths starting with './' are relative to the portable folder root.`r`n`r`n"
$cfg += "offline_only: true`r`ndisable_telemetry: true`r`n`r`n"
$cfg += "model_path: ./models/faster-whisper-${Model}`r`n`r`n"
$cfg += "device: auto`r`ncpu_compute_type: int8`r`ncuda_compute_type: float16`r`n"
$cfg += "fallback_device: cpu`r`nfallback_compute_type: int8`r`n`r`n"
$cfg += "language: en`r`ntemperature: 0.0`r`nbeam_size: 5`r`nbest_of: 5`r`n`r`n"
$cfg += "hotkey_toggle_record: f9`r`nsample_rate: 16000`r`nchannels: 1`r`n`r`n"
$cfg += "dictionary_file: ./config/pathology_replacements.json`r`n"
$cfg += "terminology_enabled: true`r`ncase_sensitive: false`r`n`r`n"
$cfg += "show_transcription_live: true`r`nauto_copy_to_clipboard: true`r`n`r`n"
$cfg += "llm:`r`n"
$cfg += "  enabled: true`r`n  provider: ollama`r`n"
$cfg += "  endpoint: `"http://localhost:11434`"`r`n  model: `"qwen2.5:14b`"`r`n"
$cfg += "  auto_start_ollama: true`r`n  ollama_start_command: `"ollama serve`"`r`n"
$cfg += "  startup_wait_seconds: 30`r`n  startup_retry_interval_seconds: 2`r`n"
$cfg += "  temperature: 0.1`r`n  max_tokens: 512`r`n  timeout_seconds: 120`r`n`r`n"
$cfg += "privacy:`r`n  offline_only: true`r`n"
$cfg += "  log_transcripts_by_default: false`r`n  log_llm_requests: false`r`n"
Set-Content (Join-Path $OutDir "config\config.yaml") $cfg -Encoding UTF8
Write-OK "config\config.yaml"

$vcSrc = Join-Path $ScriptRoot "config\voice_commands.json"
if (Test-Path $vcSrc) {
    Copy-Item $vcSrc (Join-Path $OutDir "config\voice_commands.json") -Force
    Write-OK "config\voice_commands.json"
}

$dictSrc = Join-Path $ScriptRoot "data\pathology_dictionary.json"
if (Test-Path $dictSrc) {
    Copy-Item $dictSrc (Join-Path $OutDir "data\pathology_dictionary.json") -Force
    Copy-Item $dictSrc (Join-Path $OutDir "config\pathology_replacements.json") -Force
    Write-OK "data\pathology_dictionary.json + config\pathology_replacements.json"
}

# ── Phase 7 : Whisper model ──────────────────────────────────────────────────
Write-Step "Phase 7 - Whisper model (faster-whisper-${Model})"

New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null

$dlPy = @"
import sys, os, warnings
warnings.filterwarnings('ignore')
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
try:
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=sys.argv[2], local_dir=sys.argv[1],
        ignore_patterns=['*.msgpack','*.h5','flax_model*','tf_model*','rust_model*','onnx/*'],
    )
    print('MODEL_OK')
except Exception as e:
    print(f'FAIL:{e}', file=sys.stderr)
    sys.exit(1)
"@
$dlScript = Join-Path $env:TEMP "pd_dl_model.py"
Set-Content $dlScript $dlPy -Encoding UTF8

Write-Host "   Downloading $HFRepo  (this may take several minutes)..." -ForegroundColor Gray
# Temporarily relax error preference so native-exe stderr doesn't abort the script
$_prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $VenvPy $dlScript $ModelDir $HFRepo 2>&1 | Out-Null
$dlOK = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $_prevEAP

if (-not $dlOK) {
    Write-Warn "Online download failed - checking local HF cache..."
    $hfCache = Join-Path $ScriptRoot "models\models--Systran--faster-whisper-${Model}"
    if (Test-Path $hfCache) {
        $snap = Get-ChildItem (Join-Path $hfCache "snapshots") -Directory |
                Select-Object -First 1
        if ($snap) {
            foreach ($item in (Get-ChildItem $snap.FullName)) {
                $realPath = $item.FullName
                # Dereference Windows symlinks (junctions / reparse points)
                if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    $target = (Get-Item $item.FullName -Force).Target
                    if ($target -and (Test-Path $target)) { $realPath = $target }
                }
                Copy-Item $realPath (Join-Path $ModelDir $item.Name) -Force -ErrorAction SilentlyContinue
            }
            Write-OK "Copied model from local HF cache: $($snap.FullName)"
            $dlOK = $true
        }
    }
    if (-not $dlOK) {
        Write-Warn "Model not available - portable package will need model added manually."
        Write-ModelPlaceholder -Dir $ModelDir -ModelName $Model
    }
}

if ($dlOK) {
    # Validate — vocabulary file can be .json (older models) or .txt (newer models)
    $hasVocab = (Test-Path (Join-Path $ModelDir "vocabulary.json")) -or
                (Test-Path (Join-Path $ModelDir "vocabulary.txt"))
    $required = @("model.bin", "config.json", "tokenizer.json")
    $missing  = @($required | Where-Object { -not (Test-Path (Join-Path $ModelDir $_)) })
    if (-not $hasVocab) { $missing += "vocabulary.json/txt" }
    if ($missing.Count -eq 0) {
        Write-OK "Model OK - all required files present"
        Write-OK "Model size: $('{0:N1}' -f (Get-DirMB $ModelDir)) MB"
    } else {
        Write-Warn "Model incomplete - missing: $($missing -join ', ')"
    }
}

# ── Phase 8 : START_PATHDICTATE.bat ─────────────────────────────────────────
Write-Step "Phase 8 - Creating START_PATHDICTATE.bat"

# Write the launcher as a literal string (no PS variable expansion inside)
$launcherLines = @(
    "@echo off",
    "setlocal EnableDelayedExpansion",
    "title PathDictate v0.2.1",
    "cd /d `"%~dp0`"",
    "",
    "if not exist `"runtime\pythonw.exe`" (",
    "    echo.",
    "    echo  ERROR: runtime\pythonw.exe not found.",
    "    echo  Re-download PathDictate_v0.2.1_Portable.zip from GitHub Releases.",
    "    pause",
    "    exit /b 1",
    ")",
    "if not exist `"gui_app.py`" (",
    "    echo.",
    "    echo  ERROR: gui_app.py not found.",
    "    pause",
    "    exit /b 1",
    ")",
    "",
    "set PATHDICTATE_PORTABLE=1",
    "set PATHDICTATE_ROOT=%~dp0",
    "set HF_HUB_OFFLINE=1",
    "set TRANSFORMERS_OFFLINE=1",
    "set HF_HUB_DISABLE_TELEMETRY=1",
    "set HF_HUB_DISABLE_SYMLINKS_WARNING=1",
    "set PYTHONDONTWRITEBYTECODE=1",
    "set PYTHONIOENCODING=utf-8",
    "",
    "set TCL_LIBRARY=%~dp0runtime\tcl\tcl8.6",
    "set TK_LIBRARY=%~dp0runtime\tcl\tk8.6",
    "",
    "start `"`" `"%~dp0runtime\pythonw.exe`" `"%~dp0gui_app.py`"",
    "endlocal"
)
[System.IO.File]::WriteAllLines(
    (Join-Path $OutDir "START_PATHDICTATE.bat"),
    $launcherLines,
    [System.Text.Encoding]::ASCII)
Write-OK "START_PATHDICTATE.bat"

# ── Phase 9 : Documentation ──────────────────────────────────────────────────
Write-Step "Phase 9 - Documentation"

$builtDate = (Get-Date -Format "yyyy-MM-dd")

$verLines = @(
    "PathDictate v${Version} Portable Edition",
    "=========================================",
    "Built:   ${builtDate}",
    "Python:  ${PyVer}",
    "Model:   faster-whisper-${Model}",
    "Source:  https://github.com/RNAi-C/Dictation_path",
    "",
    "Features",
    "--------",
    "  Offline pathology dictation (no internet needed)",
    "  Editable corrected-text panel",
    "  Undo / Redo  (Ctrl+Z / Ctrl+Y)",
    "  Open / Save text draft  (Ctrl+O / Ctrl+S)",
    "  Autosave every 60 seconds",
    "  Local Whisper transcription  (faster-whisper-${Model})",
    "  User-selectable Whisper model folder",
    "  F9 hotkey to start/stop recording",
    "  Pathology terminology correction dictionary",
    "  Optional local Qwen rewrite via Ollama  (not bundled)",
    "",
    "System Requirements",
    "-------------------",
    "  Windows 10 or 11  (64-bit)",
    "  4 GB RAM minimum, 8 GB recommended",
    "  NVIDIA GPU optional  (CUDA auto-detected for faster transcription)",
    "  Microphone required",
    "",
    "Privacy",
    "-------",
    "  Fully offline.  No cloud.  No telemetry.  No internet required.",
    "  Audio is never saved permanently.",
    "  Drafts and autosave files remain on this computer only.",
    "",
    "Limitations",
    "-----------",
    "  Ollama / Qwen rewrite requires separate Ollama installation",
    "  GPU support requires NVIDIA CUDA drivers",
    "  First launch may take 10-30 s while the Whisper model loads"
)
[System.IO.File]::WriteAllLines(
    (Join-Path $OutDir "VERSION.txt"),
    $verLines,
    [System.Text.UTF8Encoding]::new($false))
Write-OK "VERSION.txt"

$readmeLines = @(
    "PathDictate v${Version} - Quick Start Guide",
    "============================================",
    "",
    "GETTING STARTED",
    "---------------",
    "1.  Extract the ZIP file to any folder  (Desktop, USB drive, etc.)",
    "2.  Open the extracted folder",
    "3.  Double-click  START_PATHDICTATE.bat",
    "4.  Wait 10-30 seconds for the Whisper model to load",
    "5.  You are ready to dictate!",
    "",
    "HOW TO DICTATE",
    "--------------",
    "  Press F9       Start recording  (button turns red, timer counts)",
    "  Speak clearly into your microphone",
    "  Press F9       Stop recording  (app transcribes automatically)",
    "  Text appears   in the Corrected panel, ready to edit",
    "",
    "  Ctrl+S         Save your draft as a text file",
    "  Ctrl+O         Open a saved draft",
    "  Ctrl+Z         Undo",
    "  Ctrl+Y         Redo",
    "  Ctrl+Shift+R   Rewrite selected text with Qwen AI  (requires Ollama)",
    "",
    "SAVING YOUR WORK",
    "----------------",
    "  File > Save                 Save current draft",
    "  File > Save As              Choose where to save",
    "  File > Export as .docx      Export as Word document",
    "",
    "  Autosave runs every 60 seconds to:  autosave\PathDictate_autosave.txt",
    "",
    "CHANGING THE WHISPER MODEL",
    "--------------------------",
    "  Settings > Browse Model...  Select a different model folder",
    "  Place model folders inside the  models\  folder for easy access.",
    "  Models must be in faster-whisper / CTranslate2 format.",
    "",
    "QWEN AI REWRITE  (OPTIONAL)",
    "---------------------------",
    "  The rewrite feature requires Ollama installed separately.",
    "  The app works FULLY without Ollama - only rewrite is unavailable.",
    "",
    "  To enable:",
    "    1. Download Ollama:  https://ollama.ai",
    "    2. Install and run Ollama",
    "    3. Open a command prompt and run:  ollama pull qwen2.5:14b",
    "    4. Restart PathDictate - the rewrite button will be enabled",
    "",
    "  The AI rewrites STYLE only, never invents or infers clinical findings.",
    "  All requests stay on this computer  (localhost only).",
    "",
    "TROUBLESHOOTING",
    "---------------",
    "  App does not start?",
    "    Try: right-click START_PATHDICTATE.bat > Run as administrator",
    "",
    "  No microphone detected?",
    "    Check Windows sound settings  (right-click speaker icon in taskbar)",
    "    Make sure your microphone is the default recording device",
    "",
    "  Transcription is slow?",
    "    Normal on CPU: 5-20 seconds per 30-second recording",
    "    Install NVIDIA GPU drivers for automatic speed-up",
    "",
    "  Rewrite button greyed out?",
    "    Ollama is not running - see QWEN AI REWRITE section above",
    "",
    "PRIVACY",
    "-------",
    "  No cloud.  No internet.  No telemetry.",
    "  Audio is never saved permanently.",
    "  Drafts remain on this computer only.",
    "  AI rewrite sends text to localhost only  (your own computer)."
)
[System.IO.File]::WriteAllLines(
    (Join-Path $OutDir "README_QUICK_START.txt"),
    $readmeLines,
    [System.Text.UTF8Encoding]::new($false))
Write-OK "README_QUICK_START.txt"

# ── Phase 10 : Cleanup ───────────────────────────────────────────────────────
Write-Step "Phase 10 - Cleaning up caches"

Get-ChildItem $OutDir -Recurse -Include "__pycache__" -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $OutDir -Recurse -Include "*.pyc","*.pyo" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Remove test directories inside third-party packages  (~20-40 MB saved)
foreach ($testDir in @("tests", "test")) {
    Get-ChildItem (Join-Path $RuntimeDir "Lib\site-packages") `
        -Recurse -Filter $testDir -Directory -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Write-OK "Caches and test directories removed"

# ── Phase 11 : Size report ───────────────────────────────────────────────────
Write-Step "Phase 11 - Build size report"

$mbRuntime = Get-DirMB (Join-Path $OutDir "runtime")
$mbModel   = Get-DirMB (Join-Path $OutDir "models")
$mbTotal   = Get-DirMB $OutDir

Write-Host ""
Write-Host ("   runtime\          : {0,7:N1} MB" -f $mbRuntime) -ForegroundColor White
Write-Host ("   models\           : {0,7:N1} MB" -f $mbModel)   -ForegroundColor White
Write-Host ("   TOTAL folder      : {0,7:N1} MB" -f $mbTotal)   -ForegroundColor Cyan

# ── Phase 12 : ZIP ───────────────────────────────────────────────────────────
if (-not $SkipZip) {
    Write-Step "Phase 12 - Creating ZIP"

    if (Test-Path $ZipOut) { Remove-Item $ZipOut -Force }
    Compress-Archive -Path $OutDir -DestinationPath $ZipOut -CompressionLevel Optimal
    $zipMB = [math]::Round((Get-Item $ZipOut).Length / 1MB, 1)
    Write-OK "ZIP: ${OutName}.zip  (${zipMB} MB)"
    Write-Host ""
    Write-Host "   Distribution file: $ZipOut" -ForegroundColor Green
} else {
    Write-Warn "ZIP skipped (-SkipZip flag set)"
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  PathDictate v${Version} Portable build COMPLETE!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Test locally:" -ForegroundColor Cyan
Write-Host "    cd `"$OutDir`"" -ForegroundColor Gray
Write-Host "    .\START_PATHDICTATE.bat" -ForegroundColor Gray
Write-Host ""
Write-Host "  Verify build:" -ForegroundColor Cyan
Write-Host "    python packaging\portable_checks.py" -ForegroundColor Gray
Write-Host ""
Write-Host "  Distribute:" -ForegroundColor Cyan
Write-Host "    Upload ${OutName}.zip to GitHub Releases" -ForegroundColor Gray
Write-Host "    (or copy the folder to a USB drive)" -ForegroundColor Gray
Write-Host ""
