"""
model_manager_dialog.py — AI Model Manager dialog for PathDictate.

Allows non-technical users to check Ollama/Qwen status and download models
without using the command line.

PRIVACY: No patient text is sent anywhere during model management.
OFFLINE: Only the "Download Model" action requires internet.
"""
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import webbrowser

# Colour constants (duplicated from gui_app to keep this module standalone)
BG       = "#F4F6FB"
BG2      = "#FFFFFF"
BORDER   = "#CDD0E3"
ACCENT   = "#1A5FB4"
GREEN_OK = "#1A7A4A"
AMBER    = "#956E00"
RED_REC  = "#C0392B"
TEXT     = "#1A1C2E"
TEXT_DIM = "#6B6D88"

FONT_UI    = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 10)
FONT_HEAD  = ("Segoe UI", 13, "bold")


class ModelManagerDialog(tk.Toplevel):
    """
    Simple AI Model Manager.
    Shows Ollama/Qwen status and provides one-click download for non-technical users.
    """

    OLLAMA_DOWNLOAD_URL = "https://ollama.ai"
    RECOMMENDED_MODEL   = "qwen2.5:7b"
    ADVANCED_MODEL      = "qwen2.5:14b"

    def __init__(self, parent, ollama_client, cfg):
        super().__init__(parent)
        self.title("AI Model Manager")
        self.configure(bg=BG)
        self.geometry("560x480")
        self.minsize(480, 420)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._client      = ollama_client
        self._cfg         = cfg
        self._dl_thread   = None
        self._selected_model = self.RECOMMENDED_MODEL

        self._build()
        self._refresh_status()

    # ── UI build ──────────────────────────────────────────────────────────────

    def _build(self):
        pad = tk.Frame(self, bg=BG, padx=20, pady=16)
        pad.pack(fill="both", expand=True)
        pad.columnconfigure(1, weight=1)

        # Title
        tk.Label(pad, text="AI Model Manager",
                 font=FONT_HEAD, bg=BG, fg=ACCENT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        tk.Label(pad,
                 text="Dictation works without AI. AI rewrite requires Ollama + Qwen.",
                 font=FONT_SMALL, bg=BG, fg=TEXT_DIM).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 16))

        # ── Status grid ───────────────────────────────────────────────────────
        status_frame = tk.LabelFrame(pad, text=" Status ", bg=BG,
                                     fg=ACCENT, font=FONT_SMALL,
                                     relief="groove", bd=1)
        status_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        status_frame.columnconfigure(1, weight=1)

        def row(r, label, var):
            tk.Label(status_frame, text=label, font=FONT_SMALL,
                     bg=BG, fg=TEXT, anchor="w", width=22).grid(
                row=r, column=0, padx=(10, 4), pady=4, sticky="w")
            lbl = tk.Label(status_frame, textvariable=var, font=FONT_SMALL,
                           bg=BG, anchor="w")
            lbl.grid(row=r, column=1, padx=(0, 10), pady=4, sticky="w")
            return lbl

        self._v_ollama_inst  = tk.StringVar(value="Checking…")
        self._v_ollama_run   = tk.StringVar(value="Checking…")
        self._v_model_status = tk.StringVar(value="Checking…")
        self._v_sel_model    = tk.StringVar(value=self.RECOMMENDED_MODEL)

        self._lbl_ollama_inst  = row(0, "Ollama installed:",  self._v_ollama_inst)
        self._lbl_ollama_run   = row(1, "Ollama running:",    self._v_ollama_run)
        self._lbl_model_status = row(2, "Model status:",      self._v_model_status)
        row(3, "Selected model:",    self._v_sel_model)

        # ── Model selection ───────────────────────────────────────────────────
        sel_frame = tk.Frame(pad, bg=BG)
        sel_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        tk.Label(sel_frame, text="Model:", font=FONT_SMALL,
                 bg=BG, fg=TEXT).pack(side="left", padx=(0, 8))
        self._model_var = tk.StringVar(value=self.RECOMMENDED_MODEL)
        for m in (self.RECOMMENDED_MODEL, self.ADVANCED_MODEL):
            tk.Radiobutton(sel_frame, text=m, variable=self._model_var, value=m,
                           font=FONT_SMALL, bg=BG, fg=TEXT,
                           activebackground=BG, selectcolor=BG2,
                           command=self._on_model_select).pack(side="left", padx=6)

        # ── Progress log ──────────────────────────────────────────────────────
        self._log = tk.Text(pad, height=6, font=("Consolas", 9),
                            bg=BG2, fg=TEXT, relief="solid", bd=1,
                            state="disabled", wrap="word")
        self._log.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 16))
        pad.rowconfigure(4, weight=1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(pad, bg=BG)
        btn_frame.grid(row=5, column=0, columnspan=2, sticky="ew")

        def btn(text, cmd, bg, fg="white", state="normal"):
            b = tk.Button(btn_frame, text=text, command=cmd,
                          bg=bg, fg=fg, activebackground=bg,
                          font=("Segoe UI", 10, "bold"),
                          relief="raised", bd=2, padx=12, pady=6,
                          cursor="hand2", state=state)
            b.pack(side="left", padx=(0, 8))
            return b

        btn("Get Ollama",        self._open_ollama_page, "#555577")
        self._btn_start  = btn("Start Ollama",   self._start_ollama, "#1A5FB4")
        self._btn_dl     = btn("Download Model", self._download_model, "#1A7A4A")
        self._btn_test   = btn("Test Rewrite",   self._test_rewrite,  "#956E00")
        tk.Button(btn_frame, text="Close", command=self.destroy,
                  bg="#DDDDDD", fg=TEXT, font=FONT_SMALL,
                  relief="raised", bd=1, padx=10, pady=6).pack(side="right")

    # ── Status refresh ────────────────────────────────────────────────────────

    def _refresh_status(self):
        self._log_msg("Checking Ollama status…")
        threading.Thread(target=self._check_status_bg, daemon=True).start()

    def _check_status_bg(self):
        ollama_installed = self._is_ollama_installed()
        ollama_running   = self._client.is_ollama_running() if ollama_installed else False
        model_ok         = False
        if ollama_running:
            model_ok = self._client.is_model_available(self._model_var.get())

        self.after(0, self._apply_status, ollama_installed, ollama_running, model_ok)

    def _apply_status(self, installed, running, model_ok):
        def coloured(lbl, var, text, color):
            var.set(text); lbl.config(fg=color)

        coloured(self._lbl_ollama_inst,
                 self._v_ollama_inst,
                 "Installed ✓" if installed else "Not installed",
                 GREEN_OK if installed else RED_REC)

        coloured(self._lbl_ollama_run,
                 self._v_ollama_run,
                 "Running ✓" if running else "Not running",
                 GREEN_OK if running else AMBER)

        coloured(self._lbl_model_status,
                 self._v_model_status,
                 f"Installed ✓  ({self._model_var.get()})" if model_ok
                 else f"Not installed  ({self._model_var.get()})",
                 GREEN_OK if model_ok else AMBER)

        self._v_sel_model.set(self._model_var.get())
        msg = "Ready — AI rewrite available." if (running and model_ok) \
              else ("Ollama not running." if not running
                    else f"Model '{self._model_var.get()}' not installed.")
        self._log_msg(msg)

    def _is_ollama_installed(self) -> bool:
        import shutil, os
        if shutil.which("ollama"):
            return True
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]
        return any(os.path.exists(c) for c in candidates)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_model_select(self):
        self._selected_model = self._model_var.get()
        self._refresh_status()

    def _open_ollama_page(self):
        webbrowser.open(self.OLLAMA_DOWNLOAD_URL)
        self._log_msg("Opening Ollama download page in browser…")

    def _start_ollama(self):
        self._log_msg("Attempting to start Ollama…")
        ok = self._client.start_ollama()
        if ok:
            self._log_msg("Ollama launch command sent. Waiting for readiness…")
            threading.Thread(target=self._wait_ready_bg, daemon=True).start()
        else:
            self._log_msg("Could not start Ollama. Is it installed?")

    def _wait_ready_bg(self):
        ready = self._client.wait_until_ready(timeout=20, interval=2)
        self.after(0, self._log_msg,
                   "Ollama is ready." if ready
                   else "Ollama did not respond within 20 s.")
        self.after(0, self._refresh_status)

    def _download_model(self):
        model = self._model_var.get()
        if not self._client.is_ollama_running():
            messagebox.showwarning(
                "Ollama not running",
                "Start Ollama first before downloading a model.",
                parent=self)
            return
        if self._client.is_model_available(model):
            messagebox.showinfo(
                "Already installed",
                f"'{model}' is already installed.\nNo download needed.",
                parent=self)
            return
        if not messagebox.askyesno(
                "Download model?",
                f"This will download '{model}' from Ollama's servers.\n\n"
                "Internet connection is required for this step only.\n"
                "After download, AI rewrite runs fully locally.\n\n"
                "Proceed?", parent=self):
            return
        self._btn_dl.config(state="disabled")
        self._log_msg(f"Downloading {model}… (this may take several minutes)")
        threading.Thread(target=self._dl_bg, args=(model,), daemon=True).start()

    def _dl_bg(self, model: str):
        import shutil, os, subprocess
        ollama_exe = shutil.which("ollama") or next(
            (c for c in [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"),
            ] if os.path.exists(c)), None)
        if not ollama_exe:
            self.after(0, self._log_msg, "ollama executable not found.")
            self.after(0, lambda: self._btn_dl.config(state="normal"))
            return
        try:
            kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1)
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen([ollama_exe, "pull", model], **kwargs)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.after(0, self._log_msg, line)
            proc.wait()
            if proc.returncode == 0:
                self.after(0, self._log_msg, f"✓ {model} downloaded successfully.")
            else:
                self.after(0, self._log_msg, f"Download ended with code {proc.returncode}.")
        except Exception as exc:
            self.after(0, self._log_msg, f"Download error: {exc}")
        finally:
            self.after(0, lambda: self._btn_dl.config(state="normal"))
            self.after(0, self._refresh_status)

    def _test_rewrite(self):
        if not self._client.is_ollama_running():
            messagebox.showwarning("Ollama not running",
                                   "Start Ollama first.", parent=self)
            return
        model = self._model_var.get()
        if not self._client.is_model_available(model):
            messagebox.showwarning("Model not installed",
                                   f"'{model}' is not installed.\nDownload it first.",
                                   parent=self)
            return
        self._log_msg("Testing AI rewrite with sample text…")
        threading.Thread(target=self._test_bg, args=(model,), daemon=True).start()

    def _test_bg(self, model: str):
        from ollama_client import OllamaClient
        client = OllamaClient(endpoint=self._cfg.llm.endpoint,
                              model=model,
                              timeout=30)
        try:
            result = client.generate(
                system_prompt="You are a pathology assistant. Rewrite the text in formal English.",
                user_text="tumor size two point five cm margins clear no LVI",
                temperature=0.1, max_tokens=80)
            self.after(0, self._log_msg, f"Test result: {result[:120]}")
            self.after(0, self._log_msg, "✓ AI rewrite is working.")
        except Exception as exc:
            self.after(0, self._log_msg, f"Test failed: {exc}")

    # ── Log helper ────────────────────────────────────────────────────────────

    def _log_msg(self, msg: str):
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.config(state="disabled")
