import sys, os, traceback
_here = os.path.dirname(os.path.abspath(__file__))
os.chdir(_here)
sys.path.insert(0, _here)
try:
    import gui_app
    gui_app.main()
except Exception:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("Launch error", traceback.format_exc())
    root.destroy()
