@echo off
REM Pathology Dictation Assistant - Windows Setup Script
REM Run this script from PowerShell as Administrator or run CMD as Administrator

setlocal enabledelayedexpansion

echo.
echo ============================================================================
echo  PATHOLOGY DICTATION ASSISTANT - SETUP WIZARD
echo ============================================================================
echo.

REM Check Python installation
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ from python.org
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo Found: %PYTHON_VERSION%
echo.

REM Check CUDA installation
echo Checking CUDA installation...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo WARNING: nvidia-smi not found. CUDA may not be installed.
    echo Please install CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
    echo.
    set CUDA_AVAILABLE=0
) else (
    echo NVIDIA GPU detected.
    nvidia-smi
    set CUDA_AVAILABLE=1
)
echo.

REM Create virtual environment
echo Creating Python virtual environment...
if not exist "venv" (
    python -m venv venv
    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo.

REM Upgrade pip
echo Upgrading pip, setuptools, wheel...
python -m pip install --upgrade pip setuptools wheel >nul 2>&1
if errorlevel 1 (
    echo WARNING: Could not upgrade pip. Continuing anyway...
)
echo.

REM Install requirements
echo Installing dependencies from requirements.txt...
if not exist "requirements.txt" (
    echo ERROR: requirements.txt not found in current directory
    echo Please ensure all project files are in the same directory
    pause
    exit /b 1
)

pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

REM Verify installations
echo Verifying installations...
python -c "import faster_whisper; print('  ✓ faster-whisper')" 2>nul || echo "  ✗ faster-whisper"
python -c "import sounddevice; print('  ✓ sounddevice')" 2>nul || echo "  ✗ sounddevice"
python -c "import soundfile; print('  ✓ soundfile')" 2>nul || echo "  ✗ soundfile"
python -c "import keyboard; print('  ✓ keyboard')" 2>nul || echo "  ✗ keyboard"
python -c "import pyperclip; print('  ✓ pyperclip')" 2>nul || echo "  ✗ pyperclip"
python -c "import loguru; print('  ✓ loguru')" 2>nul || echo "  ✗ loguru"
echo.

REM Create directories
echo Creating application directories...
if not exist "config" mkdir config
if not exist "data" mkdir data
if not exist "models" mkdir models
if not exist "audio" mkdir audio
echo.

REM Pre-download model (optional)
if "%CUDA_AVAILABLE%"=="1" (
    echo.
    echo Would you like to download the Whisper model now? (1-3GB)
    echo Press Y for yes, N to skip (can download on first run)
    set /p MODEL_CHOICE="Download model now? [y/N]: "
    if /i "!MODEL_CHOICE!"=="y" (
        echo Downloading Whisper large-v3 model (this may take several minutes)...
        python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cuda')"
        if errorlevel 1 (
            echo WARNING: Model download failed. Will try on first run.
        ) else (
            echo Model downloaded successfully.
        )
    )
) else (
    echo NOTE: GPU not detected. Model will use CPU (slower).
)
echo.

REM Create run script
echo Creating run script...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo call venv\Scripts\activate.bat
    echo python pathology_dictation_app.py
    echo pause
) > run.bat

echo.
echo ============================================================================
echo  SETUP COMPLETE!
echo ============================================================================
echo.
echo Project files are ready. Your directories:
echo.
echo   config/     - Configuration files
echo   data/       - Dictionary and logs
echo   models/     - Whisper models cache
echo   audio/      - Temporary recordings
echo.
echo Next steps:
echo.
echo   1. Edit data/pathology_dictionary.json to add custom terms (optional)
echo   2. Run the application:
echo.
echo      Option A: Double-click run.bat
echo      Option B: From PowerShell:
echo                 .\venv\Scripts\Activate.ps1
echo                 python pathology_dictation_app.py
echo.
echo   3. Press F9 to start recording when ready
echo.
echo For detailed setup instructions, see SETUP.md
echo.
echo ============================================================================
echo.

pause
