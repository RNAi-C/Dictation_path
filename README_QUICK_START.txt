PathDictate v0.2.3 -- Quick Start Guide
========================================

GETTING STARTED
---------------
1.  Extract the ZIP file to any folder  (Desktop, USB drive, etc.)
2.  Open the extracted folder
3.  Double-click  START_PATHDICTATE.bat
4.  Wait 10-30 seconds for the Whisper model to load
5.  You are ready to dictate!

HOW TO DICTATE
--------------
  Press F9       Start recording  (button turns red, timer counts)
  Speak clearly  Thai or English -- mixed is supported
  Press F9       Stop recording  (app transcribes automatically)
  Text appears   in the Corrected panel, ready to edit

SAVING YOUR WORK
----------------
  Ctrl+S         Save draft
  Ctrl+Shift+S   Save As
  Ctrl+O         Open saved draft
  Ctrl+N         New draft

  Autosave runs every 60 seconds automatically.

AI REWRITE (OPTIONAL)
---------------------
  Select text -> click "Rewrite Selected" to polish in formal English
  Or click "Rewrite to Pathology English" to convert Thai-English
    dictation into professional English report prose.

  Both rewrite functions require Ollama + Qwen installed.
  Use  Tools -> AI Model Manager  to set up Ollama/Qwen.

  The app works FULLY without Ollama -- only rewrite is unavailable.

WHISPER MODEL
-------------
  Settings -> Browse Model Folder   to select a different model
  Settings -> Reload Model          to reload after changing

PRIVACY
-------
  No cloud.  No internet.  No telemetry.
  Audio is never saved permanently.
  Drafts remain on this computer only.
  AI rewrite uses your own computer only (localhost).

TROUBLESHOOTING
---------------
  App does not start?
    Right-click START_PATHDICTATE.bat -> Run as administrator

  No microphone detected?
    Check Windows sound settings (right-click speaker icon in taskbar)

  Transcription is slow?
    Normal on CPU: 5-20 s per 30-second recording
    Install NVIDIA drivers for automatic GPU speed-up

  Rewrite button greyed out?
    Ollama not running -- see AI REWRITE section above
