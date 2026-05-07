"""
Pathology Dictation Assistant - GUI
Real-time streaming transcription with live text display.
"""

import sys
import os
import json
import threading
import queue
import time
import numpy as np
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

import sounddevice as sd
from loguru import logger

from config import PathologyDictationConfig
from audio_recorder import AudioRecorder
from transcriber import PathologyTranscriber
from terminology_corrector import TerminologyCorrector
from clipboard_handler import ClipboardHandler


# ── Light palette ─────────────────────────────────────────────────────────────
BG         = "#F4F6FB"   # page background — very light blue-white
BG2        = "#FFFFFF"   # card / panel background — pure white
BG3        = "#EAECf5"   # input fields / notebook area — pale lavender-gray
BORDER     = "#CDD0E3"   # subtle dividers

ACCENT     = "#1A5FB4"   # primary blue — strong, accessible
ACCENT_H   = "#124A8C"   # hover
ACCENT_L   = "#D6E4F7"   # light tint for highlights

RED_REC    = "#C0392B"   # recording state — deep red
RED_H      = "#A93226"
RED_SOFT   = "#FDECEA"   # soft red background tint

GREEN_OK   = "#1A7A4A"   # success — dark green, readable on white
GREEN_SOFT = "#E8F5EE"

AMBER      = "#956E00"   # warning — dark amber, readable
AMBER_SOFT = "#FFF8E1"

TEXT       = "#1A1C2E"   # primary text — near-black
TEXT_MED   = "#3D3F58"   # secondary text
TEXT_DIM   = "#6B6D88"   # dimmed / placeholder
TEXT_LIVE  = "#1A5FB4"   # live transcription colour (same as accent)

FONT_UI    = ("Segoe UI", 11)
FONT_BIG   = ("Segoe UI", 14, "bold")
FONT_HEAD  = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO  = ("Consolas", 13)

FONT_SIZE_DEFAULT = 13
FONT_SIZE_MIN     = 9
FONT_SIZE_MAX     = 26

STREAM_CHUNK_SEC = 3.0
STREAM_BEAM      = 2


# ── VU meter ──────────────────────────────────────────────────────────────────

class VUMeter(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, height=14, bg=BG3,
                         highlightthickness=1, highlightbackground=BORDER, **kw)
        self._bar  = self.create_rectangle(0, 2, 0, 12, fill=GREEN_OK, outline="")
        self._peak = 0.0
        self._t    = 0.0
        self.bind("<Configure>", lambda _: self._draw(0.0))

    def update(self, rms: float):
        level = min(rms * 7, 1.0)
        now   = time.monotonic()
        if level > self._peak:
            self._peak, self._t = level, now
        elif now - self._t > 0.4:
            self._peak = max(0.0, self._peak - 0.06)
        self._draw(level)

    def reset(self):
        self._peak = 0.0
        self._draw(0.0)

    def _draw(self, level):
        w = self.winfo_width() or 300
        x = int(w * level)
        c = GREEN_OK if level < 0.65 else (AMBER if level < 0.88 else RED_REC)
        self.coords(self._bar, 0, 2, x, 12)
        self.itemconfig(self._bar, fill=c)


# ── Terminology editor ────────────────────────────────────────────────────────

class TerminologyEditor(tk.Toplevel):

    def __init__(self, parent, dict_path: Path, on_save):
        super().__init__(parent)
        self.title("Terminology Editor")
        self.configure(bg=BG)
        self.geometry("720x560")
        self.minsize(580, 420)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._path    = dict_path
        self._on_save = on_save
        self._data    = {}
        self._load()
        self._build()
        self._populate()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _build(self):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # Title
        tk.Label(root, text="Terminology Corrections",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ACCENT)\
            .grid(row=0, column=0, sticky="w")
        tk.Label(root,
                 text="Double-click a row to edit it.  Press Delete to remove selected.",
                 font=FONT_SMALL, bg=BG, fg=TEXT_DIM)\
            .grid(row=1, column=0, sticky="w", pady=(2, 10))

        # Treeview frame
        tf = tk.Frame(root, bg=BORDER, bd=1)
        tf.grid(row=2, column=0, sticky="nsew")
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(tf, columns=("spoken", "corrected"),
                                   show="headings", selectmode="browse")
        self._tree.heading("spoken",    text="You say  (speech-to-text hears)")
        self._tree.heading("corrected", text="Corrected to")
        self._tree.column("spoken",    width=320, anchor="w", minwidth=180)
        self._tree.column("corrected", width=290, anchor="w", minwidth=160)

        vsb = ttk.Scrollbar(tf, orient="vertical",   command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Treeview style
        s = ttk.Style(self)
        s.configure("Edit.Treeview",
                     background=BG2, foreground=TEXT,
                     fieldbackground=BG2, rowheight=28,
                     font=FONT_UI, borderwidth=0)
        s.configure("Edit.Treeview.Heading",
                     background=ACCENT_L, foreground=ACCENT,
                     font=("Segoe UI", 10, "bold"), relief="flat", padding=6)
        s.map("Edit.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "white")])
        self._tree.configure(style="Edit.Treeview")

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Delete>",   lambda _: self._delete_row())

        # Add / edit strip
        add = tk.Frame(root, bg=BG)
        add.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        add.columnconfigure(1, weight=1)
        add.columnconfigure(4, weight=1)

        def lbl(text):
            return tk.Label(add, text=text, font=FONT_SMALL, bg=BG, fg=TEXT_MED)

        lbl("You say:").grid(row=0, column=0, padx=(0, 6))
        self._entry_spoken = tk.Entry(add, bg=BG2, fg=TEXT, insertbackground=TEXT,
                                       relief="solid", bd=1, font=FONT_UI,
                                       highlightthickness=0)
        self._entry_spoken.grid(row=0, column=1, sticky="ew", ipady=5)

        tk.Label(add, text="→", font=("Segoe UI", 12, "bold"),
                 bg=BG, fg=ACCENT).grid(row=0, column=2, padx=12)

        lbl("Correct as:").grid(row=0, column=3, padx=(0, 6))
        self._entry_corrected = tk.Entry(add, bg=BG2, fg=TEXT, insertbackground=TEXT,
                                          relief="solid", bd=1, font=FONT_UI,
                                          highlightthickness=0)
        self._entry_corrected.grid(row=0, column=4, sticky="ew", ipady=5)

        tk.Button(add, text="Add / Update", font=FONT_UI,
                  bg=ACCENT, fg="white", activebackground=ACCENT_H,
                  activeforeground="white", relief="flat", bd=0,
                  padx=14, pady=5, cursor="hand2",
                  command=self._add_or_update)\
            .grid(row=0, column=5, padx=(12, 0))

        self._entry_spoken.bind("<Return>",    lambda _: self._entry_corrected.focus())
        self._entry_corrected.bind("<Return>", lambda _: self._add_or_update())

        # Bottom buttons
        bot = tk.Frame(root, bg=BG)
        bot.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        bot.columnconfigure(1, weight=1)

        tk.Button(bot, text="🗑  Delete Selected", font=FONT_UI,
                  bg=RED_SOFT, fg=RED_REC, activebackground="#fcd5d0",
                  relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                  command=self._delete_row).grid(row=0, column=0)

        self._count_lbl = tk.Label(bot, text="", font=FONT_SMALL,
                                    bg=BG, fg=TEXT_DIM)
        self._count_lbl.grid(row=0, column=1, padx=14, sticky="w")

        tk.Button(bot, text="✓  Save & Close", font=FONT_UI,
                  bg=GREEN_OK, fg="white", activebackground="#155f39",
                  relief="flat", bd=0, padx=16, pady=6, cursor="hand2",
                  command=self._save_close).grid(row=0, column=2)

        tk.Button(bot, text="Cancel", font=FONT_UI,
                  bg=BG3, fg=TEXT_MED, activebackground=BORDER,
                  relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                  command=self.destroy).grid(row=0, column=3, padx=(8, 0))

    def _populate(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for spoken, corrected in sorted(self._data.items()):
            self._tree.insert("", "end", values=(spoken, corrected))
        n = len(self._tree.get_children())
        self._count_lbl.config(text=f"{n} entries")

    def _add_or_update(self):
        spoken    = self._entry_spoken.get().strip().lower()
        corrected = self._entry_corrected.get().strip()
        if not spoken or not corrected:
            messagebox.showwarning("Empty field", "Both fields are required.", parent=self)
            return
        self._data[spoken] = corrected
        self._populate()
        for iid in self._tree.get_children():
            if self._tree.item(iid, "values")[0] == spoken:
                self._tree.selection_set(iid)
                self._tree.see(iid)
                break
        self._entry_spoken.delete(0, "end")
        self._entry_corrected.delete(0, "end")
        self._entry_spoken.focus()

    def _delete_row(self):
        sel = self._tree.selection()
        if not sel:
            return
        spoken = self._tree.item(sel[0], "values")[0]
        if messagebox.askyesno("Delete", f"Remove  '{spoken}'?", parent=self):
            self._data.pop(spoken, None)
            self._populate()

    def _on_double_click(self, _=None):
        sel = self._tree.selection()
        if not sel:
            return
        spoken, corrected = self._tree.item(sel[0], "values")
        self._entry_spoken.delete(0, "end")
        self._entry_spoken.insert(0, spoken)
        self._entry_corrected.delete(0, "end")
        self._entry_corrected.insert(0, corrected)
        self._entry_corrected.focus()

    def _save_close(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            self._on_save()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)


# ── Main window ───────────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Pathology Dictation Assistant")
        self.configure(bg=BG)
        self.minsize(720, 580)
        self.geometry("900x720")

        _icon = Path(__file__).parent / "app_icon.ico"
        if _icon.exists():
            try:
                self.iconbitmap(str(_icon))
            except Exception:
                pass

        self.cfg           = PathologyDictationConfig()
        self._ui_q         : queue.Queue = queue.Queue()
        self.is_recording  = False
        self.is_loading    = False
        self.transcriber   : Optional[PathologyTranscriber] = None
        self._recorder     : Optional[AudioRecorder]        = None
        self._corrector    : Optional[TerminologyCorrector] = None
        self._stream_lock  = threading.Lock()
        self._live_text    = ""
        self._cursor_on    = False
        self._rec_t0       = 0.0
        self._font_size    = FONT_SIZE_DEFAULT

        self._style()
        self._build()
        self._populate_mics()
        self._poll()

        self._set_status("Loading model…", AMBER)
        threading.Thread(target=self._load_model, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── ttk style ─────────────────────────────────────────────────────────────

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".",
                     background=BG, foreground=TEXT, font=FONT_UI)
        s.configure("TFrame",       background=BG)
        s.configure("Card.TFrame",  background=BG2,
                     relief="flat", borderwidth=1)
        s.configure("TLabel",       background=BG,  foreground=TEXT)
        s.configure("Card.TLabel",  background=BG2, foreground=TEXT)
        s.configure("Dim.TLabel",   background=BG,  foreground=TEXT_DIM,
                     font=FONT_SMALL)
        s.configure("TLabelframe",  background=BG2, relief="groove",
                     bordercolor=BORDER)
        s.configure("TLabelframe.Label",
                     background=BG2, foreground=ACCENT,
                     font=("Segoe UI", 10, "bold"))
        s.configure("TNotebook",    background=BG,  borderwidth=0)
        s.configure("TNotebook.Tab",
                     background=BG3, foreground=TEXT_DIM,
                     padding=(16, 7), font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", BG2)],
              foreground=[("selected", ACCENT)],
              font=[("selected", ("Segoe UI", 10, "bold"))])
        s.configure("TCombobox",
                     fieldbackground=BG2, background=BG2,
                     foreground=TEXT, selectbackground=ACCENT_L,
                     selectforeground=TEXT, arrowcolor=TEXT_MED,
                     bordercolor=BORDER, lightcolor=BORDER,
                     darkcolor=BORDER)
        s.map("TCombobox",
              fieldbackground=[("readonly", BG2)],
              bordercolor=[("focus", ACCENT)])
        s.configure("TScrollbar",
                     background=BG3, troughcolor=BG3,
                     arrowcolor=TEXT_DIM, borderwidth=0,
                     relief="flat")
        s.map("TScrollbar", background=[("active", BORDER)])

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        # Row 0 = header   (fixed)
        # Row 1 = rec bar  (fixed)
        # Row 2 = notebook (stretches)
        # Row 3 = bottom   (fixed)
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        # ── Header ──
        self._build_header(outer)

        # ── Record bar ──
        self._build_recbar(outer)

        # ── Notebook ──
        self._build_notebook(outer)

        # ── Bottom bar ──
        self._build_bottom(outer)

        self.bind("<F9>",     lambda _: self._toggle_record())
        self.bind("<Escape>", lambda _: self._stop_only() if self.is_recording else None)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self, parent):
        hdr = ttk.Frame(parent)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        hdr.columnconfigure(1, weight=1)

        tk.Label(hdr, text="🔬  Pathology Dictation Assistant",
                 font=FONT_HEAD, bg=BG, fg=ACCENT)\
            .grid(row=0, column=0, sticky="w")
        tk.Label(hdr, text="Local · Offline · Privacy-first · Real-time transcription",
                 font=FONT_SMALL, bg=BG, fg=TEXT_DIM)\
            .grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Config controls (right side)
        cfg = ttk.Frame(hdr)
        cfg.grid(row=0, column=2, rowspan=2, sticky="e")

        tk.Label(cfg, text="Model", font=FONT_SMALL, bg=BG, fg=TEXT_MED)\
            .grid(row=0, column=0, padx=(0, 4), sticky="w")
        self._mdl_var = tk.StringVar(value=self.cfg.transcription.model_size)
        ttk.Combobox(cfg, textvariable=self._mdl_var, width=12, state="readonly",
                     values=["tiny","base","small","medium","large-v2","large-v3"])\
            .grid(row=1, column=0, padx=(0, 16))
        cfg.children[list(cfg.children)[-1]]\
            .bind("<<ComboboxSelected>>", self._on_model_change)

        tk.Label(cfg, text="Microphone", font=FONT_SMALL, bg=BG, fg=TEXT_MED)\
            .grid(row=0, column=1, padx=(0, 4), sticky="w")
        self._mic_var = tk.StringVar()
        self._mic_cb  = ttk.Combobox(cfg, textvariable=self._mic_var,
                                      width=26, state="readonly")
        self._mic_cb.grid(row=1, column=1)
        self._mic_cb.bind("<<ComboboxSelected>>", self._on_mic_change)

        # Thin separator line
        sep = tk.Frame(parent, bg=BORDER, height=1)
        sep.grid(row=0, column=0, sticky="sew", pady=(0, 0))

    # ── Record bar ────────────────────────────────────────────────────────────

    def _build_recbar(self, parent):
        card = tk.Frame(parent, bg=BG2,
                         highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        card.columnconfigure(1, weight=1)

        self._rec_btn = tk.Button(
            card, text="⏺   Start Recording   (F9)",
            font=FONT_BIG, bg=ACCENT, fg="white",
            activebackground=ACCENT_H, activeforeground="white",
            relief="flat", bd=0, padx=28, pady=14, cursor="hand2",
            command=self._toggle_record
        )
        self._rec_btn.grid(row=0, column=0, padx=16, pady=14)

        right = tk.Frame(card, bg=BG2)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=10)
        right.columnconfigure(0, weight=1)

        # Status row
        top_row = tk.Frame(right, bg=BG2)
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.columnconfigure(0, weight=1)

        self._stat_lbl = tk.Label(top_row, text="Initializing…",
                                   font=("Segoe UI", 11, "bold"),
                                   bg=BG2, fg=AMBER, anchor="w")
        self._stat_lbl.grid(row=0, column=0, sticky="w")

        self._time_lbl = tk.Label(top_row, text="",
                                   font=("Segoe UI Semibold", 11),
                                   bg=BG2, fg=TEXT_DIM, anchor="e")
        self._time_lbl.grid(row=0, column=1, sticky="e")

        # VU meter
        self._vu = VUMeter(right)
        self._vu.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        # Hint
        tk.Label(right, text="Press F9 to start · F9 again to stop · Esc to cancel",
                 font=FONT_SMALL, bg=BG2, fg=TEXT_DIM, anchor="w")\
            .grid(row=2, column=0, sticky="w", pady=(4, 0))

    # ── Notebook ──────────────────────────────────────────────────────────────

    def _build_notebook(self, parent):
        wrap = ttk.LabelFrame(parent, text="  Transcription  ", padding=(12, 8))
        wrap.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        self._nb = ttk.Notebook(wrap)
        self._nb.grid(row=0, column=0, sticky="nsew")

        self._live_box = self._textbox(self._nb)
        self._orig_box = self._textbox(self._nb)
        self._corr_box = self._textbox(self._nb)
        self._nb.add(self._live_box, text="  🎙  Live  ")
        self._nb.add(self._orig_box, text="  📄  Original  ")
        self._nb.add(self._corr_box, text="  ✏  Corrected  ")
        self._nb.select(0)

        self._changes_lbl = tk.Label(
            wrap, text="", font=("Segoe UI", 10), bg=BG2,
            fg=TEXT_MED, anchor="w", justify="left", wraplength=820)
        self._changes_lbl.grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _textbox(self, parent) -> scrolledtext.ScrolledText:
        return scrolledtext.ScrolledText(
            parent, wrap="word",
            font=("Segoe UI", self._font_size),
            height=1,
            bg=BG2, fg=TEXT, insertbackground=ACCENT,
            relief="flat", bd=0, padx=14, pady=12,
            selectbackground=ACCENT_L, selectforeground=TEXT,
            state="disabled"
        )

    # ── Bottom bar ────────────────────────────────────────────────────────────

    def _build_bottom(self, parent):
        bar = tk.Frame(parent, bg=BG2,
                        highlightthickness=1, highlightbackground=BORDER)
        bar.grid(row=3, column=0, sticky="ew")
        bar.columnconfigure(98, weight=1)   # spacer

        def btn(col, text, cmd, bg=BG2, fg=TEXT_MED, fg_h="white", bg_h=ACCENT,
                padx=14, bold=False, **kw):
            f = ("Segoe UI", 10, "bold") if bold else ("Segoe UI", 10)
            b = tk.Button(bar, text=text, font=f, bg=bg, fg=fg,
                          activebackground=bg_h, activeforeground=fg_h,
                          relief="flat", bd=0, padx=padx, pady=8,
                          cursor="hand2", command=cmd, **kw)
            b.grid(row=0, column=col, padx=(0, 2), pady=6)
            return b

        btn(0,  "📖  Terminology",    self._open_editor,   fg=ACCENT, bold=True)
        btn(1,  "📋  Copy",           self._copy_result)
        self._save_btn = btn(2, "💾  Save ▼", self._show_save_menu)
        btn(3,  "✕  Clear",           self._clear_all,    fg=TEXT_DIM, padx=10)

        # Thin vertical divider
        tk.Frame(bar, bg=BORDER, width=1).grid(row=0, column=10,
                                                padx=(10, 8), sticky="ns", pady=8)

        # Font size controls
        tk.Label(bar, text="Text size:", font=FONT_SMALL,
                 bg=BG2, fg=TEXT_DIM)\
            .grid(row=0, column=11, padx=(0, 6))
        btn(12, "A−", self._font_down, padx=10)
        self._size_lbl = tk.Label(bar, text=str(self._font_size), width=3,
                                   font=("Segoe UI", 10, "bold"),
                                   bg=BG2, fg=TEXT_MED, anchor="center")
        self._size_lbl.grid(row=0, column=13)
        btn(14, "A+", self._font_up, padx=10)

        # Spacer
        tk.Frame(bar, bg=BG2).grid(row=0, column=98, sticky="ew")

        # Status
        self._foot = tk.Label(bar, text="", font=FONT_SMALL,
                               bg=BG2, fg=TEXT_DIM, anchor="e")
        self._foot.grid(row=0, column=99, padx=(0, 12), sticky="e")

        # Exit
        btn(100, "⏻  Exit", self._on_close, fg=RED_REC,
            bg_h=RED_REC, padx=12)

    # ── Save menu ─────────────────────────────────────────────────────────────

    def _show_save_menu(self):
        menu = tk.Menu(self, tearoff=0,
                       bg=BG2, fg=TEXT,
                       activebackground=ACCENT_L, activeforeground=ACCENT,
                       relief="solid", bd=1, font=FONT_UI)
        menu.add_command(label="  💾  Save as .txt  ",  command=self._save_txt)
        menu.add_command(label="  📄  Save as .docx  ", command=self._save_docx)
        btn = self._save_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() - 60
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ── Mic list ──────────────────────────────────────────────────────────────

    def _populate_mics(self):
        self._mic_map = {}
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0:
                    name = d["name"][:42]
                    self._mic_map[name] = i
            names = list(self._mic_map)
            self._mic_cb["values"] = names
            if names:
                default = sd.default.device
                def_idx = default[0] if isinstance(default, (list, tuple)) else default
                pick = next((n for n, i in self._mic_map.items()
                             if i == def_idx), names[0])
                self._mic_var.set(pick)
                self.cfg.audio.device_index = self._mic_map[pick]
        except Exception as e:
            logger.warning(f"mic list: {e}")

    def _on_mic_change(self, _=None):
        self.cfg.audio.device_index = self._mic_map.get(self._mic_var.get())
        self._recorder = None

    # ── Model ─────────────────────────────────────────────────────────────────

    def _load_model(self):
        self.is_loading = True
        self._btn_enabled(False)
        try:
            size = self._mdl_var.get()
            self.cfg.transcription.model_size  = size
            self.cfg.transcription.device       = "cuda"
            self.cfg.transcription.compute_type = "float16"
            self.transcriber = PathologyTranscriber(
                self.cfg.transcription, self.cfg.models_dir)
            self._corrector  = TerminologyCorrector(
                self.cfg.dictionary, self.cfg.dictionary_path)
            self._ui_q.put(("status", f"Ready  ·  model: {size}", GREEN_OK))
        except Exception as e:
            self._ui_q.put(("status", f"Error: {e}", RED_REC))
            self._ui_q.put(("msgbox", "error", "Model failed",
                             f"Could not load '{self._mdl_var.get()}':\n{e}"))
        finally:
            self.is_loading = False
            self._ui_q.put(("btn", True))

    def _on_model_change(self, _=None):
        if self.is_recording:
            return
        self._set_status("Reloading model…", AMBER)
        self._btn_enabled(False)
        threading.Thread(target=self._load_model, daemon=True).start()

    # ── Terminology ───────────────────────────────────────────────────────────

    def _open_editor(self):
        def _reload():
            if self._corrector:
                self._corrector._load_dictionary()
                n = len(self._corrector.replacements)
                self._set_status(f"Dictionary reloaded  ·  {n} entries", GREEN_OK)
        TerminologyEditor(self, self.cfg.dictionary_path, _reload)

    # ── Font size ─────────────────────────────────────────────────────────────

    def _font_up(self):
        if self._font_size < FONT_SIZE_MAX:
            self._font_size += 1
            self._apply_font()

    def _font_down(self):
        if self._font_size > FONT_SIZE_MIN:
            self._font_size -= 1
            self._apply_font()

    def _apply_font(self):
        self._size_lbl.config(text=str(self._font_size))
        f = ("Segoe UI", self._font_size)
        for box in (self._live_box, self._orig_box, self._corr_box):
            box.config(font=f)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _current_text(self) -> str:
        t = self._corr_box.get("1.0", "end").strip()
        if not t:
            t = self._live_box.get("1.0", "end").strip()
        return t

    def _save_txt(self):
        text = self._current_text()
        if not text:
            messagebox.showwarning("Nothing to save", "Transcribe something first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            title="Save transcription",
            initialfile="transcription.txt"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self._set_status(f"Saved: {Path(path).name}", GREEN_OK)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _save_docx(self):
        text = self._current_text()
        if not text:
            messagebox.showwarning("Nothing to save", "Transcribe something first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx"), ("All files", "*.*")],
            title="Save as Word document",
            initialfile="transcription.docx"
        )
        if not path:
            return
        try:
            import datetime
            from docx import Document
            from docx.shared import Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            doc = Document()
            for sec in doc.sections:
                sec.top_margin = sec.bottom_margin = Pt(72)
                sec.left_margin = sec.right_margin  = Pt(90)

            h = doc.add_heading("Pathology Dictation Report", level=1)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in h.runs:
                run.font.color.rgb = RGBColor(0x1A, 0x5F, 0xB4)

            dp = doc.add_paragraph(
                datetime.datetime.now().strftime("Generated: %d %B %Y  %H:%M"))
            dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in dp.runs:
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0x6B, 0x6D, 0x88)

            doc.add_paragraph()
            for block in text.split("\n\n"):
                block = block.strip()
                if block:
                    p = doc.add_paragraph(block)
                    p.paragraph_format.space_after = Pt(8)
                    for run in p.runs:
                        run.font.size = Pt(12)

            changes_txt = self._changes_lbl.cget("text").strip()
            if changes_txt and "No terminology" not in changes_txt:
                doc.add_paragraph()
                doc.add_heading("Terminology Corrections Applied", level=2)
                for line in changes_txt.replace("Corrections:", "").split("·"):
                    line = line.strip()
                    if line:
                        doc.add_paragraph(line, style="List Bullet")

            doc.save(path)
            self._set_status(f"Saved: {Path(path).name}", GREEN_OK)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    # ── Recording ─────────────────────────────────────────────────────────────

    def _toggle_record(self):
        if self.is_loading:
            return
        if not self.transcriber:
            messagebox.showwarning("Not ready", "Model is still loading.")
            return
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_and_finalize()

    def _start_recording(self):
        self.is_recording = True
        self._live_text   = ""
        self._clear_all()
        self._nb.select(0)

        self._rec_btn.config(
            text="⏹   Stop Recording   (F9)",
            bg=RED_REC, activebackground=RED_H)
        self._set_status("Recording…  speak clearly", RED_REC)
        self._rec_t0 = time.monotonic()

        self._recorder = AudioRecorder(self.cfg.audio, self.cfg.audio_dir)
        self._recorder.start_recording()

        self._tick()
        threading.Thread(target=self._stream_loop, daemon=True).start()

    def _stop_only(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self._rec_btn.config(text="⏺   Start Recording   (F9)",
                              bg=ACCENT, activebackground=ACCENT_H)
        if self._recorder:
            self._recorder.stop_recording()
        self._vu.reset()
        self._set_status("Recording cancelled", TEXT_DIM)
        self._btn_enabled(True)

    def _stop_and_finalize(self):
        self.is_recording = False
        self._vu.reset()
        self._rec_btn.config(text="⏺   Start Recording   (F9)",
                              bg=ACCENT, activebackground=ACCENT_H)
        self._btn_enabled(False)
        self._set_status("Transcribing…  please wait", AMBER)

        audio = self._recorder.stop_recording() if self._recorder else None
        sr    = self.cfg.audio.sample_rate
        threading.Thread(target=self._finalize, args=(audio, sr), daemon=True).start()

    # ── Streaming ─────────────────────────────────────────────────────────────

    def _stream_loop(self):
        sr           = self.cfg.audio.sample_rate
        need_samples = int(STREAM_CHUNK_SEC * sr)
        done_samples = 0
        while self.is_recording:
            time.sleep(0.25)
            recorder = self._recorder
            if not recorder:
                continue
            try:
                buf = list(recorder.audio_buffer)
            except Exception:
                continue
            total = sum(len(c) for c in buf)
            if total - done_samples < need_samples:
                continue
            if not self._stream_lock.acquire(blocking=False):
                continue
            done_samples = total
            try:
                audio = np.concatenate(buf, axis=0).squeeze().astype(np.float32)
                mx = np.abs(audio).max()
                if mx > 0:
                    audio = audio / mx
                segs, _ = self.transcriber.model.transcribe(
                    audio,
                    language=self.cfg.transcription.language,
                    beam_size=STREAM_BEAM, best_of=1,
                    word_timestamps=False, vad_filter=True, temperature=0.0,
                )
                text = " ".join(s.text for s in segs).strip()
                if text:
                    self._live_text = text
                    self._ui_q.put(("live", text))
            except Exception as e:
                logger.debug(f"stream: {e}")
            finally:
                self._stream_lock.release()

    # ── Final pass ────────────────────────────────────────────────────────────

    def _finalize(self, audio, sr):
        try:
            if audio is None or len(audio) == 0:
                self._ui_q.put(("status", "No audio captured — check microphone", RED_REC))
                return
            raw = self.transcriber.transcribe(audio, sr)
            if not raw:
                raw = self._live_text
            if not raw:
                self._ui_q.put(("status", "Nothing detected — please try again", RED_REC))
                return
            corrected, changes = self._corrector.correct_with_logging(raw)
            ClipboardHandler.copy_to_clipboard(corrected)
            self._ui_q.put(("final", raw, corrected, changes))
            n = len(changes)
            self._ui_q.put((
                "status",
                f"Done  ·  {n} correction{'s' if n != 1 else ''} applied  ·  copied to clipboard",
                GREEN_OK))
        except Exception as e:
            logger.error(f"finalize: {e}", exc_info=True)
            self._ui_q.put(("status", f"Error: {e}", RED_REC))
        finally:
            self._ui_q.put(("btn", True))

    # ── Timer / VU ────────────────────────────────────────────────────────────

    def _tick(self):
        if not self.is_recording:
            self._time_lbl.config(text="")
            return
        elapsed = time.monotonic() - self._rec_t0
        self._time_lbl.config(text=f"{elapsed:.1f} s")
        try:
            buf = self._recorder.audio_buffer
            if buf:
                recent = np.concatenate(buf[-4:], axis=0)
                rms = float(np.sqrt(np.mean(recent ** 2)))
                self._vu.update(rms)
        except Exception:
            pass
        self._cursor_on = not self._cursor_on
        cur = "▌" if self._cursor_on else " "
        self._write_live(self._live_text + cur, TEXT_LIVE)
        self.after(200, self._tick)

    # ── Queue poll ────────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                m  = self._ui_q.get_nowait()
                op = m[0]
                if op == "status":
                    self._set_status(m[1], m[2])
                elif op == "btn":
                    self._btn_enabled(m[1])
                elif op == "live":
                    if self.is_recording:
                        cur = "▌" if self._cursor_on else " "
                        self._write_live(m[1] + cur, TEXT_LIVE)
                elif op == "final":
                    _, raw, corrected, changes = m
                    self._write_box(self._live_box, corrected, TEXT)
                    self._write_box(self._orig_box, raw,       TEXT)
                    self._write_box(self._corr_box, corrected, TEXT)
                    self._nb.select(2)
                    if changes:
                        self._changes_lbl.config(
                            text="  Corrections applied:  " +
                                 "   ·   ".join(
                                     f"'{c['original']}' → '{c['replacement']}'"
                                     for c in changes))
                    else:
                        self._changes_lbl.config(
                            text="  No terminology corrections applied.")
                elif op == "msgbox":
                    _, lvl, title, txt = m
                    (messagebox.showerror if lvl == "error"
                     else messagebox.showinfo)(title, txt)
        except queue.Empty:
            pass
        self.after(40, self._poll)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _write_live(self, text: str, color=TEXT_LIVE):
        box = self._live_box
        box.config(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("end", text)
            box.tag_add("c", "1.0", "end")
            box.tag_config("c", foreground=color)
        box.see("end")
        box.config(state="disabled")

    def _write_box(self, box, text: str, color=TEXT):
        box.config(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("end", text)
            box.tag_add("c", "1.0", "end")
            box.tag_config("c", foreground=color)
        box.config(state="disabled")

    def _set_status(self, text: str, color=TEXT_DIM):
        self._stat_lbl.config(text=text, fg=color)
        self._foot.config(text=text, fg=color)

    def _btn_enabled(self, on: bool):
        self._rec_btn.config(state="normal" if on else "disabled",
                              cursor="hand2" if on else "arrow")

    def _copy_result(self):
        text = self._current_text()
        if text:
            ClipboardHandler.copy_to_clipboard(text)
            self._set_status("Copied to clipboard!", GREEN_OK)
        else:
            self._set_status("Nothing to copy yet.", RED_REC)

    def _clear_all(self):
        for box in (self._live_box, self._orig_box, self._corr_box):
            self._write_box(box, "")
        self._changes_lbl.config(text="")
        self._vu.reset()
        self._time_lbl.config(text="")
        self._live_text = ""

    def _on_close(self):
        self.is_recording = False
        if self._recorder and self._recorder.is_recording:
            try:
                self._recorder.stop_recording()
            except Exception:
                pass
        self.destroy()


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    logger.remove()
    logger.add(
        str(Path(__file__).parent / "data" / "gui.log"),
        level="DEBUG", rotation="5 MB", retention="7 days",
        format="{time:HH:mm:ss} | {level} | {message}"
    )
    App().mainloop()


if __name__ == "__main__":
    main()
