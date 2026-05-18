# PathDictate v0.2.3 — Tester Guide

## Test Environment Setup

1. Clone repo and create venv:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Place a faster-whisper model in `models/faster-whisper-small/`
   (or use `Settings → Browse Model Folder` to select any model)

3. Install Ollama from https://ollama.ai (optional — for rewrite tests)

4. Pull test model:
   ```
   ollama pull qwen2.5:7b
   ```

---

## Test Workflows

### A — Dictation Only (no Ollama required)

- [ ] App starts without errors
- [ ] Model loads (status bar shows model path)
- [ ] Microphone detected (VU meter responds)
- [ ] F9 starts recording (button turns red)
- [ ] F9 stops recording and transcribes
- [ ] Text inserts at cursor position
- [ ] Terminology corrections applied

### B — Model Path

- [ ] Delete model folder → app shows "Model not found" warning, dictation disabled
- [ ] Settings → Browse Model Folder → select valid folder → model reloads
- [ ] Settings → Reload Model reloads without restart
- [ ] Relative path `./models/faster-whisper-small` works in portable mode
- [ ] Absolute path selected by user is saved and persists on restart

### C — Document Workflow

- [ ] Ctrl+N creates new draft (prompts to save if dirty)
- [ ] Ctrl+O opens .txt file
- [ ] Ctrl+S saves to current file (or Save As if no file)
- [ ] Ctrl+Shift+S always opens Save As dialog
- [ ] Autosave creates file in `autosave/` folder every ~60 s
- [ ] Unsaved-change warning appears when closing with dirty editor
- [ ] Privacy warning shown on first save

### D — Editing

- [ ] Manual typing works in Corrected panel
- [ ] Dictation inserts at cursor position
- [ ] Ctrl+Z undoes last edit
- [ ] Ctrl+Y redoes undone edit
- [ ] Document marked dirty after any edit

### E — Rewrite Functions

- [ ] Ollama missing → rewrite buttons disabled, status shows message
- [ ] Model missing → clear warning dialog
- [ ] Select text → "Rewrite Selected" → preview appears → Accept replaces
- [ ] Select text → "Rewrite Selected" → Reject → original unchanged
- [ ] "Rewrite to Pathology English" with no selection → asks about full text
- [ ] "Rewrite to Pathology English" with selection → processes selection
- [ ] Preview shows original and rewritten side-by-side
- [ ] Accept inserts rewritten text
- [ ] Reject leaves original unchanged

### F — AI Model Manager

- [ ] Tools → AI Model Manager opens dialog
- [ ] Ollama not installed → shows "Not installed"
- [ ] Ollama running → shows "Running ✓"
- [ ] Model installed → shows "Installed ✓"
- [ ] "Get Ollama" opens ollama.ai in browser
- [ ] "Start Ollama" attempts to launch ollama serve
- [ ] "Download Model" requires confirmation before starting
- [ ] Download only starts after user confirms
- [ ] "Test Rewrite" runs a sample rewrite and shows result

### G — Thai-English Dictation

- [ ] Dictate in Thai with English medical terms
  Example: "พบ invasive carcinoma NST grade two ไม่มี lymphovascular invasion"
- [ ] Transcription captures Thai structure and English terms
- [ ] Terminology correction normalizes English terms (HER2, Ki-67, etc.)
- [ ] "Rewrite to Pathology English" converts to professional English prose

### H — Self-Correction Cleanup

- [ ] "14.5 oh no 15.2" → "15.2"
- [ ] "brown no no yellow" → "yellow"
- [ ] "grade one correction grade two" → "grade two"
- [ ] Ambiguous phrase → marked [REVIEW]
- [ ] Filler words (um, uh, er) removed

### I — Portable Package

- [ ] `build_portable.ps1` completes without errors
- [ ] Portable folder contains all required files
- [ ] `packaging\portable_checks.py` passes all checks
- [ ] Extract ZIP to clean folder on different machine
- [ ] `START_PATHDICTATE.bat` launches app
- [ ] No hardcoded developer paths
- [ ] App works offline (dictation only)

---

## Known Limitations (v0.2.3)

- .txt only (no .docx export yet)
- No gross template mode
- No CAP protocol mode
- No LIS integration
- No RAG
- AI rewrite requires local Ollama + Qwen model
- Qwen download requires internet (user-triggered only)
- Whisper model must exist locally (never downloads automatically)
- Autosave may contain sensitive text — store in approved secure folder
