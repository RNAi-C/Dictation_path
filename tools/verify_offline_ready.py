"""
verify_offline_ready.py
Run from the portable folder root:
    runtime\python\python.exe tools\verify_offline_ready.py

Checks that every component needed for offline operation is present
and that CPU-only transcription actually works.
"""

import os
import sys
import json
import importlib
from pathlib import Path

# ── helpers ───────────────────────────────────────────────────────────────────
PASS  = "[  OK  ]"
FAIL  = "[ FAIL ]"
WARN  = "[ WARN ]"
INFO  = "[ INFO ]"
SEP   = "-" * 70

def ok(msg):  print(f"{PASS} {msg}")
def fail(msg, fatal=True):
    print(f"{FAIL} {msg}")
    if fatal:
        sys.exit(1)
def warn(msg): print(f"{WARN} {msg}")
def info(msg): print(f"{INFO} {msg}")

# ── locate portable root ──────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
PORTABLE_ROOT = SCRIPT_DIR.parent  # tools/ is one level inside the portable root

print(SEP)
print("  Pathology Dictation Assistant — Offline Readiness Check")
print(SEP)
print(f"Portable root : {PORTABLE_ROOT}")
print(f"Python        : {sys.executable}  ({sys.version.split()[0]})")
print(SEP)

errors = 0

# ── 1. Bundled Python ─────────────────────────────────────────────────────────
print("\n[1] Bundled Python runtime")
py_dir = PORTABLE_ROOT / "runtime" / "python"
if py_dir.exists():
    ok(f"runtime/python/ exists")
else:
    warn(f"runtime/python/ not found — running from a non-portable Python is OK "
         f"only on the build machine")

# ── 2. Required packages ──────────────────────────────────────────────────────
print("\n[2] Required Python packages")
REQUIRED = [
    ("faster_whisper",   "faster-whisper"),
    ("ctranslate2",      "ctranslate2"),
    ("numpy",            "numpy"),
    ("sounddevice",      "sounddevice"),
    ("soundfile",        "soundfile"),
    ("keyboard",         "keyboard"),
    ("pyperclip",        "pyperclip"),
    ("tkinter",          "tkinter (stdlib)"),
    ("loguru",           "loguru"),
    ("yaml",             "PyYAML"),
    ("docx",             "python-docx"),
    ("PIL",              "Pillow"),
]
for mod, label in REQUIRED:
    try:
        importlib.import_module(mod)
        ok(label)
    except ImportError as e:
        print(f"{FAIL} {label}  →  {e}")
        errors += 1

# ── 3. Model directories ──────────────────────────────────────────────────────
print("\n[3] Local Whisper models")
models_root = PORTABLE_ROOT / "models"
if not models_root.exists():
    fail(f"models/ directory not found at {models_root}", fatal=False)
    errors += 1
else:
    found_any = False
    for model_dir in sorted(models_root.iterdir()):
        if not model_dir.is_dir():
            continue
        required_files = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]
        missing = [f for f in required_files if not (model_dir / f).exists()]
        if not missing:
            size_mb = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) / 1e6
            ok(f"{model_dir.name}  ({size_mb:.0f} MB)")
            found_any = True
        else:
            warn(f"{model_dir.name}  — missing files: {missing}")
    if not found_any:
        fail("No complete model found in models/", fatal=False)
        errors += 1

# ── 4. Config file ─────────────────────────────────────────────────────────────
print("\n[4] Config files")
config_yaml = PORTABLE_ROOT / "config" / "config.yaml"
dict_file   = PORTABLE_ROOT / "config" / "pathology_replacements.json"
for p in [config_yaml, dict_file]:
    if p.exists():
        ok(p.relative_to(PORTABLE_ROOT))
    else:
        fail(f"Missing: {p.relative_to(PORTABLE_ROOT)}", fatal=False)
        errors += 1

if dict_file.exists():
    try:
        with open(dict_file) as f:
            d = json.load(f)
        ok(f"Dictionary loaded — {len(d)} entries")
    except Exception as e:
        fail(f"Dictionary parse error: {e}", fatal=False)
        errors += 1

# ── 5. FFmpeg ─────────────────────────────────────────────────────────────────
print("\n[5] FFmpeg")
ffmpeg_path = PORTABLE_ROOT / "ffmpeg" / "bin" / "ffmpeg.exe"
if ffmpeg_path.exists():
    ok(f"ffmpeg/bin/ffmpeg.exe  ({ffmpeg_path.stat().st_size / 1e6:.1f} MB)")
else:
    warn("ffmpeg/bin/ffmpeg.exe not found — audio file loading may be limited, "
         "but live microphone dictation will still work")

# ── 6. App source ──────────────────────────────────────────────────────────────
print("\n[6] Application source files")
app_dir = PORTABLE_ROOT / "app"
REQUIRED_APP = ["gui_app.py", "config.py", "transcriber.py",
                "audio_recorder.py", "terminology_corrector.py"]
for fname in REQUIRED_APP:
    p = app_dir / fname
    if p.exists():
        ok(fname)
    else:
        fail(f"Missing app/{fname}", fatal=False)
        errors += 1

# ── 7. Offline guard — no internet calls ─────────────────────────────────────
print("\n[7] Offline guard (HuggingFace)")
hf_offline = os.environ.get("HF_HUB_OFFLINE", "0")
tf_offline  = os.environ.get("TRANSFORMERS_OFFLINE", "0")
if hf_offline == "1":
    ok("HF_HUB_OFFLINE=1")
else:
    warn("HF_HUB_OFFLINE is not set — run via start_app.bat to enforce offline mode")
if tf_offline == "1":
    ok("TRANSFORMERS_OFFLINE=1")
else:
    warn("TRANSFORMERS_OFFLINE is not set")

# ── 8. CUDA / CPU detection ──────────────────────────────────────────────────
print("\n[8] Hardware acceleration")
try:
    import ctranslate2
    cuda_count = ctranslate2.get_cuda_device_count()
    if cuda_count > 0:
        ok(f"CUDA available — {cuda_count} device(s) detected  → will use float16")
    else:
        ok("No CUDA GPU — will use CPU int8  (expected for CPU-only computers)")
except Exception as e:
    warn(f"Could not query CUDA: {e}  — defaulting to CPU")

# ── 9. Quick CPU transcription smoke-test ────────────────────────────────────
print("\n[9] CPU transcription smoke-test")
try:
    import numpy as np
    import ctranslate2

    model_dir = next(
        (d for d in (PORTABLE_ROOT / "models").iterdir()
         if d.is_dir() and (d / "model.bin").exists()),
        None
    )
    if model_dir is None:
        warn("No complete model found — skipping smoke-test")
    else:
        info(f"Loading {model_dir.name} on CPU int8 ...")
        from faster_whisper import WhisperModel
        m = WhisperModel(str(model_dir), device="cpu", compute_type="int8",
                         local_files_only=True)
        # 1-second silent audio
        silent = np.zeros(16000, dtype=np.float32)
        segs, _ = m.transcribe(silent, language="en", vad_filter=True,
                               beam_size=1, best_of=1, word_timestamps=False)
        list(segs)  # force iteration
        ok(f"CPU int8 transcription works with {model_dir.name}")
        del m
except Exception as e:
    fail(f"CPU smoke-test failed: {e}", fatal=False)
    errors += 1

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print(SEP)
if errors == 0:
    print("  RESULT: ALL CHECKS PASSED — ready for offline use")
else:
    print(f"  RESULT: {errors} check(s) FAILED — review output above")
print(SEP)
sys.exit(0 if errors == 0 else 1)
