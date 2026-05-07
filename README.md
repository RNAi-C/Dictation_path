# Pathology Dictation Assistant

A **local, offline, privacy-first** speech-to-text assistant for pathology report dictation.

---

## Purpose

Pathologists dictate findings, the app transcribes locally, applies terminology corrections, copies clean text to clipboard, and the pathologist pastes into LIS or Word.

**No cloud. No API calls. No patient data leaves the computer.**

---

## Privacy-First Design

| Principle | Implementation |
|-----------|---------------|
| Fully offline | `HF_HUB_OFFLINE=1` enforced at runtime |
| No cloud transcription | Whisper runs locally via `faster-whisper` |
| No patient data stored | Audio discarded after transcription |
| No logs with PHI | Log files excluded from repository |
| No model files in repo | Models downloaded or copied separately |

---

## Workflow

```
1. Press F9  →  start recording
2. Speak dictation
3. Press F9  →  stop recording
4. App transcribes locally (faster-whisper)
5. Applies pathology terminology corrections
6. Text copied to clipboard automatically
7. Paste into LIS / Word with Ctrl+V
```

---

## Hardware Support

### CPU-only (default)
- Works on any Windows 11 PC
- Uses `int8` quantization for speed
- Recommended model: `faster-whisper-base` or `faster-whisper-small`
- Typical speed: 5-20 seconds per 30-second dictation

### Optional GPU (NVIDIA CUDA)
- Auto-detected at startup
- Uses `float16` compute
- Recommended model: `faster-whisper-large-v3`
- Typical speed: 1-3 seconds per 30-second dictation

---

## Setup (Development)

### Requirements
- Windows 11 64-bit
- Python 3.11.x
- NVIDIA GPU optional (CUDA driver >= 520 if using GPU)

### Install

```powershell
git clone https://github.com/RNAi-C/Dictation_path.git
cd Dictation_path
python -m venv venv
venv\Scripts\activate
pip install -r requirements.lock.txt
```

### Run

```powershell
venv\Scripts\python.exe gui_app.py
# or double-click: Launch GUI.bat
```

The Whisper model downloads automatically on first run (~140 MB for base).

---

## Offline Portable Package

To deploy on a computer without internet or Python:

```powershell
# On the build machine (needs internet once for FFmpeg)
powershell -ExecutionPolicy Bypass -File package_portable_offline.ps1
```

Then copy `PathDictate_Portable\` to any Windows 11 PC and double-click `start_app.bat`.

See [`README_OFFLINE_PORTABLE.md`](README_OFFLINE_PORTABLE.md) for the full deployment guide.

---

## Synchronizing Between Computers

### First time on a new computer

```powershell
git clone https://github.com/RNAi-C/Dictation_path.git
cd Dictation_path
python -m venv venv
venv\Scripts\activate
pip install -r requirements.lock.txt
```

### Daily workflow (home <-> office)

```powershell
# START of session — always pull first
git pull

# ... make changes ...

# END of session — push before leaving
git add .
git commit -m "brief description of change"
git push
```

### What is NOT synced (see .gitignore)
- `venv/` — recreate with `pip install -r requirements.lock.txt`
- `models/` — downloaded automatically on first run
- `audio/` — never committed (privacy)
- `data/*.log` — never committed (privacy)
- `PathDictate_Portable/` — rebuild with the packaging script

---

## Project Structure

```
Dictation_path/
|-- gui_app.py                  <- main GUI application
|-- config.py                   <- configuration (env-var aware)
|-- transcriber.py              <- faster-whisper wrapper
|-- audio_recorder.py           <- microphone capture
|-- terminology_corrector.py    <- dictionary substitution
|-- clipboard_handler.py        <- clipboard integration
|-- hotkey_manager.py           <- F9 hotkey
|-- pathology_dictation_app.py  <- CLI entry point
|-- create_shortcut.py          <- desktop shortcut creator
|-- launcher.pyw                <- silent launcher for shortcuts
|
|-- config/
|   |-- config.yaml             <- portable runtime config
|   `-- pathology_replacements.json  <- terminology dictionary
|
|-- data/
|   `-- pathology_dictionary.json    <- terminology dictionary (JSON)
|
|-- tools/
|   |-- verify_offline_ready.py
|   |-- generate_checksums.py
|   `-- verify_checksums.py
|
|-- package_portable_offline.ps1  <- build portable package
|-- requirements.txt
|-- requirements.lock.txt
`-- README_OFFLINE_PORTABLE.md
```

---

## Safety Rule

> **This app transcribes and corrects dictated text only.**
> It never diagnoses, infers findings, or adds unstated pathology content.

When AI style-rewriting is added in a future phase, the required instruction will be:
> *"Rewrite into my reporting style using only dictated facts."*

---

## License

Private repository — not for public distribution.
