@echo off
:: =============================================================================
:: PathDictate v0.2.3 Portable — Launcher
:: =============================================================================
:: Double-click this file to start PathDictate.
:: No Python installation required.  No command line needed.
:: =============================================================================

setlocal EnableDelayedExpansion
title PathDictate v0.2.3

cd /d "%~dp0"

:: ── Sanity checks ─────────────────────────────────────────────────────────────

if not exist "runtime\pythonw.exe" (
    echo.
    echo  ============================================================
    echo  ERROR: runtime\pythonw.exe not found.
    echo  ============================================================
    echo.
    echo  This portable package appears to be incomplete or corrupted.
    echo.
    echo  Please re-download PathDictate_v0.2.3_Portable.zip from:
    echo    https://github.com/RNAi-C/Dictation_path/releases
    echo.
    echo  Then extract the ZIP and try again.
    echo  ============================================================
    pause
    exit /b 1
)

if not exist "gui_app.py" (
    echo.
    echo  ERROR: gui_app.py not found in this folder.
    echo  Please re-download the portable package.
    echo.
    pause
    exit /b 1
)

:: ── Portable mode environment variables ───────────────────────────────────────
::
::  PATHDICTATE_PORTABLE  — tells config.py to use relative paths
::  PATHDICTATE_ROOT      — absolute path to this folder (resolves relative paths)
::  HF_HUB_OFFLINE        — prevents any HuggingFace Hub network requests
::  TRANSFORMERS_OFFLINE  — prevents any Transformers library network requests

set PATHDICTATE_PORTABLE=1
set PATHDICTATE_ROOT=%~dp0
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set HF_HUB_DISABLE_TELEMETRY=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONIOENCODING=utf-8

:: ── Tcl/Tk paths (required for tkinter GUI) ───────────────────────────────────
set TCL_LIBRARY=%~dp0runtime\tcl\tcl8.6
set TK_LIBRARY=%~dp0runtime\tcl\tk8.6

:: ── Launch (pythonw = silent launch, no black console window) ─────────────────
start "" "%~dp0runtime\pythonw.exe" "%~dp0gui_app.py"

endlocal
