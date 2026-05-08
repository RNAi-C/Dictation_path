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

## AI Rewrite Selected Text (Ollama)

The **Rewrite Selected Text** feature lets you select any portion of your dictated text in the Corrected panel and ask a local Qwen model to rewrite it into cleaner formal pathology report style.

**Privacy guarantee:** All requests go to `localhost` only. No text leaves the computer.

### 1 — Install Ollama

Download and install from **https://ollama.ai** (Windows / macOS / Linux).

### 2 — Pull the Qwen model

Open a terminal and run:

```powershell
ollama pull qwen2.5:14b
```

> This downloads ~8 GB. You only need to do this once.
> Smaller/faster alternatives: `qwen2.5:7b` (~4 GB), `qwen2.5:3b` (~2 GB)

### 3 — Start Ollama

```powershell
ollama serve
```

Leave this running in the background while using the app.

### 4 — Configure the model (optional)

Edit `config/config.yaml` to change the model name or endpoint:

```yaml
llm:
  enabled: true
  model: "qwen2.5:14b"          # change to any pulled model
  endpoint: "http://localhost:11434/api/generate"
  temperature: 0.1
  timeout_seconds: 60
```

### 5 — Use Rewrite Selected Text

1. Dictate and transcribe as normal
2. Switch to the **✏ Corrected** tab
3. **Select** the text you want to rewrite
4. Click **✏ Rewrite Selected Text** (or press `Ctrl+Shift+R`)
5. Wait for the preview dialog to appear (~5–30 s depending on model)
6. Review the **Before / After** comparison
7. Optionally edit the rewritten text in the right pane
8. Click **✓ Accept Rewrite** to replace the selection, or **✗ Reject** to keep the original

### Undo / Redo

The Corrected panel supports full undo/redo:

| Action | Keyboard | Button |
|--------|----------|--------|
| Undo   | `Ctrl+Z` | ↩ Undo |
| Redo   | `Ctrl+Y` | ↪ Redo |

### Safety rule

The AI model is instructed with a strict system prompt:

> *Rewrite the selected text into clearer formal pathology reporting style using only the facts explicitly present in the selected text. Do not add new findings. Do not infer diagnosis, tumor grade, margin status, stage, or biomarker status. Do not convert uncertain language into definite statements. Return only the rewritten text.*

The model **never** has access to the full patient record — only the text you explicitly select.

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
|-- rewriter.py                 <- GGUF-based whole-text rewriter (llama-cpp)
|-- ollama_client.py            <- local Ollama HTTP client (stdlib only)
|-- rewrite_service.py          <- pathology-safe selection rewrite via Ollama
|-- pathology_dictation_app.py  <- CLI entry point
|-- create_shortcut.py          <- desktop shortcut creator
|-- launcher.pyw                <- silent launcher for shortcuts
|
|-- config/
|   |-- config.yaml             <- runtime config (model, LLM, privacy)
|   `-- pathology_replacements.json  <- terminology dictionary
|
|-- data/
|   `-- pathology_dictionary.json    <- terminology dictionary (JSON)
|
|-- models/
|   `-- rewrite/                <- place .gguf files here for GGUF rewriter
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

## Troubleshooting — Ollama & AI Rewrite

### Ollama auto-start

When the app launches, it automatically:
1. Checks if Ollama is running at `http://localhost:11434`
2. If not running, attempts to start it silently with `ollama serve`
3. Waits up to 30 seconds for Ollama to become ready
4. Checks whether the configured model is installed

The footer bar shows the Ollama status at all times:

| Footer message | Meaning |
|----------------|---------|
| `Ollama: checking…` | Startup check in progress |
| `Ollama: qwen2.5:14b ✓` | Ready — rewrite is enabled |
| `Ollama: 'qwen2.5:14b' not installed` | Ollama is running but model needs pulling |
| `Ollama unavailable — rewrite disabled` | Could not start; dictation still works |

**Dictation always works regardless of Ollama status.**
The ✏ Rewrite Selected Text button is simply disabled when Ollama is unavailable.

---

### How to install Ollama

Download and install from **https://ollama.ai** (Windows / macOS / Linux installer).

After installation, Ollama is available as the `ollama` command in your terminal.

---

### How to manually start Ollama

If auto-start fails, open a terminal and run:

```powershell
ollama serve
```

Leave this running in the background.  The app will detect it on next startup
or when you click ✏ Rewrite Selected Text.

---

### How to install the Qwen model

```powershell
ollama pull qwen2.5:14b      # ~8 GB — default model
```

You only need to do this once.  Alternative sizes:

```powershell
ollama pull qwen2.5:3b       # ~2 GB — fastest, less accurate
ollama pull qwen2.5:7b       # ~4 GB — good balance
ollama pull qwen2.5:32b      # ~20 GB — best, requires GPU
```

To use a different model, edit `config/config.yaml`:

```yaml
llm:
  model: "qwen2.5:7b"        # change to any pulled model
```

> **The app never pulls models automatically** — it must remain offline-safe.
> The model must be pulled manually before the rewrite feature will work.

---

### What happens if Ollama is not installed

The app starts normally.  The ✏ Rewrite Selected Text button stays disabled.
The footer shows: `Ollama unavailable — rewrite disabled (dictation works normally)`

If you later install Ollama, restart the app and it will be detected automatically.

---

### What happens if the Qwen model is not pulled

The app starts normally.  A one-time warning dialog appears:

> *"Ollama is running, but 'qwen2.5:14b' is not installed.
> Pull it with: ollama pull qwen2.5:14b"*

The ✏ Rewrite Selected Text button stays disabled until the model is installed.

---

### To disable auto-start entirely

Set `auto_start_ollama: false` in `config/config.yaml`:

```yaml
llm:
  auto_start_ollama: false    # never try to start Ollama automatically
```

---

## Safety Rule

> **This app transcribes and corrects dictated text only.**
> It never diagnoses, infers findings, or adds unstated pathology content.

The AI rewrite feature enforces this rule at the prompt level:
> *"Rewrite the selected text into clearer formal pathology reporting style using only the facts explicitly present in the selected text. Do not add new findings. Do not infer diagnosis. Return only the rewritten text."*

---

## License

Private repository — not for public distribution.
