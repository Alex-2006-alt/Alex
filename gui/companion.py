import tkinter as tk
from tkinter import ttk
import sys
import os
import argparse
import subprocess
from PIL import Image, ImageTk

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMAGE_PATH = os.path.join(PROJECT_ROOT, "gui", "assets", "cute_octocat_logo.jpg")

class CompanionWidget:
    def __init__(self, root, app_name):
        self.root = root
        self.app_name = app_name
        
        # Make borderless and topmost
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # Position at bottom right (e.g., 20px from edges)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Estimated window size
        w, h = 200, 250
        x = screen_width - w - 20
        y = screen_height - h - 60 # 60 to clear typical taskbar
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        
        # Styling
        self.root.configure(bg="white")
        
        # Add the cute cat image
        try:
            img = Image.open(IMAGE_PATH)
            img = img.resize((120, 120), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(img)
            img_label = tk.Label(self.root, image=self.photo, bg="white")
            img_label.pack(pady=10)
        except Exception as e:
            print(f"Failed to load image: {e}")
            tk.Label(self.root, text="😺", font=("Arial", 50), bg="white").pack(pady=10)
            
        # Add app context text
        if self.app_name:
            tk.Label(self.root, text=f"Focusing: {self.app_name}", bg="white", font=("Segoe UI", 10, "bold"), fg="#333").pack()
        else:
            tk.Label(self.root, text="Hello!", bg="white", font=("Segoe UI", 10, "bold"), fg="#333").pack()

        # Add buttons
        btn_frame = tk.Frame(self.root, bg="white")
        btn_frame.pack(pady=10, fill="x", padx=10)
        
        style = ttk.Style()
        style.configure("TButton", font=("Segoe UI", 9))
        
        if self.app_name:
            ttk.Button(btn_frame, text="Close App", command=self.close_app).pack(fill="x", pady=2)
            
        ttk.Button(btn_frame, text="Sleep PC", command=self.sleep_pc).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Dismiss", command=self.root.destroy).pack(fill="x", pady=2)
        
        # Allow dragging the window (optional, but good for borderless)
        self.root.bind("<ButtonPress-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def close_app(self):
        # We can use psutil or taskkill. Taskkill is simple on Windows.
        if self.app_name:
            try:
                subprocess.Popen(f'taskkill /F /IM {self.app_name}.exe', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                print(f"Failed to kill {self.app_name}: {e}")
        self.root.destroy()
        
    def sleep_pc(self):
        try:
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        except Exception:
            pass
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=str, default="", help="Name of the app that was opened")
    args = parser.parse_args()

    root = tk.Tk()
    app = CompanionWidget(root, args.app)
    
    # Auto-dismiss after 15 seconds if not interacted with
    root.after(15000, root.destroy)
    
    root.mainloop()

if __name__ == "__main__":
    main()
