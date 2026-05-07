import sys, os, traceback
os.chdir(r"G:\Dictation_Path")
sys.path.insert(0, r"G:\Dictation_Path")
try:
    import gui_app
    gui_app.main()
except Exception:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("Launch error", traceback.format_exc())
    root.destroy()
