"""
model_manager_dialog.py — AI Model Manager dialog for PathDictate.

Lets non-technical users check Ollama/Qwen status, browse installed models,
download new ones, and set which model PathDictate uses — all without a
command line.

PRIVACY: No patient text is ever sent during model management.
INTERNET: Only "Download Model" requires internet.  Everything else is local.
"""
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

# winreg is Windows-only — guard the import
try:
    import winreg as _winreg
except ImportError:
    _winreg = None

# ── Colours (self-contained — no dependency on gui_app) ──────────────────────
BG        = "#F4F6FB"
BG2       = "#FFFFFF"
BG3       = "#EAECF5"
BORDER    = "#CDD0E3"
ACCENT    = "#1A5FB4"
GREEN_OK  = "#1A7A4A"
AMBER     = "#956E00"
RED_REC   = "#C0392B"
TEXT      = "#1A1C2E"
TEXT_MED  = "#3D3F58"
TEXT_DIM  = "#6B6D88"

FN        = ("Segoe UI", 10)
FN_BOLD   = ("Segoe UI", 10, "bold")
FN_HEAD   = ("Segoe UI", 13, "bold")
FN_MONO   = ("Consolas",  9)

# ── Suggested models shown in the picker ─────────────────────────────────────
SUGGESTED_MODELS = [
    "qwen2.5:7b",
    "qwen2.5:14b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "llama3.2:3b",
    "llama3.2:1b",
    "phi3.5:mini",
    "mistral:7b",
]

OLLAMA_DOWNLOAD_URL = "https://ollama.ai"


# ── Dialog ────────────────────────────────────────────────────────────────────

class ModelManagerDialog(tk.Toplevel):
    """
    AI Model Manager.

    Shows:
      • Ollama installed / running status
      • All models currently installed in Ollama (fetched live)
      • Download picker for new models
      • Custom model name entry
      • One-click download with streaming progress

    The selected model is written back to cfg.llm.model so the next
    rewrite call uses it.
    """

    def __init__(self, parent, ollama_client, cfg):
        super().__init__(parent)
        self.title("AI Model Manager")
        self.configure(bg=BG)
        self.geometry("620x580")
        self.minsize(520, 460)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._client = ollama_client
        self._cfg    = cfg
        self._build()
        self.after(10,  self._fit_to_screen)  # size dialog after layout
        self.after(150, self._refresh_all)    # first status check

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        root = tk.Frame(self, bg=BG, padx=18, pady=6)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)

        # ── Title ─────────────────────────────────────────────────────────────
        tk.Label(root, text="AI Model Manager",
                 font=FN_HEAD, bg=BG, fg=ACCENT
                 ).grid(row=0, column=0, sticky="w")
        tk.Label(root,
                 text="Dictation works without AI.  "
                      "AI rewrite requires the Ollama app  +  a downloaded AI model.",
                 font=FN, bg=BG, fg=TEXT_DIM
                 ).grid(row=1, column=0, sticky="w", pady=(1, 6))

        # ── STEP 1 — Ollama application ───────────────────────────────────────
        sf = tk.LabelFrame(root,
                           text="  Step 1 — Ollama Application  "
                                "(install once, runs in background)",
                           bg=BG, fg=ACCENT, font=FN,
                           relief="groove", bd=1)
        sf.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        sf.columnconfigure(1, weight=1)

        self._v_installed = tk.StringVar(value="Checking…")
        self._v_running   = tk.StringVar(value="Checking…")
        self._l_installed = self._status_row(sf, 0, "App installed:", self._v_installed)
        self._l_running   = self._status_row(sf, 1, "App running:",   self._v_running)

        btn_row = tk.Frame(sf, bg=BG)
        btn_row.grid(row=2, column=0, columnspan=2, padx=8, pady=(2, 2), sticky="w")
        self._mk_btn(btn_row,
                     "Install Ollama App (opens website)",
                     self._open_ollama_page,
                     "#555577").pack(side="left", padx=(0, 6))
        self._btn_start = self._mk_btn(btn_row, "Start Ollama App",
                                       self._start_ollama, ACCENT)
        self._btn_start.pack(side="left")

        auto_row = tk.Frame(sf, bg=BG)
        auto_row.grid(row=3, column=0, columnspan=2, padx=8, pady=(2, 4), sticky="w")
        self._auto_start_var = tk.BooleanVar(
            value=getattr(self._cfg.llm, "auto_start_ollama", True))
        tk.Checkbutton(
            auto_row,
            text="Auto-start Ollama app when PathDictate opens",
            variable=self._auto_start_var,
            command=self._toggle_auto_start,
            bg=BG, fg=TEXT, activebackground=BG,
            selectcolor=BG2, font=FN,
        ).pack(side="left")

        # ── STEP 2 — Download an AI model ─────────────────────────────────────
        df = tk.LabelFrame(root,
                           text="  Step 2 — Download an AI Model  "
                                "(one-time download, runs offline after)",
                           bg=BG, fg=ACCENT, font=FN,
                           relief="groove", bd=1)
        df.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        df.columnconfigure(1, weight=1)

        pick_row = tk.Frame(df, bg=BG)
        pick_row.grid(row=0, column=0, columnspan=3,
                      padx=8, pady=(6, 3), sticky="w")
        tk.Label(pick_row, text="Model name:", font=FN, bg=BG, fg=TEXT
                 ).pack(side="left", padx=(0, 6))
        self._dl_model_var = tk.StringVar(value=SUGGESTED_MODELS[0])
        combo = ttk.Combobox(pick_row, textvariable=self._dl_model_var,
                             values=SUGGESTED_MODELS, font=FN, width=24)
        combo.pack(side="left", padx=(0, 8))
        combo.bind("<Return>", lambda _: self._download_model())
        self._btn_dl = self._mk_btn(pick_row,
                                    "⬇  Download AI Model",
                                    self._download_model, GREEN_OK)
        self._btn_dl.pack(side="left")

        tk.Label(df,
                 text="Recommended: qwen2.5:7b (~4.5 GB).  "
                      "Smaller option: qwen2.5:3b (~2 GB).  "
                      "After download, no internet needed.",
                 font=("Segoe UI", 9), bg=BG, fg=TEXT_DIM, justify="left"
                 ).grid(row=1, column=0, columnspan=3,
                        padx=8, pady=(0, 3), sticky="w")

        # ── Download progress bar (always visible) ─────────────────────────
        pb_frame = tk.Frame(df, bg=BG)
        pb_frame.grid(row=2, column=0, columnspan=3,
                      padx=8, pady=(0, 5), sticky="ew")
        pb_frame.columnconfigure(0, weight=1)

        # Status label — updated via direct .config(text=…), no StringVar
        self._pb_lbl = tk.Label(
            pb_frame, text="Ready",
            font=("Segoe UI", 9, "bold"), bg=BG, fg=TEXT_DIM, anchor="w")
        self._pb_lbl.grid(row=0, column=0, sticky="w", pady=(0, 2))

        # Progress bar — updated via self._pb["value"] = x (no DoubleVar)
        self._pb = ttk.Progressbar(
            pb_frame, maximum=100, mode="determinate", length=400)
        self._pb.grid(row=1, column=0, sticky="ew")

        # ── STEP 3 — Select active model ──────────────────────────────────────
        mf = tk.LabelFrame(root,
                           text="  Step 3 — Select Active AI Model",
                           bg=BG, fg=ACCENT, font=FN,
                           relief="groove", bd=1)
        mf.grid(row=4, column=0, sticky="nsew", pady=(0, 5))
        mf.columnconfigure(0, weight=1)
        mf.rowconfigure(0, weight=1, minsize=52)   # always show listbox
        mf.rowconfigure(1, minsize=38)              # always show button row
        root.rowconfigure(4, weight=2, minsize=110)

        list_frame = tk.Frame(mf, bg=BG)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._model_lb = tk.Listbox(
            list_frame, font=FN_MONO, bg=BG2, fg=TEXT,
            selectbackground=ACCENT, selectforeground="white",
            relief="solid", bd=1, height=3,
            activestyle="none")
        vsb = tk.Scrollbar(list_frame, orient="vertical",
                           command=self._model_lb.yview)
        self._model_lb.configure(yscrollcommand=vsb.set)
        self._model_lb.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._model_lb.bind("<<ListboxSelect>>", self._on_installed_select)

        mb_row = tk.Frame(mf, bg=BG)
        mb_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._btn_use = self._mk_btn(mb_row, "Use Selected Model",
                                     self._use_selected_model, GREEN_OK)
        self._btn_use.pack(side="left", padx=(0, 6))
        self._btn_use.config(state="disabled")
        self._mk_btn(mb_row, "Refresh List", self._refresh_all,
                     "#555577").pack(side="left")
        self._v_active = tk.StringVar(value="")
        tk.Label(mb_row, textvariable=self._v_active, font=FN,
                 bg=BG, fg=GREEN_OK).pack(side="left", padx=(10, 0))

        # ── Progress / log ────────────────────────────────────────────────────
        lf = tk.LabelFrame(root, text=" Progress / Log ",
                           bg=BG, fg=ACCENT, font=FN,
                           relief="groove", bd=1)
        lf.grid(row=5, column=0, sticky="nsew", pady=(0, 5))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        root.rowconfigure(5, weight=1, minsize=55)

        self._log = tk.Text(lf, font=FN_MONO, bg=BG2, fg=TEXT,
                            relief="flat", bd=0, height=3,
                            state="disabled", wrap="word")
        lsb = tk.Scrollbar(lf, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=lsb.set)
        self._log.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=4)
        lsb.grid(row=0, column=1, sticky="ns", pady=4)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bot = tk.Frame(root, bg=BG)
        bot.grid(row=6, column=0, sticky="ew")
        self._btn_test = self._mk_btn(bot, "Test AI Rewrite",
                                      self._test_rewrite, AMBER)
        self._btn_test.pack(side="left")
        tk.Button(bot, text="Close", command=self.destroy,
                  bg=BG3, fg=TEXT, font=FN,
                  relief="raised", bd=1, padx=14, pady=5,
                  cursor="hand2").pack(side="right")

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _fit_to_screen(self):
        """Resize the dialog so all content is visible without scrolling."""
        self.update_idletasks()
        # winfo_screenheight() returns logical pixels (DPI-adjusted on Windows)
        screen_h  = self.winfo_screenheight()
        # Reserve ~80 px for taskbar + window chrome
        avail_h   = screen_h - 80
        # Natural minimum height the layout requires
        req_h     = self.winfo_reqheight()
        # Use whichever is larger: our desired 580 or the natural req, but cap
        # to available screen space
        target_h  = max(req_h + 10, 460)
        target_h  = min(target_h, avail_h)
        cur_w     = self.winfo_width() or 620
        # Place at the top of the work-area so the bottom isn't cropped
        self.geometry(f"{cur_w}x{target_h}+0+0")
        self.minsize(520, min(460, target_h))

    # ── Status helpers ────────────────────────────────────────────────────────

    def _status_row(self, parent, row, label, var):
        tk.Label(parent, text=label, font=FN, bg=BG, fg=TEXT,
                 anchor="w", width=20
                 ).grid(row=row, column=0, padx=(8, 4), pady=3, sticky="w")
        lbl = tk.Label(parent, textvariable=var, font=FN_BOLD,
                       bg=BG, anchor="w")
        lbl.grid(row=row, column=1, padx=(0, 8), pady=3, sticky="w")
        return lbl

    @staticmethod
    def _mk_btn(parent, text, cmd, bg):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=bg, fg="white", activebackground=bg,
                      font=FN_BOLD, relief="raised", bd=2,
                      padx=10, pady=5, cursor="hand2")
        return b

    # ── Thread-safe helpers: background threads post work to the main thread ──
    # self.after(0, fn) posts to Tcl's event queue which is thread-safe in
    # Tcl 8.6+ (Python's _tkinter uses Tcl_ThreadQueueEvent from non-main threads).

    def _post(self, fn):
        """Schedule a zero-arg callable to run in the main (UI) thread."""
        try:
            if self.winfo_exists():
                self.after(0, fn)
        except Exception:
            pass

    def _post_log(self, msg: str):
        self._post(lambda m=msg: self._log_msg(m))

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._log_msg("Refreshing Ollama status…")
        threading.Thread(target=self._refresh_bg, daemon=True).start()

    def _refresh_bg(self):
        """Background thread: probe Ollama then post results to main thread."""
        try:
            models    = self._client.list_models()
            running   = bool(models) or self._client.is_ollama_running()
            installed = running or self._is_ollama_installed()
            self._post(lambda: self._apply_status(installed, running, models))
        except Exception as exc:
            import traceback
            self._post_log(f"Refresh error: {exc}\n{traceback.format_exc()}")

    def _apply_status(self, installed: bool, running: bool, models: list):
        """Called in the main thread."""
        if installed:
            self._v_installed.set("Installed  ✓")
            self._l_installed.config(text="Installed  ✓", fg=GREEN_OK)
        else:
            self._v_installed.set("Not installed")
            self._l_installed.config(text="Not installed", fg=RED_REC)

        if running:
            self._v_running.set("Running  ✓")
            self._l_running.config(text="Running  ✓", fg=GREEN_OK)
        else:
            self._v_running.set("Not running")
            self._l_running.config(text="Not running", fg=AMBER)

        # ── Model list ─────────────────────────────────────────────────────
        self._model_lb.delete(0, "end")
        if models:
            for m in sorted(models):
                self._model_lb.insert("end", m)
            self._log_msg(f"Found {len(models)} installed model(s).")
        elif running:
            self._log_msg(
                "Ollama is running but no models are installed yet.\n"
                "Use 'Download a Model' below to install one (e.g. qwen2.5:7b).")
        else:
            self._log_msg(
                "Ollama is not running.  Click 'Start Ollama' above,\n"
                "or install Ollama from ollama.ai first.")

        # ── Highlight active model ─────────────────────────────────────────
        active = self._cfg.llm.model
        self._v_active.set(f"Active: {active}")
        # Try exact match first, then prefix fallback
        active_l = active.lower()
        prefix   = active_l.split(":")[0] + ":"
        selected = False
        for i in range(self._model_lb.size()):
            if self._model_lb.get(i).lower() == active_l:
                self._model_lb.selection_set(i)
                self._model_lb.see(i)
                selected = True
                break
        if not selected:
            for i in range(self._model_lb.size()):
                if self._model_lb.get(i).lower().startswith(prefix):
                    self._model_lb.selection_set(i)
                    self._model_lb.see(i)
                    break

        self._btn_use.config(
            state="normal" if self._model_lb.curselection() else "disabled")

    # ── Ollama exe discovery ──────────────────────────────────────────────────

    @staticmethod
    def _ollama_candidate_paths() -> list:
        """All plausible Ollama executable locations on this machine."""
        paths = []

        # 1. System PATH
        in_path = shutil.which("ollama")
        if in_path:
            paths.append(in_path)

        # 2. Well-known Windows install locations
        if sys.platform == "win32":
            env_candidates = [
                r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                r"%LOCALAPPDATA%\Ollama\ollama.exe",
                r"%APPDATA%\Ollama\ollama.exe",
                r"%PROGRAMFILES%\Ollama\ollama.exe",
                r"%PROGRAMFILES(X86)%\Ollama\ollama.exe",
            ]
            for p in env_candidates:
                expanded = os.path.expandvars(p)
                if expanded not in paths:
                    paths.append(expanded)
            paths += [
                r"C:\Ollama\ollama.exe",
                r"C:\Program Files\Ollama\ollama.exe",
                r"C:\Program Files (x86)\Ollama\ollama.exe",
            ]

            # 3. Windows registry — Ollama registers its install dir
            if _winreg:
                for root in (
                    _winreg.HKEY_LOCAL_MACHINE,
                    _winreg.HKEY_CURRENT_USER,
                ):
                    for sub in (
                        r"SOFTWARE\Ollama",
                        r"SOFTWARE\WOW6432Node\Ollama",
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ollama.exe",
                    ):
                        try:
                            with _winreg.OpenKey(root, sub) as k:
                                val, _ = _winreg.QueryValueEx(k, "")
                                if val and val not in paths:
                                    paths.append(val)
                        except OSError:
                            pass
        return paths

    def _find_ollama_exe(self) -> str | None:
        """Return the path to the ollama executable, or None if not found."""
        for p in self._ollama_candidate_paths():
            if os.path.isfile(p):
                return p
        # Last resort: try subprocess — works if PATH is set but shutil missed it
        try:
            r = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, timeout=3,
                **({"creationflags": subprocess.CREATE_NO_WINDOW}
                   if sys.platform == "win32" else {}),
            )
            if r.returncode == 0:
                return shutil.which("ollama") or "ollama"
        except Exception:
            pass
        return None

    def _is_ollama_installed(self) -> bool:
        return self._find_ollama_exe() is not None

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_auto_start(self):
        val = self._auto_start_var.get()
        self._cfg.llm.auto_start_ollama = val
        self._cfg.save_user_settings()
        self._log_msg(
            f"Auto-start Ollama on launch: {'enabled' if val else 'disabled'}.")

    def _on_installed_select(self, _=None):
        sel = self._model_lb.curselection()
        self._btn_use.config(state="normal" if sel else "disabled")
        if sel:
            self._dl_model_var.set(self._model_lb.get(sel[0]))

    def _use_selected_model(self):
        sel = self._model_lb.curselection()
        if not sel:
            return
        model = self._model_lb.get(sel[0])
        self._cfg.llm.model = model
        self._client.model  = model
        self._v_active.set(f"Active: {model}")
        self._cfg.save_user_settings()
        self._log_msg(f"Active model set to: {model}")

    def _open_ollama_page(self):
        webbrowser.open(OLLAMA_DOWNLOAD_URL)
        self._log_msg("Opening ollama.ai in your browser…")

    def _start_ollama(self):
        # Change button immediately so user gets visual feedback right away.
        self._btn_start.config(state="disabled", text="Starting…")
        self._log_msg("Attempting to start Ollama…")
        # Run everything (including the blocking wait) on a background thread.
        threading.Thread(target=self._start_ollama_bg, daemon=True).start()

    def _start_ollama_bg(self):
        try:
            ok = self._client.start_ollama()
            if ok:
                self._post_log("Ollama launched — waiting up to 20 s for it to be ready…")
                ready = self._client.wait_until_ready(timeout=20, interval=2)
                if ready:
                    self._post_log("Ollama is ready  ✓")
                else:
                    self._post_log(
                        "Ollama did not respond within 20 s.  "
                        "It may still be starting — try refreshing in a moment.")
            else:
                self._post_log(
                    "Could not launch Ollama.  "
                    "Is it installed?  Click 'Install Ollama App' above.")
        except Exception as exc:
            self._post_log(f"Start error: {exc}")
        finally:
            self._post(lambda: self._btn_start.config(
                state="normal", text="Start Ollama App"))
            self._post(self._refresh_all)

    def _download_model(self):
        model = self._dl_model_var.get().strip()
        if not model:
            messagebox.showwarning("No model specified",
                                   "Enter a model name (e.g. qwen2.5:7b).",
                                   parent=self)
            return
        # Start immediately — no blocking network check on the main thread.
        # If Ollama is not running the download thread will report the error
        # in the progress bar within ~1 second.
        self._btn_dl.config(state="disabled", text="Downloading…")
        self._pb_reset()
        self._log_msg(f"▶ Starting download: {model}")
        threading.Thread(target=self._dl_bg, args=(model,),
                         daemon=True, name="ollama-dl").start()

    # ── Progress bar helpers (always called in main thread via _poll_q) ──────
    # Use direct widget['value'] = x instead of DoubleVar to avoid binding bugs.

    def _pb_busy(self, status: str):
        """Animated indeterminate — manifest pull, verify, write phases."""
        self._pb.stop()
        self._pb.config(mode="indeterminate")
        self._pb["value"] = 0
        self._pb_lbl.config(text=status, fg=ACCENT)
        self._pb.start(10)

    def _pb_update(self, value: float, status: str):
        """Deterministic fill — actual download percentage."""
        self._pb.stop()
        self._pb.config(mode="determinate")
        self._pb["value"] = value
        self._pb_lbl.config(text=status, fg=ACCENT)

    def _pb_done(self, success: bool, status: str):
        """Final state — green tick or red cross."""
        self._pb.stop()
        self._pb.config(mode="determinate")
        self._pb["value"] = 100 if success else 0
        color = GREEN_OK if success else RED_REC
        self._pb_lbl.config(text=status, fg=color)

    def _pb_reset(self):
        """Return to idle / ready state."""
        self._pb.stop()
        self._pb.config(mode="determinate")
        self._pb["value"] = 0
        self._pb_lbl.config(text="Ready", fg=TEXT_DIM)

    # ── Download via Ollama REST API ──────────────────────────────────────────
    # Uses POST /api/pull with stream=true → clean JSON lines, no ANSI issues.

    def _dl_bg(self, model: str):
        import json as _json
        import urllib.request as _req

        self._post_log("● Thread started — connecting to Ollama API…")
        self._post(lambda: self._pb_busy("Connecting to Ollama…"))

        url     = f"{self._client.base_url}/api/pull"
        payload = _json.dumps({"name": model, "stream": True}).encode()
        request = _req.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")

        try:
            # Track aggregate bytes across all layers
            layer_total: dict[str, int] = {}
            layer_done:  dict[str, int] = {}
            last_pct  = -1
            last_phase = ""

            with _req.urlopen(request, timeout=7200) as resp:
                for raw_line in resp:
                    try:
                        obj = _json.loads(raw_line.decode("utf-8", errors="replace"))
                    except Exception:
                        continue

                    status    = obj.get("status", "")
                    digest    = obj.get("digest", "")
                    total     = obj.get("total",     0)
                    completed = obj.get("completed", 0)

                    # ── Phase labels ──────────────────────────────────────
                    if status == "pulling manifest":
                        if last_phase != "manifest":
                            last_phase = "manifest"
                            self._post(lambda: self._pb_busy("Pulling manifest…"))
                            self._post_log("Pulling manifest…")
                        continue

                    if status == "verifying sha256 digest":
                        if last_phase != "verify":
                            last_phase = "verify"
                            self._post(lambda: self._pb_busy("Verifying download…"))
                            self._post_log("Verifying download…")
                        continue

                    if status == "writing manifest":
                        if last_phase != "write":
                            last_phase = "write"
                            self._post(lambda: self._pb_busy("Writing manifest…"))
                            self._post_log("Writing manifest…")
                        continue

                    if status in ("removing any unused layers", "success"):
                        continue   # handled after loop

                    # ── Layer download progress ───────────────────────────
                    if status.startswith("pulling") and digest and total:
                        layer_total[digest] = total
                        layer_done[digest]  = completed

                        grand_total = sum(layer_total.values())
                        grand_done  = sum(layer_done.values())

                        if grand_total > 0:
                            pct = min(int(grand_done / grand_total * 100), 100)
                            if pct != last_pct:
                                last_pct   = pct
                                last_phase = "dl"

                                def _fmt(b):
                                    if b >= 1_073_741_824:
                                        return f"{b/1_073_741_824:.1f} GB"
                                    if b >= 1_048_576:
                                        return f"{b/1_048_576:.0f} MB"
                                    return f"{b/1024:.0f} KB"

                                size_str = (f"  ({_fmt(grand_done)} / "
                                            f"{_fmt(grand_total)})")
                                label = f"Downloading…  {pct}%{size_str}"
                                self._post(lambda v=float(pct), s=label:
                                           self._pb_update(v, s))
                                if pct in (0, 25, 50, 75, 100):
                                    self._post_log(label)
                        continue

            # ── Success ───────────────────────────────────────────────────
            self._post(lambda: self._pb_done(
                True, f"Complete!  '{model}' is ready to use."))
            self._post_log(f"'{model}' downloaded successfully.")

        except Exception as exc:
            self._post(lambda e=str(exc): self._pb_done(False, f"Error: {e}"))
            self._post_log(f"Download error: {exc}")
        finally:
            self._post(lambda: self._btn_dl.config(
                state="normal", text="⬇  Download AI Model"))
            self._post(self._refresh_all)

    def _test_rewrite(self):
        if not self._client.is_ollama_running():
            messagebox.showwarning("Ollama not running",
                                   "Start Ollama first.", parent=self)
            return
        model = self._cfg.llm.model
        if not self._client.is_model_available(model):
            messagebox.showwarning(
                "Model not installed",
                f"Active model '{model}' is not installed.\n"
                "Select an installed model or download one first.",
                parent=self)
            return
        self._log_msg(f"Testing rewrite with model: {model}…")
        threading.Thread(target=self._test_bg, args=(model,), daemon=True).start()

    def _test_bg(self, model: str):
        from ollama_client import OllamaClient
        client = OllamaClient(
            endpoint=self._cfg.llm.endpoint,
            model=model, timeout=30)
        try:
            result = client.generate(
                system_prompt=(
                    "You are a pathology report assistant. "
                    "Rewrite the text in formal English pathology style."),
                user_text="tumor size two point five cm margins clear no LVI",
                temperature=0.1, max_tokens=80)
            self._post_log(f"Result: {result[:160]}")
            self._post_log("Test passed — AI rewrite is working.")
        except Exception as exc:
            self._post_log(f"Test failed: {exc}")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log_msg(self, msg: str):
        self._log.config(state="normal")
        self._log.insert("end", msg.rstrip() + "\n")
        self._log.see("end")
        self._log.config(state="disabled")
