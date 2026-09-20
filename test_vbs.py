import os, time, subprocess
import pygetwindow

os.startfile('notepad.exe')
time.sleep(1)

win = [w for w in pygetwindow.getAllWindows() if 'notepad' in w.title.lower()][0]
title = win.title

vbs = f'''
Set objShell = WScript.CreateObject("WScript.Shell")
objShell.AppActivate "{title}"
'''
with open('test.vbs', 'w') as f:
    f.write(vbs)

import ctypes
hwnd = win._hWnd
user32 = ctypes.windll.user32
print('Before:', user32.GetForegroundWindow() == hwnd)
subprocess.run(['cscript', '//nologo', 'test.vbs'])
time.sleep(0.5)
print('After VBScript:', user32.GetForegroundWindow() == hwnd)
