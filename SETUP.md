# Pathology Dictation Assistant - Phase 1 Setup Guide

## Overview

A local, offline speech-to-text application for pathology dictation with terminology correction.

- **No cloud services** - runs entirely on your Windows 11 workstation
- **GPU-accelerated** - uses NVIDIA CUDA for fast transcription
- **Privacy-first** - patient data never leaves your machine
- **Simple workflow** - Press F9, dictate, get corrected text in clipboard

## System Requirements

- **OS**: Windows 11
- **Python**: 3.10 or higher
- **GPU**: NVIDIA GPU with CUDA support (RTX 4090 or RTX 5090)
- **CUDA**: CUDA Toolkit 11.8+ (verify with `nvidia-smi`)
- **cuDNN**: 8.x (typically installed with CUDA)
- **RAM**: 16GB minimum (32GB recommended)
- **Disk**: 10GB for models cache

## Pre-Installation Checklist

### 1. Verify NVIDIA CUDA Setup

```powershell
# Check GPU
nvidia-smi

# Output should show your GPU and CUDA version
# Example: NVIDIA-SMI 545.84  Driver Version: 545.84  CUDA Version: 12.4
```

If `nvidia-smi` command not found:
1. Download CUDA Toolkit from: https://developer.nvidia.com/cuda-downloads
2. Download cuDNN from: https://developer.nvidia.com/cudnn (requires account)
3. Follow installation instructions for Windows

### 2. Verify Python Installation

```powershell
python --version
# Should be 3.10 or higher

pip --version
# Verify pip is working
```

## Installation Steps

### Step 1: Create Project Directory

```powershell
# Create a dedicated directory for the application
mkdir "C:\PathologyDictation"
cd "C:\PathologyDictation"
```

### Step 2: Create Virtual Environment

```powershell
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1

# If you get an execution policy error, run:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Step 3: Copy Project Files

Copy all the Python files into the project directory:
- `pathology_dictation_app.py`
- `config.py`
- `audio_recorder.py`
- `transcriber.py`
- `terminology_corrector.py`
- `clipboard_handler.py`
- `hotkey_manager.py`
- `requirements.txt`

### Step 4: Install Dependencies

```powershell
# Make sure virtual environment is activated
.\venv\Scripts\Activate.ps1

# Upgrade pip, setuptools, wheel
pip install --upgrade pip setuptools wheel

# Install requirements
pip install -r requirements.txt

# Verify installations
pip list
```

### Step 5: Download Whisper Model (First Run Only)

The first time you run the application, it will automatically download the large-v3 Whisper model (~3GB). This may take several minutes depending on internet speed.

```powershell
# Optional: Pre-download model to avoid delay on first run
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cuda')"
```

## Configuration

### Default Configuration

The application creates these directories automatically:
```
C:\PathologyDictation\
├── config/          # Configuration files
├── models/          # Cached Whisper models
├── audio/           # Recorded audio files
├── data/            # Dictionary and logs
└── venv/            # Virtual environment
```

### Customize Settings

Edit `config.py` to change:

**Audio Settings** (line ~15):
```python
sample_rate: int = 16000  # Whisper requires 16kHz
channels: int = 1         # Mono
device_index: Optional[int] = None  # Default mic (None = system default)
```

**Whisper Model** (line ~30):
```python
model_size: str = "large-v3"  # large-v3 (best), medium, base, tiny
device: str = "cuda"  # cuda or cpu
compute_type: str = "float16"  # float16 (fast), float32 (accurate), int8
```

**Hotkey** (line ~47):
```python
toggle_record: str = "f9"  # Change recording hotkey here
```

### Terminology Dictionary

The application creates `data/pathology_dictionary.json` with default pathology terms. Edit this file to add custom terms.

## First Run

### 1. Test Microphone

```powershell
# Activate environment
.\venv\Scripts\Activate.ps1

# Run microphone test
python pathology_dictation_app.py
```

### 2. First Recording

1. **Press F9** - recording starts
2. **Speak clearly** - dictate your pathology findings
3. **Press F9 again** - stops recording and starts transcription
4. **Wait** - transcription takes 5-30 seconds
5. **Result** - Text automatically copied to clipboard

## Troubleshooting

### "nvidia-smi not found"
- CUDA not installed or not in PATH
- **Fix**: Install CUDA Toolkit, restart PowerShell

### "No module named 'faster_whisper'"
- Dependencies not installed
- **Fix**: Run `pip install -r requirements.txt` with venv activated

### "Microphone test failed"
- **Fix**: Check Windows Sound settings, modify `device_index` in config.py

### "Transcription very slow"
- **Fix**: Verify CUDA is being used: `nvidia-smi`

### "Out of memory"
- **Fix**: Use smaller model: `model_size: "medium"` in config.py

## Safety Considerations

✅ **What this system does:**
- Transcribes speech to text locally
- Corrects terminology
- Copies to clipboard

❌ **What this system NEVER does:**
- Uploads data to cloud
- Diagnoses cases autonomously
- Invents pathology findings

---

**Remember**: Always review transcriptions before clinical use.
