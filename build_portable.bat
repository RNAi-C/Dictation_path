@echo off
:: =============================================================================
:: PathDictate v0.2.1 — Portable Package Builder
:: =============================================================================
:: Double-click this file (or run from a command prompt) to build the portable
:: package.  PowerShell 5+ is required (included with Windows 10/11).
::
:: Options (pass as arguments):
::   -Model large-v3    Bundle large-v3 instead of small (default: small)
::   -SkipZip           Build folder only, skip ZIP creation
::   -Clean             Force a clean rebuild if folder already exists
::
:: Examples:
::   build_portable.bat
::   build_portable.bat -Model base
::   build_portable.bat -Model large-v3 -SkipZip
:: =============================================================================

setlocal
cd /d "%~dp0"

echo.
echo  PathDictate Portable Package Builder
echo  =====================================
echo.

:: Check that PowerShell is available
where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo  ERROR: PowerShell not found.
    echo  Windows 10/11 includes PowerShell by default.
    echo  Please install PowerShell from: https://aka.ms/powershell
    pause
    exit /b 1
)

:: Run the PowerShell build script, forwarding any arguments
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_portable.ps1" %*

if errorlevel 1 (
    echo.
    echo  Build FAILED. See errors above.
    pause
    exit /b 1
)

echo.
echo  Build finished successfully.
echo.
pause
endlocal
