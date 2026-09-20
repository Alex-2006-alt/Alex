import os, time, ctypes
import pygetwindow

os.startfile('notepad.exe')
time.sleep(1)

win = [w for w in pygetwindow.getAllWindows() if 'notepad' in w.title.lower()][0]
hwnd = win._hWnd
user32 = ctypes.windll.user32

SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 2 | 1

timeout = ctypes.c_uint(0)
user32.SystemParametersInfoW(SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout), 0)
user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE)

user32.BringWindowToTop(hwnd)
user32.SetForegroundWindow(hwnd)

user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, timeout, SPIF_SENDCHANGE)

time.sleep(0.5)
print('After SPI trick:', user32.GetForegroundWindow() == hwnd)
