# Pathology Dictation Assistant — Offline Portable Edition

**Version:** 1.0.0  
**Target OS:** Windows 11 (64-bit)  
**Internet required:** None — fully offline after copying  
**GPU required:** No — CPU-only operation is fully supported

---

## Quick Start (Target Computer)

1. Copy the entire `PathDictate_Portable` folder to the target computer.  
   USB drive, network share, or any transfer method works.
2. Double-click **`start_app.bat`**.  
   The app window opens in 10–60 seconds (first launch loads the model).
3. Press **F9** to start recording. Speak your dictation. Press **F9** again to stop.  
   Transcribed text appears in the window and is copied to the clipboard.
4. Paste (**Ctrl+V**) into your LIS, Word document, or any text field.

> **Tip:** To verify everything is working before first use, double-click  
> **`verify_install.bat`** instead. It runs a quick self-test and prints a report.

---

## Folder Structure

```
PathDictate_Portable/
├── start_app.bat              ← double-click to launch
├── start_app_debug.bat        ← same but shows console output (troubleshooting)
├── verify_install.bat         ← self-test / offline readiness check
├── README_OFFLINE_PORTABLE.md ← this file
│
├── app/                       ← Python source files (do not edit)
├── runtime/
│   └── python/                ← bundled Python 3.11.4 (no installation needed)
│
├── models/
│   ├── faster-whisper-base/   ← 140 MB, fastest CPU option (default)
│   ├── faster-whisper-small/  ← 244 MB, better accuracy (optional)
│   └── faster-whisper-large-v3/  ← 1.5 GB, best quality, GPU recommended (optional)
│
├── ffmpeg/
│   └── bin/ffmpeg.exe         ← audio processing utility
│
├── config/
│   ├── config.yaml            ← main settings (editable)
│   └── pathology_replacements.json  ← terminology dictionary (editable)
│
├── data/                      ← logs and session data
├── tools/                     ← verification and checksum utilities
└── checksums/
    └── SHA256SUMS.txt         ← integrity reference
```

---

## Choosing a Model

Edit `config/config.yaml` and change `model_path`:

| Model | Size | CPU Speed | Accuracy | Recommended For |
|-------|------|-----------|----------|-----------------|
| `faster-whisper-base` | ~140 MB | ★★★★★ | ★★★ | Default; good balance on CPU |
| `faster-whisper-small` | ~244 MB | ★★★★ | ★★★★ | Better accuracy, still CPU-friendly |
| `faster-whisper-medium` | ~769 MB | ★★ | ★★★★★ | High accuracy; slow on CPU |
| `faster-whisper-large-v3` | ~1.5 GB | ★ | ★★★★★ | Best quality; GPU strongly recommended |

Example — switch to small:
```yaml
model_path: ./models/faster-whisper-small
```

The model folder must exist inside `models/` before changing this setting.  
See [How to Add a Model Later](#how-to-add-a-model-later) below.

---

## CPU-Only Instructions

The app defaults to **CPU + int8 quantization** when no NVIDIA GPU is detected.

- No CUDA, no drivers, no GPU required.
- Transcription speed depends on your CPU. Typical times:
  - Base model: 5–15 seconds for a 30-second dictation.
  - Small model: 10–25 seconds for a 30-second dictation.
- If transcription feels slow, use the **base** model or upgrade to a GPU-equipped PC.
- The app remains fully functional — only speed differs.

---

## Optional GPU (NVIDIA CUDA) Instructions

If the target computer has an NVIDIA RTX GPU with CUDA:

1. Set `device: auto` in `config/config.yaml` (default).
2. The app automatically detects the GPU and switches to float16.
3. Transcription will be 5–20× faster than CPU.

No additional installation is needed — CUDA libraries are bundled.

> **Note:** CUDA requires an NVIDIA GPU with CUDA Compute Capability ≥ 5.0  
> and a recent NVIDIA driver (≥ 520). The driver must already be installed on  
> the target machine; it is the only external dependency.

---

## Microphone Troubleshooting

**No audio / recording button doesn't respond:**
- Open Windows **Sound Settings** → Input.  
  Confirm a microphone is listed and set as default.
- Make sure the app has microphone permission:  
  **Settings → Privacy → Microphone → Allow apps to access microphone**.
- If the wrong microphone is selected, edit `config/config.yaml`:  
  ```yaml
  # device_index: null   # null = system default
  device_index: 1        # change to the index of your microphone
  ```
  To find the correct index, run:
  ```
  runtime\python\python.exe -c "import sounddevice; print(sounddevice.query_devices())"
  ```

**Recording works but transcription produces garbled text:**
- Speak clearly and at a normal pace.
- Use a headset or directional microphone for best results.
- Ensure the microphone is recording at 16 kHz or higher.

---

## FFmpeg Troubleshooting

FFmpeg is included for audio processing. If `ffmpeg.exe` is missing:
- Live microphone dictation still works.
- Loading audio files (`.wav`, `.mp3`) may not work.

To add manually: place `ffmpeg.exe` in `ffmpeg\bin\` inside the portable folder.

---

## Editing the Terminology Dictionary

Open `config/pathology_replacements.json` in any text editor (Notepad works).

Format:
```json
{
  "what you say": "what you want it to become",
  "hurt two": "HER2",
  "doctor carcinoma": "ductal carcinoma"
}
```

You can also use the **Terminology Editor** inside the app (Edit menu or toolbar button).  
Changes are saved automatically.

---

## No-Internet Validation Checklist

Before deploying to an air-gapped computer, verify:

- [ ] `start_app.bat` launches the app without internet.
- [ ] `verify_install.bat` reports all checks passed.
- [ ] Model loads from `models/` without network activity.
- [ ] Transcription completes without network activity.
- [ ] No Windows Firewall prompts appear during use.
- [ ] Task Manager shows no network activity from python.exe during dictation.

---

## How to Add a Model Later

1. On a machine **with internet**, run:
   ```powershell
   .\venv\Scripts\python.exe -c "
   from faster_whisper import WhisperModel
   m = WhisperModel('small', device='cpu', compute_type='int8',
                    download_root='models')
   del m
   print('Done')
   "
   ```
2. Run `package_portable_offline.ps1` again (it will re-flatten the new model).  
   Or manually copy `models--Systran--faster-whisper-small\snapshots\<hash>\*`  
   into `PathDictate_Portable\models\faster-whisper-small\` (four files: `model.bin`,  
   `config.json`, `tokenizer.json`, `vocabulary.txt`).
3. Copy only the new `models/faster-whisper-small/` folder to the target computer.
4. Update `config/config.yaml` on the target: `model_path: ./models/faster-whisper-small`.

---

## Privacy Statement

- All audio is processed **locally on this computer**.
- No audio, text, or metadata is sent to any server or cloud service.
- No internet connection is used during operation.
- `HF_HUB_OFFLINE=1` is set by `start_app.bat` to prevent any accidental  
  network calls from HuggingFace Hub libraries.
- Transcriptions are stored **only** if you explicitly save them (Save button).

---

## Known Limitations

| Limitation | Notes |
|------------|-------|
| Windows 11 64-bit only | 32-bit Windows is not supported |
| English only by default | Change `language:` in `config.yaml` for other languages |
| CPU transcription is slower than GPU | See model size guidance above |
| Microphone access required | System permission must be granted |
| No automatic updates | Copy a new build folder to update |
| large-v3 not included by default | Add with `-IncludeLargeV3` flag during build |
| NVIDIA driver not bundled | Only the CUDA compute libraries are bundled |

---

## Build Instructions (Build Machine)

Run once on the machine that has the project set up:

```powershell
# Default: includes faster-whisper-base only
.\package_portable_offline.ps1

# Include large-v3 model (~1.5 GB extra)
.\package_portable_offline.ps1 -IncludeLargeV3

# Custom output location
.\package_portable_offline.ps1 -OutputDir "D:\Deploy\PathDictate_Portable"
```

Requirements on the build machine:
- Python 3.11.4 with the project venv set up (`venv/`)
- faster-whisper-base model downloaded (happens automatically during packaging)
- Internet access (for FFmpeg download — only needed once)

---

## Support

- Check `data/gui.log` inside the portable folder for error details.
- Run `start_app_debug.bat` to see the console output directly.
- Run `verify_install.bat` to diagnose missing components.
