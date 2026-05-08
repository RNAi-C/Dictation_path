"""
Pathology Dictation Assistant - GUI
Real-time streaming transcription with live text display.
"""

import sys
import os
import re
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
from rewriter import LocalRewriter, scan_models
from ollama_client import OllamaClient, OllamaError, OllamaConnectionError
from rewrite_service import RewriteService


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


# ── Voice command processor ───────────────────────────────────────────────────

class VoiceCommandProcessor:
    """
    Converts spoken command words/phrases into formatting actions.

    Built-in defaults (always active):
        "enter"          → newline
        "new line"       → newline
        "finish case"    → separator line  (***************)
        "new paragraph"  → blank line

    To add more without editing code:
        Edit  config/voice_commands.json
        Format: { "spoken phrase": "output text" }
        Use \\n for newline inside JSON values.

    Command phrases are matched case-insensitively as whole words.
    Longer phrases are matched first (so "finish case" wins over "finish").
    """

    DEFAULT_COMMANDS: dict[str, str] = {
        "enter":          "\n",
        "new line":       "\n",
        "new paragraph":  "\n\n",
        "finish case":    "\n**************\n",
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.commands    = dict(self.DEFAULT_COMMANDS)
        self.config_path = config_path
        if config_path and config_path.exists():
            self._load(config_path)
        self._pattern = self._compile()

    def reload(self):
        self.commands = dict(self.DEFAULT_COMMANDS)
        if self.config_path and self.config_path.exists():
            self._load(self.config_path)
        self._pattern = self._compile()

    def _load(self, path: Path):
        try:
            with open(path, encoding="utf-8") as f:
                extra = json.load(f)
            # decode \\n in JSON values
            self.commands.update(
                {k: v.replace("\\n", "\n") for k, v in extra.items()}
            )
        except Exception as e:
            logger.warning(f"voice_commands: could not load {path}: {e}")

    def _compile(self):
        phrases = sorted(self.commands.keys(), key=len, reverse=True)
        escaped = [re.escape(p) for p in phrases]
        pat = r'(?<![A-Za-z])(' + '|'.join(escaped) + r')(?![A-Za-z])'
        return re.compile(pat, re.IGNORECASE)

    def process(self, text: str) -> tuple:
        """Return (processed_text, list_of_command_names_applied)."""
        applied: list[str] = []

        def replace(m):
            key = m.group(1).lower()
            applied.append(key)
            return self.commands.get(key, m.group(1))

        result = self._pattern.sub(replace, text)
        return result, applied

    def save(self, path: Path):
        """Save current commands (excluding defaults) to JSON."""
        data = {
            k: v.replace("\n", "\\n")
            for k, v in self.commands.items()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ── Voice command editor ──────────────────────────────────────────────────────

class VoiceCommandEditor(tk.Toplevel):

    def __init__(self, parent, processor: VoiceCommandProcessor, on_save):
        super().__init__(parent)
        self.title("Voice Command Editor")
        self.configure(bg=BG)
        self.geometry("720x520")
        self.minsize(560, 380)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._proc    = processor
        self._on_save = on_save
        self._data    = {}   # spoken → output (with literal \n stored as \\n for display)
        self._load_display_data()
        self._build()
        self._populate()

    def _load_display_data(self):
        """Convert newlines to \\n for display in the table."""
        self._data = {
            k: v.replace("\n", "\\n")
            for k, v in self._proc.commands.items()
        }

    def _build(self):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        tk.Label(root, text="Voice Commands",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ACCENT)\
            .grid(row=0, column=0, sticky="w")
        tk.Label(root,
                 text='Say the command word while dictating — it will be replaced by the output.  '
                      'Use \\n for newline.',
                 font=FONT_SMALL, bg=BG, fg=TEXT_DIM)\
            .grid(row=1, column=0, sticky="w", pady=(2, 10))

        tf = tk.Frame(root, bg=BORDER, bd=1)
        tf.grid(row=2, column=0, sticky="nsew")
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(tf, columns=("spoken", "output"),
                                   show="headings", selectmode="browse")
        self._tree.heading("spoken", text="You say (during dictation)")
        self._tree.heading("output", text="Output / formatting")
        self._tree.column("spoken", width=280, anchor="w", minwidth=160)
        self._tree.column("output", width=340, anchor="w", minwidth=160)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        s = ttk.Style(self)
        s.configure("Cmd.Treeview",
                     background=BG2, foreground=TEXT,
                     fieldbackground=BG2, rowheight=28,
                     font=FONT_UI, borderwidth=0)
        s.configure("Cmd.Treeview.Heading",
                     background=ACCENT_L, foreground=ACCENT,
                     font=("Segoe UI", 10, "bold"), relief="flat", padding=6)
        s.map("Cmd.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "white")])
        self._tree.configure(style="Cmd.Treeview")
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Delete>",   lambda _: self._delete_row())

        add = tk.Frame(root, bg=BG)
        add.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        add.columnconfigure(1, weight=1)
        add.columnconfigure(4, weight=1)

        def lbl(t): return tk.Label(add, text=t, font=FONT_SMALL, bg=BG, fg=TEXT_MED)

        lbl("You say:").grid(row=0, column=0, padx=(0, 6))
        self._e_spoken = tk.Entry(add, bg=BG2, fg=TEXT, insertbackground=TEXT,
                                   relief="solid", bd=1, font=FONT_UI,
                                   highlightthickness=0)
        self._e_spoken.grid(row=0, column=1, sticky="ew", ipady=5)

        tk.Label(add, text="→", font=("Segoe UI", 12, "bold"),
                 bg=BG, fg=ACCENT).grid(row=0, column=2, padx=12)

        lbl("Output:").grid(row=0, column=3, padx=(0, 6))
        self._e_output = tk.Entry(add, bg=BG2, fg=TEXT, insertbackground=TEXT,
                                   relief="solid", bd=1, font=FONT_UI,
                                   highlightthickness=0)
        self._e_output.grid(row=0, column=4, sticky="ew", ipady=5)

        tk.Button(add, text="Add / Update", font=FONT_UI,
                  bg=ACCENT, fg="white", activebackground=ACCENT_H,
                  activeforeground="white", relief="flat", bd=0,
                  padx=14, pady=5, cursor="hand2",
                  command=self._add_or_update)\
            .grid(row=0, column=5, padx=(12, 0))

        self._e_spoken.bind("<Return>", lambda _: self._e_output.focus())
        self._e_output.bind("<Return>", lambda _: self._add_or_update())

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
        for spoken, output in sorted(self._data.items()):
            self._tree.insert("", "end", values=(spoken, output))
        self._count_lbl.config(text=f"{len(self._data)} commands")

    def _add_or_update(self):
        spoken = self._e_spoken.get().strip().lower()
        output = self._e_output.get().strip()
        if not spoken or not output:
            messagebox.showwarning("Empty field", "Both fields are required.", parent=self)
            return
        self._data[spoken] = output
        self._populate()
        self._e_spoken.delete(0, "end")
        self._e_output.delete(0, "end")
        self._e_spoken.focus()

    def _delete_row(self):
        sel = self._tree.selection()
        if not sel:
            return
        spoken = self._tree.item(sel[0], "values")[0]
        if messagebox.askyesno("Delete", f"Remove command  '{spoken}'?", parent=self):
            self._data.pop(spoken, None)
            self._populate()

    def _on_double_click(self, _=None):
        sel = self._tree.selection()
        if not sel:
            return
        spoken, output = self._tree.item(sel[0], "values")
        self._e_spoken.delete(0, "end"); self._e_spoken.insert(0, spoken)
        self._e_output.delete(0, "end"); self._e_output.insert(0, output)
        self._e_output.focus()

    def _save_close(self):
        try:
            # Update processor commands (convert \\n back to real newlines)
            self._proc.commands = {
                k: v.replace("\\n", "\n")
                for k, v in self._data.items()
            }
            self._proc._pattern = self._proc._compile()
            if self._proc.config_path:
                self._proc.save(self._proc.config_path)
            self._on_save()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)


# ── Rewrite preview dialog ────────────────────────────────────────────────────

class RewritePreviewDialog(tk.Toplevel):
    """
    Modal dialog that shows the original selected text alongside the
    AI-rewritten version.  The user may edit the rewritten version before
    accepting.  Pressing Accept calls on_accept(final_text); pressing Reject
    calls on_reject() and leaves the Corrected panel unchanged.
    """

    def __init__(self, parent, original: str, rewritten: str,
                 on_accept, on_reject):
        super().__init__(parent)
        self.title("AI Rewrite Preview")
        self.configure(bg=BG)
        self.geometry("940x540")
        self.minsize(700, 380)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self._on_accept = on_accept
        self._on_reject = on_reject
        self._build(original, rewritten)
        self.focus_set()
        # Keyboard shortcuts inside dialog
        self.bind("<Return>",  lambda _: None)          # prevent accidental close
        self.bind("<Escape>",  lambda _: self._reject())

    def _build(self, original: str, rewritten: str):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        # ── Title ──
        hdr = tk.Frame(root, bg=BG)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Label(hdr, text="AI Rewrite Preview",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ACCENT)\
            .pack(side="left")
        tk.Label(hdr,
                 text="  You may edit the rewritten text before accepting.",
                 font=FONT_SMALL, bg=BG, fg=TEXT_DIM)\
            .pack(side="left", padx=(8, 0))

        # ── Left pane: original (readonly) ──
        lf = tk.Frame(root, bg=BG)
        lf.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(1, weight=1)

        tk.Label(lf, text="Original selected text",
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=TEXT_MED)\
            .grid(row=0, column=0, sticky="w", pady=(0, 4))

        orig_box = scrolledtext.ScrolledText(
            lf, wrap="word", font=FONT_MONO,
            bg="#FFF9F0", fg=TEXT,
            relief="solid", bd=1, highlightthickness=0,
            padx=10, pady=8, state="normal")
        orig_box.grid(row=1, column=0, sticky="nsew")
        orig_box.insert("1.0", original)
        orig_box.config(state="disabled")

        # ── Right pane: rewritten (editable) ──
        rf = tk.Frame(root, bg=BG)
        rf.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(1, weight=1)

        tk.Label(rf, text="Rewritten text",
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=ACCENT)\
            .grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._rewr_edit = scrolledtext.ScrolledText(
            rf, wrap="word", font=FONT_MONO,
            bg="#F0FFF4", fg=TEXT, insertbackground=ACCENT,
            relief="solid", bd=1, highlightthickness=0,
            padx=10, pady=8, undo=True, state="normal")
        self._rewr_edit.grid(row=1, column=0, sticky="nsew")
        self._rewr_edit.insert("1.0", rewritten)
        self._rewr_edit.focus_set()

        # ── Divider ──
        tk.Frame(root, bg=BORDER, height=1)\
            .grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 8))

        # ── Buttons ──
        btns = tk.Frame(root, bg=BG)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew")

        tk.Button(btns, text="✓  Accept Rewrite", font=FONT_UI,
                  bg=GREEN_OK, fg="white", activebackground="#155f39",
                  activeforeground="white", relief="flat", bd=0,
                  padx=20, pady=8, cursor="hand2",
                  command=self._accept)\
            .pack(side="left")

        tk.Button(btns, text="✗  Reject — Keep Original", font=FONT_UI,
                  bg=RED_SOFT, fg=RED_REC, activebackground="#fcd5d0",
                  activeforeground=RED_REC, relief="flat", bd=0,
                  padx=20, pady=8, cursor="hand2",
                  command=self._reject)\
            .pack(side="left", padx=(8, 0))

        tk.Label(btns, text="Esc = reject",
                 font=FONT_SMALL, bg=BG, fg=TEXT_DIM)\
            .pack(side="right", padx=(0, 4))

    def _accept(self):
        final = self._rewr_edit.get("1.0", "end-1c")
        self._on_accept(final)
        self.destroy()

    def _reject(self):
        self._on_reject()
        self.destroy()


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

        # Voice commands processor
        _vc_path = Path(__file__).parent / "config" / "voice_commands.json"
        self._voice_cmd = VoiceCommandProcessor(config_path=_vc_path)

        # GGUF rewriter (lazy-loaded when first used — whole-text rewrite)
        self._rewriter: Optional[LocalRewriter] = None

        # Ollama rewrite service (selected-text rewrite)
        self._rewrite_svc: Optional[RewriteService] = None
        self._init_ollama()

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

        self.bind("<F9>",               lambda _: self._toggle_record())
        self.bind("<Escape>",           lambda _: self._stop_only() if self.is_recording else None)
        self.bind("<Control-Shift-R>",  lambda _: self._rewrite_selected())
        self.bind("<Control-Shift-r>",  lambda _: self._rewrite_selected())

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

        # Live tab — readonly streaming preview
        self._live_box = self._textbox(self._nb)
        self._nb.add(self._live_box, text="  🎙  Live  ")

        # Corrected tab — editable by user
        self._corr_box = self._editable_textbox(self._nb)
        self._nb.add(self._corr_box, text="  ✏  Corrected  ")

        # Rewritten tab — readonly AI output
        self._rewr_box = self._textbox(self._nb)
        self._nb.add(self._rewr_box, text="  ✨  Rewritten  ")

        self._nb.select(0)

        # Bind Ctrl+Y for Redo on the editable corrected box
        self._corr_box.bind("<Control-y>", lambda e: self._redo() or "break")
        self._corr_box.bind("<Control-Y>", lambda e: self._redo() or "break")

        # Edit toolbar (undo / redo / rewrite selected) — row 1
        self._build_edit_toolbar(wrap)

        # Changes / corrections summary — row 2
        self._changes_lbl = tk.Label(
            wrap, text="", font=("Segoe UI", 10), bg=BG2,
            fg=TEXT_MED, anchor="w", justify="left", wraplength=820)
        self._changes_lbl.grid(row=2, column=0, sticky="w", pady=(4, 0))

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

    def _editable_textbox(self, parent) -> scrolledtext.ScrolledText:
        """Textbox that stays editable — undo/redo enabled, user can type freely."""
        return scrolledtext.ScrolledText(
            parent, wrap="word",
            font=("Segoe UI", self._font_size),
            height=1,
            bg="#F7FFFE", fg=TEXT, insertbackground=ACCENT,
            relief="flat", bd=0, padx=14, pady=12,
            selectbackground=ACCENT_L, selectforeground=TEXT,
            undo=True, maxundo=200,
            state="normal"
        )

    def _build_edit_toolbar(self, parent):
        """
        Compact toolbar below the notebook tabs.
        Contains: Undo · Redo | Rewrite Selected Text
        This toolbar only operates on the Corrected (editable) panel.
        """
        bar = tk.Frame(parent, bg=BG2)
        bar.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        def tbtn(text, cmd, fg=TEXT_MED, **kw):
            b = tk.Button(bar, text=text, font=("Segoe UI", 9),
                          bg=BG2, fg=fg,
                          activebackground=ACCENT_L, activeforeground=ACCENT,
                          relief="flat", bd=0, padx=10, pady=4,
                          cursor="hand2", command=cmd, **kw)
            b.pack(side="left", padx=(0, 2))
            return b

        tbtn("↩  Undo  Ctrl+Z", self._undo)
        tbtn("↪  Redo  Ctrl+Y", self._redo)

        tk.Frame(bar, bg=BORDER, width=1)\
            .pack(side="left", fill="y", padx=(8, 8), pady=3)

        self._rewrite_sel_btn = tbtn(
            "✏  Rewrite Selected Text   Ctrl+Shift+R",
            self._rewrite_selected, fg=ACCENT,
            state="disabled")   # enabled once Ollama startup check passes

        # Right-side hint
        tk.Label(bar,
                 text="✎ Corrected tab is editable — type freely or rewrite selection with AI",
                 font=("Segoe UI", 9), bg=BG2, fg=TEXT_DIM)\
            .pack(side="right", padx=(0, 6))

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

        btn(0,  "📖  Terminology",    self._open_editor,       fg=ACCENT, bold=True)
        btn(1,  "🎙  Voice Cmds",    self._open_voice_editor, fg=ACCENT)
        btn(2,  "📋  Copy",           self._copy_result)
        self._save_btn = btn(3, "💾  Save ▼", self._show_save_menu)
        btn(4,  "✕  Clear",           self._clear_all,        fg=TEXT_DIM, padx=10)

        # Thin vertical divider
        tk.Frame(bar, bg=BORDER, width=1).grid(row=0, column=5,
                                                padx=(8, 8), sticky="ns", pady=8)

        # AI rewrite controls
        tk.Label(bar, text="AI:", font=FONT_SMALL,
                 bg=BG2, fg=TEXT_DIM)\
            .grid(row=0, column=6, padx=(0, 4))
        self._rewr_model_var = tk.StringVar()
        self._rewr_model_cb  = ttk.Combobox(
            bar, textvariable=self._rewr_model_var,
            width=22, state="readonly")
        self._rewr_model_cb.grid(row=0, column=7, padx=(0, 4), pady=6)
        self._rewrite_btn = btn(8, "✨  Rewrite", self._rewrite, fg=ACCENT)

        # Refresh model list button
        btn(9, "↺", self._populate_rewrite_models, fg=TEXT_DIM, padx=6)

        # Thin vertical divider (2nd)
        tk.Frame(bar, bg=BORDER, width=1).grid(row=0, column=11,
                                                padx=(10, 8), sticky="ns", pady=8)

        # Font size controls
        tk.Label(bar, text="Text size:", font=FONT_SMALL,
                 bg=BG2, fg=TEXT_DIM)\
            .grid(row=0, column=12, padx=(0, 6))
        btn(13, "A−", self._font_down, padx=10)
        self._size_lbl = tk.Label(bar, text=str(self._font_size), width=3,
                                   font=("Segoe UI", 10, "bold"),
                                   bg=BG2, fg=TEXT_MED, anchor="center")
        self._size_lbl.grid(row=0, column=14)
        btn(15, "A+", self._font_up, padx=10)

        # Populate rewrite model list now that widgets exist
        self._populate_rewrite_models()

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

    def _open_voice_editor(self):
        def _reload():
            n = len(self._voice_cmd.commands)
            self._set_status(f"Voice commands saved  ·  {n} commands active", GREEN_OK)
        VoiceCommandEditor(self, self._voice_cmd, _reload)

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def _undo(self):
        """Undo the last edit in the Corrected text panel."""
        try:
            self._corr_box.edit_undo()
        except tk.TclError:
            pass   # Nothing to undo

    def _redo(self):
        """Redo the last undone edit in the Corrected text panel."""
        try:
            self._corr_box.edit_redo()
        except tk.TclError:
            pass   # Nothing to redo

    # ── Ollama rewrite selected text ──────────────────────────────────────────

    def _init_ollama(self):
        """
        Initialise the Ollama rewrite service (no network call here).
        Launches a background thread to check / auto-start Ollama and
        update the rewrite button state once the result is known.
        """
        cfg = self.cfg.llm
        if not cfg.enabled:
            logger.info("LLM rewrite disabled in config")
            return
        try:
            client = OllamaClient(
                endpoint = cfg.endpoint,
                model    = cfg.model,
                timeout  = cfg.timeout_seconds,
            )
            self._rewrite_svc = RewriteService(
                client      = client,
                temperature = cfg.temperature,
                max_tokens  = cfg.max_tokens,
            )
            logger.info(f"Ollama service object created: {cfg.model} @ {cfg.endpoint}")
        except Exception as e:
            logger.warning(f"Could not create Ollama service: {e}")
            self._rewrite_svc = None
            return

        # Run startup check in background — does not block the GUI
        threading.Thread(
            target = self._check_ollama_startup,
            daemon = True,
            name   = "ollama-startup",
        ).start()

    def _check_ollama_startup(self):
        """
        Background thread: check whether Ollama is running; auto-start if not.
        Posts all results to _ui_q — never touches widgets directly.

        Queue messages posted:
          ("ollama_foot",   text, color)     — update footer label only
          ("ollama_status", state, detail)   — final result:
              state = "ready"       detail = model name
              state = "no_model"    detail = model name
              state = "unavailable" detail = human-readable reason
        """
        cfg    = self.cfg.llm
        client = self._rewrite_svc.client   # never None at this point

        self._ui_q.put(("ollama_foot", "Ollama: checking…", TEXT_DIM))

        # ── Step 1: Already running? ──────────────────────────────────────────
        if client.is_ollama_running():
            logger.info("Ollama already running")
            self._finish_ollama_check(client, cfg)
            return

        # ── Step 2: Auto-start ────────────────────────────────────────────────
        if not cfg.auto_start_ollama:
            msg = (
                "Ollama is not running.  Dictation still works, but "
                "Qwen rewrite is unavailable.\n\n"
                "Start Ollama manually:\n  ollama serve"
            )
            self._ui_q.put(("ollama_status", "unavailable", msg))
            return

        self._ui_q.put(("ollama_foot", "Ollama: starting…", AMBER))
        logger.info("Ollama not detected — attempting auto-start")

        launched = client.start_ollama(cfg.ollama_start_command)
        if not launched:
            msg = (
                "Could not start Ollama automatically.\n\n"
                "Dictation still works, but Qwen rewrite is unavailable.\n\n"
                "Install Ollama from https://ollama.ai\n"
                "then start it with:  ollama serve"
            )
            self._ui_q.put(("ollama_status", "unavailable", msg))
            return

        # ── Step 3: Wait until ready ──────────────────────────────────────────
        self._ui_q.put(("ollama_foot",
                         f"Ollama: waiting (up to {cfg.startup_wait_seconds} s)…",
                         AMBER))
        ready = client.wait_until_ready(
            timeout  = cfg.startup_wait_seconds,
            interval = cfg.startup_retry_interval_seconds,
        )
        if not ready:
            msg = (
                f"Ollama was started but did not respond within "
                f"{cfg.startup_wait_seconds} s.\n\n"
                "Dictation still works, but Qwen rewrite is unavailable.\n\n"
                "Try starting Ollama manually:\n  ollama serve"
            )
            self._ui_q.put(("ollama_status", "unavailable", msg))
            return

        logger.info("Ollama became ready after auto-start")
        self._finish_ollama_check(client, cfg)

    def _finish_ollama_check(self, client, cfg):
        """Called (from background thread) when Ollama is confirmed running."""
        ok, msg = client.check_status()
        if ok:
            logger.info(f"Ollama model ready: {cfg.model}")
            self._ui_q.put(("ollama_status", "ready", cfg.model))
        else:
            logger.warning(f"Ollama running but model unavailable: {msg}")
            self._ui_q.put(("ollama_status", "no_model", cfg.model))

    def _rewrite_selected(self):
        """
        Rewrite the text currently selected in the Corrected panel using Ollama.
        If no text is selected, show a friendly prompt.
        Runs the Ollama call in a background thread; shows a preview dialog on
        completion.  The Corrected panel is locked during the request to preserve
        selection indices.
        """
        # Must be on Corrected tab (index 1) for selection to make sense
        # — but we allow the call from any tab; just need text selected.
        try:
            sel_start = self._corr_box.index(tk.SEL_FIRST)
            sel_end   = self._corr_box.index(tk.SEL_LAST)
            sel_text  = self._corr_box.get(sel_start, sel_end)
        except tk.TclError:
            messagebox.showinfo(
                "No text selected",
                "Please select text in the Corrected panel to rewrite.",
                parent=self)
            return

        if not sel_text.strip():
            messagebox.showinfo(
                "Empty selection",
                "The selected text is empty.  Please select some text.",
                parent=self)
            return

        if self._rewrite_svc is None:
            messagebox.showerror(
                "Ollama not available",
                "The Ollama rewrite service could not be initialised.\n\n"
                "To use AI rewrite:\n"
                "  1. Install Ollama:  https://ollama.ai\n"
                f"  2. Pull model:      ollama pull {self.cfg.llm.model}\n"
                "  3. Start server:    ollama serve\n"
                "  4. Restart this app\n\n"
                f"Configured endpoint: {self.cfg.llm.endpoint}\n"
                f"Configured model:    {self.cfg.llm.model}",
                parent=self)
            return

        # Lock the corrected box so indices stay valid during the request
        self._corr_box.config(state="disabled")
        self._rewrite_sel_btn.config(state="disabled")
        self._nb.select(1)   # Make Corrected tab visible
        self._set_status(
            f"Rewriting selection with {self.cfg.llm.model}…  "
            f"(may take up to {self.cfg.llm.timeout_seconds} s)", AMBER)

        threading.Thread(
            target = self._rewrite_selected_bg,
            args   = (sel_text, sel_start, sel_end),
            daemon = True,
        ).start()

    def _rewrite_selected_bg(self, sel_text: str,
                              sel_start: str, sel_end: str):
        """Background worker: call Ollama then post result to the UI queue."""
        try:
            result = self._rewrite_svc.rewrite(sel_text)
            self._ui_q.put(("rewrite_sel_done",
                             sel_text, result, sel_start, sel_end))
        except OllamaConnectionError as exc:
            self._ui_q.put(("rewrite_sel_error", str(exc)))
        except OllamaError as exc:
            self._ui_q.put(("rewrite_sel_error", str(exc)))
        except Exception as exc:
            logger.error(f"_rewrite_selected_bg: {exc}", exc_info=True)
            self._ui_q.put(("rewrite_sel_error",
                             f"Unexpected error: {exc}"))
        finally:
            # Always re-enable the button (text box re-enabled in _poll)
            self._ui_q.put(("rewrite_sel_enable", None))

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
        for box in (self._live_box, self._corr_box, self._rewr_box):
            box.config(font=f)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _current_text(self) -> str:
        """Return best available text: rewritten > corrected > live."""
        t = self._rewr_box.get("1.0", "end").strip()
        if not t:
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
        # Clear only the live preview box; orig/corr boxes persist until Clear is pressed
        self._write_box(self._live_box, "")
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
                    live_text, _ = self._voice_cmd.process(text)
                    self._live_text = live_text
                    self._ui_q.put(("live", live_text))
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
            # Apply voice commands first, then terminology correction
            raw_after_vc, vc_applied = self._voice_cmd.process(raw)
            corrected, changes = self._corrector.correct_with_logging(raw_after_vc)
            ClipboardHandler.copy_to_clipboard(corrected)
            self._ui_q.put(("final", raw, corrected, changes, vc_applied))
            n = len(changes)
            v = len(vc_applied)
            status_parts = [f"Done  ·  {n} correction{'s' if n!=1 else ''} applied"]
            if v:
                status_parts.append(f"{v} voice command{'s' if v!=1 else ''}")
            status_parts.append("copied to clipboard")
            self._ui_q.put(("status", "  ·  ".join(status_parts), GREEN_OK))
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
                    _, raw, corrected, changes, vc_applied = m
                    self._write_box(self._live_box, corrected, TEXT)
                    self._append_box(self._corr_box, corrected, TEXT, stay_enabled=True)
                    self._nb.select(1)   # Switch to Corrected tab
                    parts = []
                    if vc_applied:
                        parts.append("  Voice cmds: " +
                                     ", ".join(f"[{c}]" for c in vc_applied))
                    if changes:
                        parts.append("  Corrections: " +
                                     "   ·   ".join(
                                         f"'{c['original']}' → '{c['replacement']}'"
                                         for c in changes))
                    if parts:
                        self._changes_lbl.config(text="   ".join(parts))
                    else:
                        self._changes_lbl.config(
                            text="  No voice commands or terminology corrections applied.")
                elif op == "rewrite_done":
                    self._append_box(self._rewr_box, m[1], TEXT)
                    self._nb.select(2)   # Switch to Rewritten tab
                elif op == "rewrite_btn_enable":
                    self._rewrite_btn.config(state="normal")
                elif op == "rewrite_sel_done":
                    # m = ("rewrite_sel_done", original, rewritten, sel_start, sel_end)
                    _, original, rewritten, sel_start, sel_end = m
                    # Unlock the corrected box before showing the dialog
                    self._corr_box.config(state="normal")
                    self._set_status("Rewrite ready — review in preview dialog",
                                     GREEN_OK)
                    def _on_accept(final_text,
                                   _ss=sel_start, _se=sel_end):
                        # Replace only the originally selected span
                        self._corr_box.delete(_ss, _se)
                        self._corr_box.insert(_ss, final_text)
                        self._corr_box.edit_separator()   # single undo step
                        self._set_status("Rewrite accepted", GREEN_OK)
                    def _on_reject():
                        self._set_status(
                            "Rewrite rejected — original text kept", TEXT_DIM)
                    RewritePreviewDialog(
                        self, original, rewritten, _on_accept, _on_reject)
                elif op == "rewrite_sel_error":
                    _, msg = m
                    self._corr_box.config(state="normal")
                    self._set_status(f"Rewrite error — see dialog", RED_REC)
                    messagebox.showerror("Rewrite failed", msg, parent=self)
                elif op == "rewrite_sel_enable":
                    self._rewrite_sel_btn.config(state="normal")
                elif op == "ollama_foot":
                    # Update footer label only — does not overwrite main status
                    _, text, color = m
                    self._foot.config(text=text, fg=color)
                elif op == "ollama_status":
                    # Final result of the Ollama startup check
                    _, state, detail = m
                    if state == "ready":
                        self._rewrite_sel_btn.config(state="normal")
                        self._foot.config(
                            text=f"Ollama: {detail}  ✓", fg=GREEN_OK)
                    elif state == "no_model":
                        # Ollama is running but model not pulled
                        self._rewrite_sel_btn.config(state="disabled")
                        self._foot.config(
                            text=f"Ollama: '{detail}' not installed — run: "
                                 f"ollama pull {detail}",
                            fg=AMBER)
                        messagebox.showwarning(
                            "Qwen model not installed",
                            f"Ollama is running, but '{detail}' is not installed.\n\n"
                            f"Pull it with:\n  ollama pull {detail}\n\n"
                            "Dictation works normally.\n"
                            "The Rewrite feature will be unavailable until the "
                            "model is installed.",
                            parent=self)
                    elif state == "unavailable":
                        # Not running and could not be started
                        self._rewrite_sel_btn.config(state="disabled")
                        self._foot.config(
                            text="Ollama unavailable — rewrite disabled  "
                                 "(dictation works normally)",
                            fg=AMBER)
                        logger.info(f"Ollama unavailable at startup: {detail}")
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

    def _write_box(self, box, text: str, color=TEXT, stay_enabled=False):
        box.config(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("end", text)
            box.tag_add("c", "1.0", "end")
            box.tag_config("c", foreground=color)
        if not stay_enabled:
            box.config(state="disabled")

    def _append_box(self, box, text: str, color=TEXT, stay_enabled=False):
        """Append text to box, adding a separator if content already exists."""
        box.config(state="normal")
        existing = box.get("1.0", "end").strip()
        if existing:
            sep_idx = box.index("end-1c")
            box.insert("end", "\n\n― ― ―\n\n")   # ― ― ―
            box.tag_add("sep", sep_idx, box.index("end"))
            box.tag_config("sep", foreground=TEXT_DIM)
        if text:
            start_idx = box.index("end-1c")
            box.insert("end", text)
            box.tag_add("new", start_idx, box.index("end"))
            box.tag_config("new", foreground=color)
        box.see("end")
        if not stay_enabled:
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
        # Readonly boxes
        for box in (self._live_box, self._rewr_box):
            self._write_box(box, "")
        # Editable corrected box — stays enabled
        self._corr_box.delete("1.0", "end")
        self._changes_lbl.config(text="")
        self._vu.reset()
        self._time_lbl.config(text="")
        self._live_text = ""

    # ── AI rewrite ────────────────────────────────────────────────────────────

    def _populate_rewrite_models(self):
        """Scan models/rewrite/ for .gguf files and populate the combobox."""
        try:
            models = scan_models(self.cfg.models_dir)
        except Exception:
            models = []
        if models:
            names = [m.name for m in models]
            self._rewr_model_cb.configure(values=names)
            # Keep current selection if still valid, else pick first
            if self._rewr_model_var.get() not in names:
                self._rewr_model_var.set(names[0])
            self._rewrite_btn.config(state="normal")
        else:
            self._rewr_model_cb.configure(values=["No models found"])
            self._rewr_model_var.set("No models found")
            self._rewrite_btn.config(state="disabled")

    def _rewrite(self):
        """Start AI rewrite of the Corrected text in a background thread."""
        text = self._corr_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(
                "Nothing to rewrite",
                "Dictate and correct something first.",
                parent=self)
            return

        model_name = self._rewr_model_var.get()
        if not model_name or model_name == "No models found":
            messagebox.showinfo(
                "No rewrite model found",
                "Place a .gguf model file in:\n"
                f"  {self.cfg.models_dir / 'rewrite'}\n\n"
                "Supported models (Q4_K_M GGUF format):\n"
                "  • Qwen2.5-1.5B-Instruct-Q4_K_M.gguf  (~0.9 GB)\n"
                "  • Qwen2.5-3B-Instruct-Q4_K_M.gguf    (~1.8 GB)\n"
                "  • Phi-3.5-mini-instruct-Q4_K_M.gguf  (~2.2 GB)\n"
                "  • Llama-3.2-1B-Instruct-Q4_K_M.gguf  (~0.7 GB)\n\n"
                "Download from HuggingFace — see README.",
                parent=self)
            return

        # Check llama-cpp-python is available before launching thread
        avail, msg = LocalRewriter.check_available()
        if not avail:
            messagebox.showerror("llama-cpp-python not installed", msg, parent=self)
            return

        model_path = self.cfg.models_dir / "rewrite" / model_name
        self._rewrite_btn.config(state="disabled")
        self._set_status(
            f"Loading  {model_name}…  (first run may take 10–30 s)", AMBER)
        threading.Thread(
            target=self._rewrite_bg, args=(text, model_path), daemon=True
        ).start()

    def _rewrite_bg(self, text: str, model_path: Path):
        """Background worker: load GGUF model if needed, then rewrite."""
        try:
            # Load or swap model (unload old if different)
            if self._rewriter is None or self._rewriter.model_path != model_path:
                if self._rewriter and self._rewriter.is_loaded():
                    self._rewriter.unload()
                self._rewriter = LocalRewriter(model_path)
                self._rewriter.load()

            self._ui_q.put(("status", "Rewriting text…", AMBER))
            result = self._rewriter.rewrite(text)
            self._ui_q.put(("rewrite_done", result))
            self._ui_q.put(("status",
                             "Rewrite complete  ·  see  ✨ Rewritten  tab", GREEN_OK))
        except Exception as e:
            logger.error(f"rewrite_bg: {e}", exc_info=True)
            self._ui_q.put(("status", f"Rewrite error: {e}", RED_REC))
            self._ui_q.put(("msgbox", "error", "Rewrite failed", str(e)))
        finally:
            self._ui_q.put(("rewrite_btn_enable", True))

    def _on_close(self):
        self.is_recording = False
        if self._recorder and self._recorder.is_recording:
            try:
                self._recorder.stop_recording()
            except Exception:
                pass
        if self._rewriter and self._rewriter.is_loaded():
            try:
                self._rewriter.unload()
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
