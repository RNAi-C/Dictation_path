"""
Creates the Miku-themed app icon (.ico) and a Windows Desktop shortcut.
Run once: venv\Scripts\python.exe create_shortcut.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR   = Path(__file__).parent.resolve()
ICON_PATH     = PROJECT_DIR / "app_icon.ico"
LAUNCHER_PATH = PROJECT_DIR / "launcher.pyw"
PYW_EXE       = PROJECT_DIR / "venv" / "Scripts" / "pythonw.exe"
SHORTCUT_NAME = "Pathology Dictation.lnk"


# ── 1. Generate Miku-themed icon ──────────────────────────────────────────────

def make_icon():
    from PIL import Image, ImageDraw

    # Miku brand colours
    TEAL   = (0,   154, 180, 255)   # #009AB4
    PINK   = (227,   0, 127, 255)   # #E3007F
    WHITE  = (255, 255, 255, 255)
    DARK   = ( 10,  30,  40, 255)
    TEAL_D = (  0,  90, 110, 255)   # darker teal for depth

    sizes  = [256, 128, 64, 48, 32, 16]
    frames = []

    for size in sizes:
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        s    = size
        m    = s / 256

        def sc(v): return max(1, int(v * m))

        # ── Background circle (dark teal) ──
        pad = sc(4)
        draw.ellipse([pad, pad, s - pad, s - pad], fill=DARK)

        # ── Teal ring ──
        ring = sc(10)
        draw.ellipse([pad, pad, s - pad, s - pad],
                     outline=TEAL, width=ring)

        # ── Pink inner ring ──
        p2 = pad + ring + sc(3)
        draw.ellipse([p2, p2, s - p2, s - p2],
                     outline=PINK, width=sc(4))

        cx, cy = s // 2, s // 2

        # ── Musical note ──
        # Stem
        stem_x  = cx + sc(18)
        stem_y1 = cy - sc(52)
        stem_y2 = cy + sc(10)
        stem_w  = sc(10)
        draw.rectangle([stem_x - stem_w // 2, stem_y1,
                        stem_x + stem_w // 2, stem_y2],
                       fill=TEAL)

        # Note head (filled ellipse)
        nh_rx, nh_ry = sc(22), sc(16)
        nh_cx = stem_x - sc(14)
        nh_cy = stem_y2 + sc(4)
        draw.ellipse([nh_cx - nh_rx, nh_cy - nh_ry,
                      nh_cx + nh_rx, nh_cy + nh_ry],
                     fill=TEAL)

        # Second note stem (eighth note pair)
        stem2_x  = stem_x - sc(38)
        stem2_y1 = cy - sc(32)
        stem2_y2 = cy + sc(30)
        draw.rectangle([stem2_x - stem_w // 2, stem2_y1,
                        stem2_x + stem_w // 2, stem2_y2],
                       fill=PINK)

        # Second note head
        nh2_cx = stem2_x - sc(14)
        nh2_cy = stem2_y2 + sc(4)
        draw.ellipse([nh2_cx - nh_rx, nh2_cy - nh_ry,
                      nh2_cx + nh_rx, nh2_cy + nh_ry],
                     fill=PINK)

        # Beam connecting both stems (at top)
        beam_y  = stem_y1
        beam_h  = sc(8)
        draw.rectangle([stem2_x, beam_y,
                        stem_x, beam_y + beam_h],
                       fill=WHITE)

        # ── Highlight dot ──
        hl_r = sc(12)
        draw.ellipse([pad + sc(16), pad + sc(16),
                      pad + sc(16) + hl_r, pad + sc(16) + hl_r],
                     fill=(255, 255, 255, 60))

        frames.append(img)

    frames[0].save(
        str(ICON_PATH),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:]
    )
    print(f"Icon created: {ICON_PATH}")


# ── 2. Create launcher.pyw ────────────────────────────────────────────────────

def make_launcher():
    """
    A tiny wrapper that ensures the working directory is correct
    and shows a popup if something goes wrong — so double-click always works.
    """
    code = f'''\
import sys, os, traceback
os.chdir(r"{PROJECT_DIR}")
sys.path.insert(0, r"{PROJECT_DIR}")
try:
    import gui_app
    gui_app.main()
except Exception:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("Launch error", traceback.format_exc())
    root.destroy()
'''
    LAUNCHER_PATH.write_text(code, encoding="utf-8")
    print(f"Launcher created: {LAUNCHER_PATH}")


# ── 3. Create Desktop shortcut ────────────────────────────────────────────────

def make_shortcut():
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home() / "OneDrive" / "Desktop"
    if not desktop.exists():
        desktop = PROJECT_DIR

    shortcut_path = desktop / SHORTCUT_NAME

    # Build VBScript — avoid triple-quote issues by concatenating
    lines = [
        'Set oWS = WScript.CreateObject("WScript.Shell")',
        f'Set oLink = oWS.CreateShortcut("{shortcut_path}")',
        f'oLink.TargetPath = "{PYW_EXE}"',
        f'oLink.Arguments = Chr(34) & "{LAUNCHER_PATH}" & Chr(34)',
        f'oLink.WorkingDirectory = "{PROJECT_DIR}"',
        f'oLink.IconLocation = "{ICON_PATH}"',
        'oLink.Description = "Pathology Dictation Assistant"',
        'oLink.Save',
    ]
    vbs_path = PROJECT_DIR / "_tmp.vbs"
    vbs_path.write_text("\n".join(lines), encoding="utf-8")

    result = subprocess.run(
        ["cscript", "//NoLogo", str(vbs_path)],
        capture_output=True, text=True
    )
    vbs_path.unlink(missing_ok=True)

    if result.returncode == 0:
        print(f"Shortcut placed on Desktop: {shortcut_path}")
    else:
        # Fallback: .bat in project folder
        bat = PROJECT_DIR / "Pathology Dictation.bat"
        bat.write_text(
            f'@echo off\ncd /d "{PROJECT_DIR}"\n'
            f'start "" "{PYW_EXE}" "{LAUNCHER_PATH}"\n',
            encoding="utf-8"
        )
        print(f"(VBS failed — .bat fallback created: {bat})")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Setting up Pathology Dictation shortcut...")
    make_icon()
    make_launcher()
    make_shortcut()
    print("\nAll done!")
    print("Double-click 'Pathology Dictation' on your Desktop to launch.")
    try:
        input("Press Enter to close...")
    except EOFError:
        pass
