"""
packaging/portable_checks.py
─────────────────────────────
Developer utility: verifies that a built portable package is complete and
likely to work on a fresh Windows machine.

Run AFTER build_portable.ps1:
    python packaging\\portable_checks.py PathDictate_v0.2.1_Portable

Exit codes:
    0  — all critical checks passed
    1  — one or more critical checks failed
    2  — warnings only (non-critical issues found)
"""

import sys
import os
import struct
from pathlib import Path


# ── ANSI colours (Windows 10+ supports ANSI by default) ─────────────────────
GRN  = "\033[92m"
YEL  = "\033[93m"
RED  = "\033[91m"
CYN  = "\033[96m"
RST  = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str):   print(f"  {GRN}✓{RST}  {msg}")
def warn(msg: str): print(f"  {YEL}⚠{RST}  {msg}")
def fail(msg: str): print(f"  {RED}✗{RST}  {msg}")
def info(msg: str): print(f"  {CYN}·{RST}  {msg}")


# ── Check helpers ────────────────────────────────────────────────────────────

def check_file(base: Path, rel: str, critical: bool = True) -> bool:
    p = base / rel
    if p.exists() and p.stat().st_size > 0:
        ok(rel)
        return True
    msg = f"MISSING: {rel}"
    fail(msg) if critical else warn(msg)
    return not critical          # non-critical → still "pass"


def check_dir(base: Path, rel: str, min_files: int = 1) -> bool:
    p = base / rel
    if not p.is_dir():
        fail(f"MISSING directory: {rel}")
        return False
    count = sum(1 for _ in p.rglob("*") if _.is_file())
    if count < min_files:
        warn(f"{rel}  has only {count} file(s) (expected ≥ {min_files})")
        return False
    ok(f"{rel}  ({count} files)")
    return True


def check_model(models_dir: Path) -> bool:
    """Check that at least one faster-whisper model folder with model.bin exists."""
    for d in models_dir.iterdir():
        if not d.is_dir():
            continue
        # vocabulary file can be .json (older models) or .txt (newer models)
        has_vocab = (d / "vocabulary.json").exists() or (d / "vocabulary.txt").exists()
        required = ["model.bin", "config.json", "tokenizer.json"]
        missing  = [f for f in required if not (d / f).exists()]
        if not has_vocab:
            missing.append("vocabulary.json or vocabulary.txt")
        if not missing:
            ok(f"Model: {d.name}  (all required files present)")
            return True
        else:
            warn(f"Model folder {d.name} is incomplete — missing: {', '.join(missing)}")
    fail("No complete faster-whisper model found in models\\")
    return False


def check_python_exe(runtime: Path) -> bool:
    exe = runtime / "pythonw.exe"
    if not exe.exists():
        fail("runtime\\pythonw.exe not found")
        return False
    # Read PE header to confirm 64-bit
    try:
        with open(exe, "rb") as f:
            f.seek(0x3C)
            pe_offset = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_offset + 4)
            machine = struct.unpack("<H", f.read(2))[0]
        arch = {0x8664: "x64 (AMD64)", 0x014c: "x86 (32-bit)", 0xAA64: "ARM64"}.get(machine, f"unknown (0x{machine:04x})")
        ok(f"runtime\\pythonw.exe  — {arch}")
        return machine == 0x8664   # only x64 supported
    except Exception as e:
        warn(f"Could not read PE header: {e}")
        return True   # assume OK


def check_site_packages(sp: Path) -> bool:
    critical_packages = [
        "ctranslate2",
        "faster_whisper",
        "numpy",
        "sounddevice.py",
        "soundfile.py",
        "_sounddevice_data",
        "_soundfile_data",
        "keyboard",
        "loguru",
        "tokenizers",
        "huggingface_hub",
        "av",
    ]
    all_ok = True
    for pkg in critical_packages:
        p = sp / pkg
        if p.exists():
            ok(f"package: {pkg}")
        else:
            fail(f"package MISSING: {pkg}")
            all_ok = False
    return all_ok


def check_tkinter(runtime: Path) -> bool:
    checks = [
        (runtime / "Lib" / "tkinter" / "__init__.py", "Lib\\tkinter\\__init__.py"),
        (runtime / "DLLs" / "_tkinter.pyd",           "DLLs\\_tkinter.pyd"),
        (runtime / "DLLs" / "tcl86t.dll",             "DLLs\\tcl86t.dll"),
        (runtime / "DLLs" / "tk86t.dll",              "DLLs\\tk86t.dll"),
        (runtime / "tcl" / "tcl8.6",                  "tcl\\tcl8.6"),
    ]
    all_ok = True
    for path, label in checks:
        if path.exists():
            ok(f"tkinter: {label}")
        else:
            fail(f"tkinter: MISSING {label}")
            all_ok = False
    return all_ok


def check_config(base: Path) -> bool:
    cfg = base / "config" / "config.yaml"
    if not cfg.exists():
        fail("config\\config.yaml not found")
        return False
    content = cfg.read_text(encoding="utf-8")
    if "model_path" not in content:
        warn("config.yaml: model_path not set")
    if "offline_only: true" in content:
        ok("config.yaml: offline_only confirmed")
    else:
        warn("config.yaml: offline_only not set to true")
    ok("config\\config.yaml found")
    return True


def estimate_size(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 ** 3)   # GB


# ── Main ─────────────────────────────────────────────────────────────────────

def run_checks(portable_dir: Path) -> int:
    """
    Returns:
        0  — all critical checks passed, no warnings
        1  — one or more CRITICAL failures
        2  — only warnings
    """
    if not portable_dir.is_dir():
        print(f"{RED}ERROR: {portable_dir} is not a directory.{RST}")
        return 1

    print(f"\n{BOLD}{CYN}PathDictate Portable — Build Verification{RST}")
    print(f"  Checking: {portable_dir}\n")

    failures = 0
    warnings = 0

    runtime = portable_dir / "runtime"
    sp      = runtime / "Lib" / "site-packages"
    models  = portable_dir / "models"

    # ── Executable ────────────────────────────────────────────────────────────
    print(f"{BOLD}[ Python runtime ]{RST}")
    if not check_python_exe(runtime):
        failures += 1
    if not (runtime / "python313._pth").exists():
        fail("runtime\\python313._pth missing")
        failures += 1
    else:
        pth = (runtime / "python313._pth").read_text()
        if "import site" in pth:
            ok("python313._pth: import site enabled")
        else:
            fail("python313._pth: 'import site' line missing — site-packages won't load")
            failures += 1

    # ── Tkinter ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ Tkinter support ]{RST}")
    if not check_tkinter(runtime):
        failures += 1

    # ── Site-packages ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ Critical Python packages ]{RST}")
    if not check_site_packages(sp):
        failures += 1

    # ── App source ────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ App source files ]{RST}")
    app_files = [
        "gui_app.py", "config.py", "audio_recorder.py", "transcriber.py",
        "terminology_corrector.py", "clipboard_handler.py",
        "rewrite_service.py", "ollama_client.py", "rewriter.py",
    ]
    for f in app_files:
        if not check_file(portable_dir, f, critical=True):
            failures += 1

    # ── Launcher ──────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ Launcher ]{RST}")
    if not check_file(portable_dir, "START_PATHDICTATE.bat"):
        failures += 1
    check_file(portable_dir, "VERSION.txt", critical=False)
    check_file(portable_dir, "README_QUICK_START.txt", critical=False)

    # ── Config ────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ Configuration ]{RST}")
    if not check_config(portable_dir):
        failures += 1
    check_file(portable_dir, "config\\voice_commands.json", critical=False)
    check_file(portable_dir, "config\\pathology_replacements.json", critical=False)
    check_file(portable_dir, "data\\pathology_dictionary.json", critical=False)

    # ── Model ─────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ Whisper model ]{RST}")
    if models.is_dir():
        if not check_model(models):
            warnings += 1
    else:
        fail("models\\ directory not found")
        failures += 1

    # ── Size summary ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}[ Size summary ]{RST}")
    total_gb = estimate_size(portable_dir)
    info(f"Total portable folder size: {total_gb:.2f} GB")
    if total_gb > 3.0:
        warn(f"Package is large ({total_gb:.1f} GB) — consider using the 'small' model for distribution")
    elif total_gb < 0.3:
        warn(f"Package seems too small ({total_gb:.2f} GB) — model or runtime may be missing")
    else:
        ok(f"Size looks reasonable ({total_gb:.2f} GB)")

    # ── Result ────────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    if failures:
        print(f"{RED}{BOLD}  FAILED — {failures} critical check(s) failed.{RST}")
        print(f"  The portable package is likely to NOT work on a fresh machine.")
        return 1
    elif warnings:
        print(f"{YEL}{BOLD}  PASSED WITH WARNINGS — {warnings} non-critical issue(s).{RST}")
        print(f"  The package should work but review the warnings above.")
        return 2
    else:
        print(f"{GRN}{BOLD}  ALL CHECKS PASSED — portable package looks good!{RST}")
        print(f"  Copy {portable_dir.name} to another Windows 11 machine and test.")
        return 0


if __name__ == "__main__":
    # Enable ANSI on Windows
    os.system("")

    if len(sys.argv) < 2:
        # Default: look for PathDictate_v*_Portable next to this script
        script_dir = Path(__file__).parent.parent   # project root
        candidates = sorted(script_dir.glob("PathDictate_v*_Portable"), reverse=True)
        if not candidates:
            print("Usage: python packaging\\portable_checks.py <portable_folder>")
            print("       No PathDictate_v*_Portable folder found in project root.")
            sys.exit(1)
        target = candidates[0]
        print(f"Auto-detected portable folder: {target}")
    else:
        target = Path(sys.argv[1])

    sys.exit(run_checks(target))
