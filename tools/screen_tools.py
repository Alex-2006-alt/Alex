"""
ALEX — Screen Tools
Captures the display so the vision brain can answer questions about
whatever is currently on screen.

Modes
-----
full          : entire virtual desktop (all monitors)
active_window : only the foreground window's client rectangle
region        : user drags a selection rectangle (Snipping-Tool style)
"""

import base64
import io
import os
import time
import threading
from pathlib import Path

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
import config

# ─── Screenshot directory ────────────────────────────────────────────────────

SCREENSHOT_DIR = config.DATA_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Internal helpers ────────────────────────────────────────────────────────

def _pil_to_b64(img) -> str:
    """Convert a PIL Image to a base64-encoded PNG string."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _save_screenshot(img) -> str:
    """Save a PIL Image to the screenshots folder and return the path."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"screen_{ts}.png"
    img.save(str(path))
    log.info(f"📸 Screenshot saved: {path}")
    return str(path)


def capture_full() -> tuple:
    """
    Capture the entire virtual desktop (all monitors combined).
    Returns (PIL.Image, path, base64_str).
    """
    try:
        import mss
        from PIL import Image

        with mss.mss() as sct:
            # monitor 0 = combined bounding box of all monitors
            monitor = sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        path = _save_screenshot(img)
        b64 = _pil_to_b64(img)
        return img, path, b64

    except ImportError:
        # Fallback: use PIL/ImageGrab (slower, Windows-only multi-monitor issues)
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
        path = _save_screenshot(img)
        b64 = _pil_to_b64(img)
        return img, path, b64


def capture_active_window() -> tuple:
    """
    Capture only the foreground window.
    Returns (PIL.Image, path, base64_str).
    Falls back to full screenshot if the window rect can't be determined.
    """
    try:
        import win32gui
        from PIL import ImageGrab

        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            # Clamp to positive dimensions
            if right > left and bottom > top:
                img = ImageGrab.grab(bbox=(left, top, right, bottom))
                path = _save_screenshot(img)
                b64 = _pil_to_b64(img)
                log.info(f"📸 Active window captured: {right-left}x{bottom-top}")
                return img, path, b64
    except Exception as e:
        log.warning(f"Active window capture failed, falling back to full: {e}")

    return capture_full()


def capture_region_interactive() -> tuple | None:
    """
    Show a transparent fullscreen overlay; user clicks and drags to select a
    region. Returns (PIL.Image, path, base64_str) or None if cancelled.

    Uses tkinter — available in every standard Python install.
    """
    import tkinter as tk
    from PIL import ImageGrab

    result_box = [None]  # mutable container so inner class can write to it
    done_event = threading.Event()

    def _run_selector():
        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-alpha", 0.3)
        root.attributes("-topmost", True)
        root.configure(bg="black")
        root.title("Alex — drag to select region")
        root.config(cursor="crosshair")

        canvas = tk.Canvas(root, cursor="crosshair", bg="black",
                           highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        start = [0, 0]
        rect_id = [None]

        def on_press(e):
            start[0], start[1] = e.x_root, e.y_root
            if rect_id[0]:
                canvas.delete(rect_id[0])

        def on_drag(e):
            if rect_id[0]:
                canvas.delete(rect_id[0])
            x0 = start[0] - root.winfo_rootx()
            y0 = start[1] - root.winfo_rooty()
            x1 = e.x_root - root.winfo_rootx()
            y1 = e.y_root - root.winfo_rooty()
            rect_id[0] = canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="#00FF88", width=2,
                fill="#00FF88", stipple="gray25"
            )

        def on_release(e):
            x1, y1 = e.x_root, e.y_root
            x0, y0 = start
            # Ensure left < right, top < bottom
            box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            if box[2] - box[0] > 5 and box[3] - box[1] > 5:
                result_box[0] = box
            root.destroy()

        def on_escape(e):
            root.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind("<Escape>", on_escape)
        root.mainloop()
        done_event.set()

    t = threading.Thread(target=_run_selector, daemon=True)
    t.start()
    done_event.wait(timeout=60)

    box = result_box[0]
    if box is None:
        log.info("Region selection cancelled")
        return None

    img = ImageGrab.grab(bbox=box)
    path = _save_screenshot(img)
    b64 = _pil_to_b64(img)
    log.info(f"📸 Region captured: {img.width}x{img.height}")
    return img, path, b64


# ─── Public convenience function (called by VisionBrain & hotkey) ─────────────

def take_screenshot(mode: str = "active_window") -> dict | None:
    """
    Take a screenshot and return a dict with image_path and image_b64.
    mode: "full" | "active_window" | "region"
    Returns None if the operation was cancelled (region mode only).
    """
    mode = mode.lower().strip()
    try:
        if mode == "region":
            result = capture_region_interactive()
            if result is None:
                return None
            _, path, b64 = result
        elif mode == "active_window":
            _, path, b64 = capture_active_window()
        else:
            _, path, b64 = capture_full()

        return {
            "image_path": path,
            "image_b64": b64,
        }
    except Exception as e:
        log.error(f"Screenshot failed ({mode}): {e}")
        return None


# ─── ALEX Tool registration ───────────────────────────────────────────────────

@tool(
    name="capture_screen",
    description=(
        "Take a screenshot of the display so you can see and answer questions "
        "about what is currently on the user's screen. "
        "Use mode='active_window' for the focused app, 'full' for all monitors, "
        "'region' to let the user drag a selection."
    ),
    parameters={
        "mode": {
            "type": "string",
            "description": "Capture mode: 'full', 'active_window', or 'region'",
            "required": False,
        },
        "question": {
            "type": "string",
            "description": "The user's question about the screen content",
            "required": False,
        },
    },
    category="vision",
    safety=SafetyLevel.SAFE,
)
def capture_screen(params: dict) -> ToolResult:
    mode = params.get("mode", config.SCREEN_CAPTURE_MODE)
    question = params.get("question", "What do you see on the screen?")

    data = take_screenshot(mode)
    if data is None:
        return ToolResult(success=False, error="Screenshot cancelled or failed.")

    # If vision is enabled, immediately answer the question using VisionBrain
    if config.SCREEN_VISION_ENABLED:
        try:
            from core.vision_brain import VisionBrain
            vb = VisionBrain()
            answer = vb.ask_about_image(data["image_b64"], question)
            return ToolResult(
                success=True,
                message=answer,
                artifacts=[data["image_path"]],
                data={"image_path": data["image_path"], "answer": answer},
            )
        except Exception as e:
            log.error(f"VisionBrain failed: {e}")
            return ToolResult(
                success=True,
                message=f"Screenshot saved to {data['image_path']}. Vision analysis unavailable: {e}",
                artifacts=[data["image_path"]],
            )

    return ToolResult(
        success=True,
        message="Screenshot saved.",
        artifacts=[data["image_path"]],
        data=data,
    )
