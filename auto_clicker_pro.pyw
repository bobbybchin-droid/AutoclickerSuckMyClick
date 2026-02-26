#!/usr/bin/env python3
"""
Suck My Click — A standalone Windows 11 auto-clicker with keyboard actions.
Built with tkinter, pyautogui, keyboard, and pynput.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import time
import sys
import os

# ---------------------------------------------------------------------------
# Optional dependency imports — graceful fallback
# ---------------------------------------------------------------------------
_MISSING = []

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02
except ImportError:
    pyautogui = None
    _MISSING.append("pyautogui")

try:
    import keyboard as kb_module
except ImportError:
    kb_module = None
    _MISSING.append("keyboard")

try:
    from pynput import mouse as pynput_mouse
except ImportError:
    pynput_mouse = None
    _MISSING.append("pynput")

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
COLORS = {
    "bg_dark":      "#0D1117",
    "bg_panel":     "#161B22",
    "bg_card":      "#1C2333",
    "bg_input":     "#0D1117",
    "border":       "#30363D",
    "accent":       "#58A6FF",
    "green":        "#3FB950",
    "red":          "#F85149",
    "orange":       "#D29922",
    "text":         "#E6EDF3",
    "text_dim":     "#8B949E",
    "text_muted":   "#484F58",
    "module_a":     "#58A6FF",
    "module_b":     "#D2A8FF",
}

FONT_UI        = ("Segoe UI", 10)
FONT_UI_BOLD   = ("Segoe UI", 10, "bold")
FONT_TITLE     = ("Segoe UI", 14, "bold")
FONT_HEADING   = ("Segoe UI", 11, "bold")
FONT_CODE      = ("Consolas", 10)
FONT_LIST      = ("Consolas", 9)
FONT_SMALL     = ("Segoe UI", 8)


def _virtual_screen_geometry():
    """Return (x, y, width, height) spanning all monitors (virtual desktop).

    Uses ctypes on Windows; falls back to primary monitor metrics.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        x = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        y = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        w = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        h = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return 0, 0, 0, 0  # caller will fall back to winfo_screenwidth/height


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ClickAction:
    """One click or keyboard action in a sequence."""

    def __init__(self, action_type="click", x=0, y=0, button="left", clicks=1,
                 delay_ms=200, label="", key_text="", key_action="press"):
        self.action_type = action_type  # "click" or "keyboard"
        self.x = x
        self.y = y
        self.button = button       # left / right / middle
        self.clicks = clicks       # 1 or 2
        self.delay_ms = delay_ms
        self.label = label
        # Keyboard-specific
        self.key_text = key_text       # e.g. "hello" or "enter" or "ctrl+c"
        self.key_action = key_action   # "press", "hotkey", "type"

    def to_dict(self):
        return {
            "action_type": self.action_type,
            "x": self.x, "y": self.y,
            "button": self.button,
            "clicks": self.clicks,
            "delay_ms": self.delay_ms,
            "label": self.label,
            "key_text": self.key_text,
            "key_action": self.key_action,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            action_type=d.get("action_type", "click"),
            x=d.get("x", 0), y=d.get("y", 0),
            button=d.get("button", "left"),
            clicks=d.get("clicks", 1),
            delay_ms=d.get("delay_ms", 200),
            label=d.get("label", ""),
            key_text=d.get("key_text", ""),
            key_action=d.get("key_action", "press"),
        )



class ClickModule:
    """Named list of actions with loop settings and execution thread."""

    def __init__(self, name="Module"):
        self.name = name
        self.actions: list[ClickAction] = []
        self.loop = False
        self.loop_count = 0  # 0 = infinite
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.running = False

    def start(self, on_start=None, on_stop=None, on_action=None):
        if self.running or not self.actions:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(on_start, on_stop, on_action), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def wait(self):
        """Block until the module's thread finishes."""
        if self._thread is not None:
            self._thread.join()

    _PRE_MOVE_MS = 5  # cursor arrives this many ms before clicking

    def _run(self, on_start, on_stop, on_action):
        self.running = True
        if on_start:
            on_start()
        try:
            iterations = 0
            num_actions = len(self.actions)
            while True:
                for i, action in enumerate(self.actions):
                    if self._stop_event.is_set():
                        return
                    if on_action:
                        on_action(i)
                    self._execute(action)
                    if self._stop_event.is_set():
                        return
                    # Interruptible delay with pre-move for next click action
                    if action.delay_ms > 0:
                        next_action = self._peek_next(i, num_actions)
                        if (next_action is not None
                                and next_action.action_type == "click"
                                and action.delay_ms > self._PRE_MOVE_MS
                                and pyautogui):
                            # Wait (delay - 5ms), move cursor, wait 5ms
                            main_wait = (action.delay_ms - self._PRE_MOVE_MS) / 1000.0
                            if self._stop_event.wait(main_wait):
                                return
                            pyautogui.moveTo(next_action.x, next_action.y)
                            if self._stop_event.wait(self._PRE_MOVE_MS / 1000.0):
                                return
                        else:
                            if self._stop_event.wait(action.delay_ms / 1000.0):
                                return
                iterations += 1
                if not self.loop:
                    break
                if self.loop_count > 0 and iterations >= self.loop_count:
                    break
        except Exception as e:
            print(f"Module '{self.name}' error: {e}")
        finally:
            self.running = False
            if on_stop:
                on_stop()

    def _peek_next(self, current_index, num_actions):
        """Return the next action in the sequence, or None."""
        next_i = current_index + 1
        if next_i < num_actions:
            return self.actions[next_i]
        # If looping, next action wraps to index 0
        if self.loop:
            return self.actions[0]
        return None

    @staticmethod
    def _execute(action: ClickAction):
        if action.action_type == "keyboard":
            if not pyautogui:
                return
            if action.key_action == "type":
                pyautogui.typewrite(action.key_text, interval=0.02)
            elif action.key_action == "hotkey":
                keys = [k.strip() for k in action.key_text.split("+")]
                pyautogui.hotkey(*keys)
            else:  # press
                pyautogui.press(action.key_text)
        else:
            if not pyautogui:
                return
            pyautogui.click(
                x=action.x, y=action.y,
                button=action.button,
                clicks=action.clicks,
            )

    def to_dict(self):
        return {
            "name": self.name,
            "actions": [a.to_dict() for a in self.actions],
            "loop": self.loop,
            "loop_count": self.loop_count,
        }

    def load_dict(self, d):
        self.name = d.get("name", self.name)
        self.actions = [ClickAction.from_dict(a) for a in d.get("actions", [])]
        self.loop = d.get("loop", False)
        self.loop_count = d.get("loop_count", 0)


# ---------------------------------------------------------------------------
# Coordinate Picker — fullscreen overlay with live XY text following cursor
# ---------------------------------------------------------------------------

class CoordinatePicker(tk.Toplevel):
    """Fullscreen overlay that shows live X,Y and captures on click."""

    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.30)
        self.configure(bg="#1a3a5c")

        # Cover entire virtual screen (all monitors)
        vx, vy, vw, vh = _virtual_screen_geometry()
        if vw <= 0 or vh <= 0:
            vx, vy, vw, vh = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        self._vx = vx
        self._vy = vy
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.config(cursor="crosshair")

        self.canvas = tk.Canvas(
            self, bg="#1a3a5c", highlightthickness=0,
            width=vw, height=vh
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.create_text(
            vw // 2, 40,
            text="Click anywhere to capture coordinates  /  Press ESC to cancel",
            fill="white", font=("Segoe UI", 16, "bold")
        )

        # Live coordinate label (follows cursor)
        self._coord_text = self.canvas.create_text(
            0, 0, text="", fill="#58A6FF", font=("Consolas", 14, "bold"), anchor="nw"
        )

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.bind("<Escape>", self._cancel)
        self.focus_force()
        self.grab_set()

    def _on_motion(self, event):
        x, y = event.x_root, event.y_root
        # Offset label slightly so it doesn't sit under the cursor
        self.canvas.coords(self._coord_text, event.x + 18, event.y + 18)
        self.canvas.itemconfig(self._coord_text, text=f"X: {x}  Y: {y}")

    def _on_click(self, event):
        x, y = event.x_root, event.y_root
        self.grab_release()
        self.destroy()
        self.callback(x, y)

    def _cancel(self, event=None):
        self.grab_release()
        self.destroy()


# ---------------------------------------------------------------------------
# Module Panel (one column of UI for a single ClickModule)
# ---------------------------------------------------------------------------

class ModulePanel(tk.Frame):
    """Complete UI for one click module."""

    def __init__(self, master, app, module: ClickModule, accent_color: str):
        super().__init__(master, bg=COLORS["bg_card"], highlightbackground=COLORS["border"],
                         highlightthickness=1)
        self.app = app
        self.module = module
        self.accent = accent_color

        # --- Header ---
        hdr = tk.Frame(self, bg=COLORS["bg_card"])
        hdr.pack(fill="x", padx=8, pady=(8, 4))

        self.status_dot = tk.Canvas(hdr, width=12, height=12, bg=COLORS["bg_card"],
                                    highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self._dot = self.status_dot.create_oval(2, 2, 11, 11, fill=COLORS["text_muted"], outline="")

        self.name_var = tk.StringVar(value=module.name)
        self.name_var.trace_add("write", lambda *_: setattr(module, "name", self.name_var.get()))
        name_entry = tk.Entry(
            hdr, textvariable=self.name_var, bg=COLORS["bg_card"], fg=accent_color,
            font=FONT_HEADING, relief="flat", insertbackground=accent_color,
            highlightthickness=0, width=16
        )
        name_entry.pack(side="left")

        self.count_label = tk.Label(hdr, text="0 actions", bg=COLORS["bg_card"],
                                    fg=COLORS["text_dim"], font=FONT_SMALL)
        self.count_label.pack(side="right")

        # Save/Load module buttons
        f_modio = tk.Frame(hdr, bg=COLORS["bg_card"])
        f_modio.pack(side="right", padx=(0, 8))
        tk.Button(f_modio, text="Load", bg=COLORS["bg_dark"], fg=COLORS["text_dim"],
                  font=FONT_SMALL, relief="flat", cursor="hand2",
                  command=self._load_module).pack(side="left", padx=2)
        tk.Button(f_modio, text="Save", bg=COLORS["bg_dark"], fg=COLORS["text_dim"],
                  font=FONT_SMALL, relief="flat", cursor="hand2",
                  command=self._save_module).pack(side="left", padx=2)

        # --- Separator ---
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill="x", padx=8, pady=2)

        # --- Action treeview with drag reorder ---
        list_frame = tk.Frame(self, bg=COLORS["bg_card"])
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)

        cols = ("num", "type", "details", "delay", "label")
        self.tree = ttk.Treeview(
            list_frame, columns=cols, show="headings",
            style="Dark.Treeview", selectmode="extended", height=8
        )
        self.tree.heading("num", text="#")
        self.tree.heading("type", text="Type")
        self.tree.heading("details", text="Details")
        self.tree.heading("delay", text="Delay")
        self.tree.heading("label", text="Label")

        self.tree.column("num", width=35, minwidth=30, stretch=False, anchor="center")
        self.tree.column("type", width=45, minwidth=40, stretch=False, anchor="center")
        self.tree.column("details", width=180, minwidth=80, stretch=True, anchor="w")
        self.tree.column("delay", width=65, minwidth=50, stretch=False, anchor="center")
        self.tree.column("label", width=90, minwidth=60, stretch=False, anchor="w")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # Drag reorder bindings
        self._drag_item = None
        self._drag_index = None
        self.tree.bind("<Button-1>", self._drag_start)
        self.tree.bind("<B1-Motion>", self._drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._drag_end)

        # --- List action buttons (Edit/Del/Copy/Paste) ---
        f_btns = tk.Frame(self, bg=COLORS["bg_card"])
        f_btns.pack(fill="x", padx=8, pady=2)

        btn_style = {"bg": COLORS["bg_dark"], "fg": COLORS["text"], "font": FONT_UI,
                     "relief": "flat", "cursor": "hand2", "padx": 4}

        tk.Button(f_btns, text="Edit", command=self._edit_action, **btn_style).pack(side="left", padx=2)
        tk.Button(f_btns, text="Del", command=self._del_action,
                  bg=COLORS["bg_dark"], fg=COLORS["red"], font=FONT_UI,
                  relief="flat", cursor="hand2", padx=4).pack(side="left", padx=2)
        tk.Button(f_btns, text="Copy", command=self._copy_action, **btn_style).pack(side="left", padx=2)
        tk.Button(f_btns, text="Paste", command=self._paste_action, **btn_style).pack(side="left", padx=2)

        # --- Separator ---
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill="x", padx=8, pady=2)

        # --- Loop controls ---
        f_loop = tk.Frame(self, bg=COLORS["bg_card"])
        f_loop.pack(fill="x", padx=8, pady=4)
        self.loop_var = tk.BooleanVar(value=module.loop)
        self.loop_var.trace_add("write", lambda *_: setattr(module, "loop", self.loop_var.get()))
        tk.Checkbutton(
            f_loop, text="Loop", variable=self.loop_var,
            bg=COLORS["bg_card"], fg=COLORS["text"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["text"],
            font=FONT_UI
        ).pack(side="left")
        tk.Label(f_loop, text="Count:", bg=COLORS["bg_card"], fg=COLORS["text_dim"],
                 font=FONT_UI).pack(side="left", padx=(10, 2))
        self.loop_count_var = tk.IntVar(value=module.loop_count)
        self.loop_count_var.trace_add("write", self._sync_loop_count)
        tk.Entry(
            f_loop, textvariable=self.loop_count_var, width=5,
            bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"],
            relief="flat", font=FONT_CODE, highlightthickness=1,
            highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"]
        ).pack(side="left", padx=2)
        tk.Label(f_loop, text="(0 = infinite)", bg=COLORS["bg_card"],
                 fg=COLORS["text_muted"], font=FONT_SMALL).pack(side="left", padx=4)

        # --- Run / Stop ---
        f_run = tk.Frame(self, bg=COLORS["bg_card"])
        f_run.pack(fill="x", padx=8, pady=(4, 8))
        self.run_btn = tk.Button(
            f_run, text="Run", bg=COLORS["green"], fg="#ffffff",
            font=FONT_UI_BOLD, relief="flat", cursor="hand2", width=8,
            command=self.run_module
        )
        self.run_btn.pack(side="left", padx=4)
        self.stop_btn = tk.Button(
            f_run, text="Stop", bg=COLORS["red"], fg="#ffffff",
            font=FONT_UI_BOLD, relief="flat", cursor="hand2", width=8,
            command=self.stop_module
        )
        self.stop_btn.pack(side="left", padx=4)

    # --- Drag reorder ---
    def _drag_start(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self._drag_item = item
            self._drag_index = self.tree.index(item)
        else:
            self._drag_item = None
            self._drag_index = None

    def _drag_motion(self, event):
        target_item = self.tree.identify_row(event.y)
        if not target_item or self._drag_index is None:
            return
        target_index = self.tree.index(target_item)
        if target_index != self._drag_index:
            actions = self.module.actions
            if 0 <= self._drag_index < len(actions) and 0 <= target_index < len(actions):
                actions[self._drag_index], actions[target_index] = actions[target_index], actions[self._drag_index]
                self._drag_index = target_index
                self._refresh_list()
                # Re-select the dragged row
                children = self.tree.get_children()
                if 0 <= target_index < len(children):
                    self.tree.selection_set(children[target_index])

    def _drag_end(self, event):
        self._drag_item = None
        self._drag_index = None

    # --- Sync helpers ---
    def _sync_loop_count(self, *_):
        try:
            self.module.loop_count = self.loop_count_var.get()
        except tk.TclError:
            pass

    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, action in enumerate(self.module.actions):
            if action.action_type == "keyboard":
                act = action.key_action.upper()
                txt = action.key_text[:18]
                details = f'{act} "{txt}"'
            else:
                details = f"({action.x},{action.y}) {action.button} x{action.clicks}"
            atype = "Key" if action.action_type == "keyboard" else "Click"
            delay = f"{action.delay_ms}ms"
            label = action.label[:16] if action.label else ""
            self.tree.insert("", "end", values=(i + 1, atype, details, delay, label))
        n = len(self.module.actions)
        self.count_label.config(text=f"{n} action{'s' if n != 1 else ''}")

    def _set_status(self, running: bool):
        color = COLORS["green"] if running else COLORS["text_muted"]
        self.status_dot.itemconfig(self._dot, fill=color)

    # --- Form helpers ---
    # --- Action management (delegated to shared form on app) ---
    def _edit_action(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        action = self.module.actions[idx]
        self.app.edit_action_on_panel(self, idx, action)

    def _del_action(self):
        sel = self.tree.selection()
        if not sel:
            return
        indices = sorted([self.tree.index(item) for item in sel])
        # Auto-cancel edit on shared form if editing any of the deleted actions
        self.app.notify_delete(self, indices)
        # Delete in reverse order so indices stay valid
        for idx in sorted(indices, reverse=True):
            del self.module.actions[idx]
        self._refresh_list()

    def _copy_action(self):
        sel = self.tree.selection()
        if not sel:
            return
        indices = [self.tree.index(item) for item in sel]
        self.app._clipboard = [
            ClickAction.from_dict(self.module.actions[i].to_dict())
            for i in indices
        ]
        count = len(indices)
        self.app.set_status(f"Copied {count} action{'s' if count != 1 else ''}")

    def _paste_action(self):
        if not self.app._clipboard:
            return
        sel = self.tree.selection()
        # Insert after last selected item, or at end if nothing selected
        if sel:
            indices = [self.tree.index(item) for item in sel]
            insert_at = max(indices) + 1
        else:
            insert_at = len(self.module.actions)
        for i, action in enumerate(self.app._clipboard):
            self.module.actions.insert(insert_at + i, ClickAction.from_dict(action.to_dict()))
        self._refresh_list()
        count = len(self.app._clipboard)
        self.app.set_status(f"Pasted {count} action{'s' if count != 1 else ''}")

    # --- Per-module save/load ---
    def _save_module(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            title=f"Save {self.module.name}"
        )
        if not path:
            return
        try:
            data = {"version": "1.0", "module": self.module.to_dict()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.app.set_status(f"Saved module to {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _load_module(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")], title=f"Load {self.module.name}"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Support both full config (pick module_a/module_b) and single-module files
            if "module" in data:
                self.module.load_dict(data["module"])
            elif "module_a" in data:
                self.module.load_dict(data["module_a"])
            else:
                messagebox.showwarning("Format", "Unrecognized config format.")
                return
            self.name_var.set(self.module.name)
            self.loop_var.set(self.module.loop)
            self.loop_count_var.set(self.module.loop_count)
            self._refresh_list()
            self.app.set_status(f"Loaded module from {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    # --- Run / Stop ---
    def run_module(self):
        if self.module.running:
            return

        def on_start():
            self.app.root.after(0, lambda: self._set_status(True))
            self.app.root.after(0, lambda: self.app.set_status(f"{self.module.name} running..."))

        def on_stop():
            self.app.root.after(0, lambda: self._set_status(False))
            self.app.root.after(0, lambda: self.app.set_status(f"{self.module.name} stopped."))

        self.module.start(on_start=on_start, on_stop=on_stop)

    def stop_module(self):
        self.module.stop()

    def load_from_module(self):
        """Refresh all UI elements from the module's current data."""
        self.name_var.set(self.module.name)
        self.loop_var.set(self.module.loop)
        self.loop_count_var.set(self.module.loop_count)
        self._refresh_list()


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class AutoClickerApp:
    VERSION = "1.0.0"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Suck My Click v{self.VERSION}")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.geometry("960x720")
        self.root.minsize(840, 620)

        # Shared clipboard for cross-module copy/paste
        self._clipboard: list[ClickAction] = []

        # Recording state
        self._recording = False
        self._recorded_actions: list[ClickAction] = []
        self._record_last_time = 0.0
        self._record_mouse_listener = None
        self._record_kb_hook = None

        # Modules
        self.module_a = ClickModule("Module A")
        self.module_b = ClickModule("Module B")

        self._build_ui()
        self._setup_hotkeys()
        self._update_mouse_pos()

    # ---- UI construction ----

    def _build_ui(self):
        # --- Treeview style for dark theme ---
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                         background=COLORS["bg_dark"],
                         fieldbackground=COLORS["bg_dark"],
                         foreground=COLORS["text"],
                         font=FONT_LIST,
                         borderwidth=0,
                         relief="flat",
                         rowheight=22)
        style.configure("Dark.Treeview.Heading",
                         background=COLORS["bg_panel"],
                         foreground=COLORS["text_dim"],
                         font=("Segoe UI", 9, "bold"),
                         borderwidth=0,
                         relief="flat")
        style.map("Dark.Treeview",
                   background=[("selected", COLORS["accent"])],
                   foreground=[("selected", "#ffffff")])
        style.map("Dark.Treeview.Heading",
                   background=[("active", COLORS["bg_card"])])

        # --- Title bar area ---
        title_bar = tk.Frame(self.root, bg=COLORS["bg_panel"])
        title_bar.pack(fill="x")
        tk.Label(
            title_bar, text="Suck My Click", bg=COLORS["bg_panel"],
            fg=COLORS["accent"], font=FONT_TITLE
        ).pack(side="left", padx=10, pady=6)
        tk.Label(
            title_bar, text=f"v{self.VERSION}", bg=COLORS["bg_panel"],
            fg=COLORS["text_muted"], font=FONT_UI
        ).pack(side="left")

        self.mouse_label = tk.Label(
            title_bar, text="Mouse: (—, —)", bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"], font=FONT_CODE
        )
        self.mouse_label.pack(side="right", padx=10, pady=6)

        # --- Toolbar ---
        self._toolbar_frame = tk.Frame(self.root, bg=COLORS["bg_panel"])
        self._toolbar_frame.pack(fill="x", pady=(0, 2))

        tb_btn = {"bg": COLORS["bg_dark"], "fg": COLORS["text"], "font": FONT_UI,
                  "relief": "flat", "cursor": "hand2", "padx": 8}

        tk.Button(self._toolbar_frame, text="Save Config", command=self._save_config, **tb_btn).pack(side="left", padx=4, pady=4)
        tk.Button(self._toolbar_frame, text="Load Config", command=self._load_config, **tb_btn).pack(side="left", padx=4, pady=4)

        tk.Frame(self._toolbar_frame, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=6, pady=4)

        tk.Button(self._toolbar_frame, text="Run All", command=self._run_sequence,
                  bg=COLORS["green"], fg="#ffffff", font=FONT_UI_BOLD,
                  relief="flat", cursor="hand2", padx=8).pack(side="left", padx=4, pady=4)
        tk.Button(self._toolbar_frame, text="Stop All", command=self._stop_all,
                  bg=COLORS["red"], fg="#ffffff", font=FONT_UI_BOLD,
                  relief="flat", cursor="hand2", padx=8).pack(side="left", padx=4, pady=4)
        self._record_btn = tk.Button(self._toolbar_frame, text="Record", command=self._toggle_recording,
                  bg=COLORS["orange"], fg="#ffffff", font=FONT_UI_BOLD,
                  relief="flat", cursor="hand2", padx=8)
        self._record_btn.pack(side="left", padx=4, pady=4)

        tk.Button(self._toolbar_frame, text="Hotkeys", command=self._open_hotkey_settings,
                  **tb_btn).pack(side="left", padx=4, pady=4)

        self._hotkey_label = tk.Label(
            self._toolbar_frame,
            text="F6: Run A  |  F7: Run B  |  F8: Stop All  |  F9: Quick Pick XY",
            bg=COLORS["bg_panel"], fg=COLORS["text_muted"], font=FONT_SMALL
        )
        self._hotkey_label.pack(side="right", padx=10, pady=4)

        # --- Shared action form ---
        self._build_action_form()

        # --- Sequence control bar ---
        self._sequence_stop_event = threading.Event()
        self._sequence_thread = None
        seq_frame = tk.Frame(self.root, bg=COLORS["bg_card"],
                             highlightbackground=COLORS["border"], highlightthickness=1)
        seq_frame.pack(fill="x", padx=8, pady=(2, 2))

        tk.Label(seq_frame, text="Sequence Control", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left", padx=(8, 4), pady=4)

        tk.Frame(seq_frame, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=4)

        self._master_loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            seq_frame, text="Master Loop", variable=self._master_loop_var,
            bg=COLORS["bg_card"], fg=COLORS["text"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["text"],
            font=FONT_SMALL
        ).pack(side="left", padx=(4, 2), pady=4)
        tk.Label(seq_frame, text="Count:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left", padx=(4, 2))
        self._master_loop_count_var = tk.IntVar(value=0)
        tk.Entry(seq_frame, textvariable=self._master_loop_count_var, width=4,
                 bg=COLORS["bg_input"], fg=COLORS["text"],
                 insertbackground=COLORS["text"], relief="flat", font=FONT_CODE,
                 highlightthickness=1, highlightbackground=COLORS["border"],
                 highlightcolor=COLORS["accent"]).pack(side="left", padx=2, pady=4)
        tk.Label(seq_frame, text="(0 = infinite)", bg=COLORS["bg_card"],
                 fg=COLORS["text_muted"], font=FONT_SMALL).pack(side="left", padx=4)

        tk.Frame(seq_frame, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=4)

        tk.Label(seq_frame, text="Order:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left", padx=(4, 2))
        self._seq_order_var = tk.StringVar(value="ab")
        tk.Radiobutton(
            seq_frame, text="A \u2192 B", variable=self._seq_order_var, value="ab",
            bg=COLORS["bg_card"], fg=COLORS["text"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["text"],
            font=FONT_SMALL
        ).pack(side="left", padx=2)
        tk.Radiobutton(
            seq_frame, text="B \u2192 A", variable=self._seq_order_var, value="ba",
            bg=COLORS["bg_card"], fg=COLORS["text"], selectcolor=COLORS["bg_dark"],
            activebackground=COLORS["bg_card"], activeforeground=COLORS["text"],
            font=FONT_SMALL
        ).pack(side="left", padx=2)

        # --- Module panels ---
        panels = tk.Frame(self.root, bg=COLORS["bg_dark"])
        panels.pack(fill="both", expand=True, padx=8, pady=4)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)

        self.panel_a = ModulePanel(panels, self, self.module_a, COLORS["module_a"])
        self.panel_a.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.panel_b = ModulePanel(panels, self, self.module_b, COLORS["module_b"])
        self.panel_b.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        panels.rowconfigure(0, weight=1)

        # --- Status bar ---
        status_bar = tk.Frame(self.root, bg=COLORS["bg_panel"])
        status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(
            status_bar, text="Ready", bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"], font=FONT_SMALL, anchor="w"
        )
        self.status_label.pack(side="left", padx=10, pady=3)

        failsafe_text = "Failsafe: move mouse to top-left corner to abort"
        if _MISSING:
            failsafe_text += f"  |  Missing: {', '.join(_MISSING)}"
        tk.Label(
            status_bar, text=failsafe_text, bg=COLORS["bg_panel"],
            fg=COLORS["orange"] if _MISSING else COLORS["text_muted"],
            font=FONT_SMALL
        ).pack(side="right", padx=10, pady=3)

    # ---- Hotkeys ----

    _HOTKEY_DEFAULTS = {
        "run_a": "F6",
        "run_b": "F7",
        "stop_all": "F8",
        "quick_pick": "F9",
        "add_action": "F10",
        "run_all": "F11",
        "record": "F12",
    }

    def _hotkey_config_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotkeys.json")

    def _load_hotkey_config(self):
        path = self._hotkey_config_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge with defaults for any missing keys
            merged = dict(self._HOTKEY_DEFAULTS)
            merged.update(data)
            return merged
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(self._HOTKEY_DEFAULTS)

    def _save_hotkey_config(self):
        path = self._hotkey_config_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._hotkey_cfg, f, indent=2)
        except Exception as e:
            print(f"Hotkey config save error: {e}")

    def _setup_hotkeys(self):
        self._hotkey_cfg = self._load_hotkey_config()
        self._hotkey_hooks = []
        if not kb_module:
            return
        try:
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["run_a"],
                                     lambda: self.root.after(0, self.panel_a.run_module)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["run_b"],
                                     lambda: self.root.after(0, self.panel_b.run_module)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["stop_all"],
                                     lambda: self.root.after(0, self._stop_all)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["quick_pick"], self._quick_pick))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["add_action"],
                                     lambda: self.root.after(0, self._form_add_action)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["run_all"],
                                     lambda: self.root.after(0, self._run_sequence)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["record"],
                                     lambda: self.root.after(0, self._toggle_recording)))
        except Exception as e:
            print(f"Hotkey setup error: {e}")
        self._update_hotkey_label()

    def _rebind_hotkeys(self):
        if kb_module:
            for hook in self._hotkey_hooks:
                try:
                    kb_module.remove_hotkey(hook)
                except Exception:
                    pass
        self._hotkey_hooks = []
        if not kb_module:
            return
        try:
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["run_a"],
                                     lambda: self.root.after(0, self.panel_a.run_module)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["run_b"],
                                     lambda: self.root.after(0, self.panel_b.run_module)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["stop_all"],
                                     lambda: self.root.after(0, self._stop_all)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["quick_pick"], self._quick_pick))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["add_action"],
                                     lambda: self.root.after(0, self._form_add_action)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["run_all"],
                                     lambda: self.root.after(0, self._run_sequence)))
            self._hotkey_hooks.append(
                kb_module.add_hotkey(self._hotkey_cfg["record"],
                                     lambda: self.root.after(0, self._toggle_recording)))
        except Exception as e:
            print(f"Hotkey rebind error: {e}")
        self._update_hotkey_label()

    def _update_hotkey_label(self):
        cfg = self._hotkey_cfg
        self._hotkey_label.config(
            text=(f"{cfg['run_a']}: Run A  |  {cfg['run_b']}: Run B  |  "
                  f"{cfg['stop_all']}: Stop All  |  {cfg['quick_pick']}: Quick Pick  |  "
                  f"{cfg['add_action']}: Add  |  {cfg['run_all']}: Run All  |  "
                  f"{cfg['record']}: Record")
        )

    def _open_hotkey_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Hotkey Settings")
        dlg.configure(bg=COLORS["bg_panel"])
        dlg.geometry("340x340")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        entries = {}
        labels = [("run_a", "Run A"), ("run_b", "Run B"),
                  ("stop_all", "Stop All"), ("quick_pick", "Quick Pick"),
                  ("add_action", "Add Action"),
                  ("run_all", "Run All"),
                  ("record", "Record")]

        for i, (key, display) in enumerate(labels):
            tk.Label(dlg, text=f"{display}:", bg=COLORS["bg_panel"],
                     fg=COLORS["text"], font=FONT_UI).grid(
                         row=i, column=0, padx=(12, 6), pady=6, sticky="e")
            var = tk.StringVar(value=self._hotkey_cfg[key])
            ent = tk.Entry(dlg, textvariable=var, width=16,
                           bg=COLORS["bg_input"], fg=COLORS["text"],
                           insertbackground=COLORS["text"], relief="flat",
                           font=FONT_CODE, highlightthickness=1,
                           highlightbackground=COLORS["border"],
                           highlightcolor=COLORS["accent"])
            ent.grid(row=i, column=1, padx=(0, 12), pady=6, sticky="w")
            entries[key] = var

        btn_frame = tk.Frame(dlg, bg=COLORS["bg_panel"])
        btn_frame.grid(row=len(labels), column=0, columnspan=2, pady=12)

        def save():
            for key, var in entries.items():
                self._hotkey_cfg[key] = var.get().strip()
            self._save_hotkey_config()
            self._rebind_hotkeys()
            dlg.destroy()
            self.set_status("Hotkeys updated")

        tk.Button(btn_frame, text="Save", bg=COLORS["green"], fg="#ffffff",
                  font=FONT_UI_BOLD, relief="flat", cursor="hand2", padx=10,
                  command=save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancel", bg=COLORS["bg_dark"], fg=COLORS["text"],
                  font=FONT_UI, relief="flat", cursor="hand2", padx=10,
                  command=dlg.destroy).pack(side="left", padx=6)

    def _quick_pick(self):
        """Quick Pick — grab current mouse position into the form X/Y fields."""
        if pynput_mouse:
            from pynput.mouse import Controller
            m = Controller()
            pos = m.position
            self.root.after(0, lambda: self._form_x_var.set(pos[0]))
            self.root.after(0, lambda: self._form_y_var.set(pos[1]))
            self.root.after(0, lambda: self.set_status(f"Picked ({pos[0]}, {pos[1]}) into form"))

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ---- Recording ----

    def _toggle_recording(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self._recorded_actions = []
        self._record_last_time = time.perf_counter()
        self.set_status("Recording... (0 actions)")
        self._record_btn.config(text="Stop Rec", bg=COLORS["red"])

        # Mouse listener (pynput)
        if pynput_mouse:
            from pynput.mouse import Listener as MouseListener, Button

            def on_click(x, y, button, pressed):
                if not pressed or not self._recording:
                    return
                now = time.perf_counter()
                delay_ms = int((now - self._record_last_time) * 1000)
                self._record_last_time = now

                btn_map = {Button.left: "left", Button.right: "right", Button.middle: "middle"}
                btn_name = btn_map.get(button, "left")

                action = ClickAction(
                    action_type="click",
                    x=int(x), y=int(y),
                    button=btn_name,
                    clicks=1,
                    delay_ms=max(0, delay_ms),
                )
                self._recorded_actions.append(action)
                count = len(self._recorded_actions)
                self.root.after(0, lambda c=count:
                    self.set_status(f"Recording... ({c} actions)"))

            self._record_mouse_listener = MouseListener(on_click=on_click)
            self._record_mouse_listener.start()

        # Keyboard listener
        if kb_module:
            record_key = self._hotkey_cfg.get("record", "F12").lower()

            def on_key(event):
                if not self._recording:
                    return
                # Ignore the record hotkey itself
                if event.name.lower() == record_key:
                    return
                # Ignore modifier-only keys held down (shift, ctrl, alt)
                if event.event_type != "down":
                    return

                now = time.perf_counter()
                delay_ms = int((now - self._record_last_time) * 1000)
                self._record_last_time = now

                action = ClickAction(
                    action_type="keyboard",
                    key_text=event.name,
                    key_action="press",
                    delay_ms=max(0, delay_ms),
                )
                self._recorded_actions.append(action)
                count = len(self._recorded_actions)
                self.root.after(0, lambda c=count:
                    self.set_status(f"Recording... ({c} actions)"))

            self._record_kb_hook = kb_module.on_press(on_key)

    def _stop_recording(self):
        self._recording = False
        self._record_btn.config(text="Record", bg=COLORS["orange"])

        # Stop mouse listener
        if self._record_mouse_listener is not None:
            self._record_mouse_listener.stop()
            self._record_mouse_listener = None

        # Stop keyboard listener
        if self._record_kb_hook is not None and kb_module:
            try:
                kb_module.unhook(self._record_kb_hook)
            except Exception:
                pass
            self._record_kb_hook = None

        if not self._recorded_actions:
            self.set_status("Recording stopped — no actions captured.")
            return

        # Shift delays forward: each action gets the *next* action's delay
        # so delay_ms means "wait this long after performing this action"
        for i in range(len(self._recorded_actions) - 1):
            self._recorded_actions[i].delay_ms = self._recorded_actions[i + 1].delay_ms
        self._recorded_actions[-1].delay_ms = 0

        # Put recorded actions into the target module, clearing it first
        panel = self._get_target_panel()
        panel.module.actions = self._recorded_actions
        panel._refresh_list()
        count = len(self._recorded_actions)
        self.set_status(
            f"Recorded {count} action{'s' if count != 1 else ''} into {panel.module.name}")
        self._recorded_actions = []

    # ---- Mouse position tracker ----

    def _update_mouse_pos(self):
        try:
            if pynput_mouse:
                from pynput.mouse import Controller
                m = Controller()
                pos = m.position
                self.mouse_label.config(text=f"Mouse: ({pos[0]}, {pos[1]})")
            elif pyautogui:
                pos = pyautogui.position()
                self.mouse_label.config(text=f"Mouse: ({pos[0]}, {pos[1]})")
        except Exception:
            pass
        self.root.after(100, self._update_mouse_pos)

    # ---- Config save/load ----

    def _save_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            title="Save Configuration"
        )
        if not path:
            return
        try:
            data = {
                "version": "1.0",
                "module_a": self.module_a.to_dict(),
                "module_b": self.module_b.to_dict(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.set_status(f"Config saved to {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _load_config(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")], title="Load Configuration"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "module_a" in data:
                self.module_a.load_dict(data["module_a"])
            if "module_b" in data:
                self.module_b.load_dict(data["module_b"])
            self.panel_a.load_from_module()
            self.panel_b.load_from_module()
            self.set_status(f"Config loaded from {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    # ---- Run / Stop ----

    def _run_sequence(self):
        """Run modules sequentially in the chosen order, repeating per master loop."""
        if self._sequence_thread and self._sequence_thread.is_alive():
            return
        self._sequence_stop_event.clear()

        try:
            master_count = max(0, self._master_loop_count_var.get())
        except tk.TclError:
            master_count = 0
        use_master_loop = self._master_loop_var.get()

        # Determine run order
        if self._seq_order_var.get() == "ba":
            order = [
                (self.module_b, self.panel_b),
                (self.module_a, self.panel_a),
            ]
        else:
            order = [
                (self.module_a, self.panel_a),
                (self.module_b, self.panel_b),
            ]

        def run():
            iteration = 0
            while True:
                if self._sequence_stop_event.is_set():
                    break
                iteration += 1
                total_str = str(master_count) if (use_master_loop and master_count > 0) else "\u221e"
                for module, panel in order:
                    if self._sequence_stop_event.is_set():
                        break
                    if module.actions:
                        self.root.after(0, lambda i=iteration, t=total_str, m=module:
                            self.set_status(f"Sequence pass {i}/{t}: Running {m.name}..."))
                        self.root.after(0, lambda p=panel: p._set_status(True))
                        module.start()
                        module.wait()
                        self.root.after(0, lambda p=panel: p._set_status(False))
                if self._sequence_stop_event.is_set():
                    break
                # Check master loop
                if not use_master_loop:
                    break
                if master_count > 0 and iteration >= master_count:
                    break
            self.root.after(0, lambda: self.set_status("Sequence finished."))

        self._sequence_thread = threading.Thread(target=run, daemon=True)
        self._sequence_thread.start()

    def _stop_all(self):
        self._sequence_stop_event.set()
        self.module_a.stop()
        self.module_b.stop()
        self.set_status("All modules stopped.")

    # ---- Helpers ----

    def set_status(self, text):
        self.status_label.config(text=text)

    # ---- Shared action form ----

    def _build_action_form(self):
        """Build the shared action form bar above the module panels."""
        self._edit_panel = None   # which ModulePanel we're editing on
        self._edit_index = None   # index within that panel's module

        form_frame = tk.Frame(self.root, bg=COLORS["bg_card"],
                              highlightbackground=COLORS["border"], highlightthickness=1)
        form_frame.pack(fill="x", padx=8, pady=(2, 2))

        entry_cfg = {
            "bg": COLORS["bg_input"], "fg": COLORS["text"],
            "insertbackground": COLORS["text"], "relief": "flat",
            "font": FONT_CODE, "highlightthickness": 1,
            "highlightbackground": COLORS["border"],
            "highlightcolor": COLORS["accent"],
        }
        radio_cfg = {
            "bg": COLORS["bg_card"], "fg": COLORS["text"],
            "selectcolor": COLORS["bg_dark"],
            "activebackground": COLORS["bg_card"],
            "activeforeground": COLORS["text"], "font": FONT_SMALL,
        }

        # Row 1: Target | Type | Label | Delay
        row1 = tk.Frame(form_frame, bg=COLORS["bg_card"])
        row1.pack(fill="x", padx=8, pady=(4, 1))

        tk.Label(row1, text="Target:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left")
        self._form_target_var = tk.StringVar(value="a")
        tk.Radiobutton(row1, text="A", variable=self._form_target_var,
                       value="a", fg=COLORS["module_a"],
                       **{k: v for k, v in radio_cfg.items() if k != "fg"}
                       ).pack(side="left", padx=2)
        tk.Radiobutton(row1, text="B", variable=self._form_target_var,
                       value="b", fg=COLORS["module_b"],
                       **{k: v for k, v in radio_cfg.items() if k != "fg"}
                       ).pack(side="left", padx=2)

        tk.Frame(row1, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=1)

        tk.Label(row1, text="Type:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left")
        self._form_action_type_var = tk.StringVar(value="click")
        tk.Radiobutton(row1, text="Click", variable=self._form_action_type_var,
                       value="click", command=self._form_toggle_type,
                       **radio_cfg).pack(side="left", padx=2)
        tk.Radiobutton(row1, text="Key", variable=self._form_action_type_var,
                       value="keyboard", command=self._form_toggle_type,
                       **radio_cfg).pack(side="left", padx=2)

        tk.Frame(row1, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=1)

        tk.Label(row1, text="Label:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left")
        self._form_label_var = tk.StringVar()
        tk.Entry(row1, textvariable=self._form_label_var, width=10, **entry_cfg).pack(side="left", padx=2)

        tk.Frame(row1, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=1)

        tk.Label(row1, text="Delay:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left")
        self._form_delay_var = tk.IntVar(value=200)
        tk.Entry(row1, textvariable=self._form_delay_var, width=5, **entry_cfg).pack(side="left", padx=2)
        tk.Label(row1, text="ms", bg=COLORS["bg_card"],
                 fg=COLORS["text_muted"], font=FONT_SMALL).pack(side="left")

        # Click row: X | Y | Pick | Grid | Btn | Clicks
        self._form_click_row = tk.Frame(form_frame, bg=COLORS["bg_card"])

        tk.Label(self._form_click_row, text="X:", bg=COLORS["bg_card"],
                 fg=COLORS["text"], font=FONT_SMALL).pack(side="left")
        self._form_x_var = tk.IntVar(value=0)
        tk.Entry(self._form_click_row, textvariable=self._form_x_var, width=5, **entry_cfg).pack(side="left", padx=(1, 3))
        tk.Label(self._form_click_row, text="Y:", bg=COLORS["bg_card"],
                 fg=COLORS["text"], font=FONT_SMALL).pack(side="left")
        self._form_y_var = tk.IntVar(value=0)
        tk.Entry(self._form_click_row, textvariable=self._form_y_var, width=5, **entry_cfg).pack(side="left", padx=1)
        tk.Button(self._form_click_row, text="Pick", bg=COLORS["accent"], fg="#ffffff",
                  font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                  command=self._form_pick_xy).pack(side="left", padx=(4, 1))

        tk.Frame(self._form_click_row, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=1)

        self._form_button_var = tk.StringVar(value="left")
        for val in ("left", "right", "middle"):
            tk.Radiobutton(self._form_click_row, text=val[0].upper(),
                           variable=self._form_button_var, value=val,
                           **radio_cfg).pack(side="left", padx=1)

        tk.Frame(self._form_click_row, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=1)

        self._form_clicks_var = tk.IntVar(value=1)
        tk.Radiobutton(self._form_click_row, text="1x", variable=self._form_clicks_var,
                       value=1, **radio_cfg).pack(side="left", padx=1)
        tk.Radiobutton(self._form_click_row, text="2x", variable=self._form_clicks_var,
                       value=2, **radio_cfg).pack(side="left", padx=1)

        # Keyboard row: Action | Key/Text
        self._form_kb_row = tk.Frame(form_frame, bg=COLORS["bg_card"])

        tk.Label(self._form_kb_row, text="Action:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left")
        self._form_key_action_var = tk.StringVar(value="press")
        for val, txt in [("press", "Press"), ("hotkey", "Hotkey"), ("type", "Type")]:
            tk.Radiobutton(self._form_kb_row, text=txt, variable=self._form_key_action_var,
                           value=val, **radio_cfg).pack(side="left", padx=1)

        tk.Frame(self._form_kb_row, bg=COLORS["border"], width=1).pack(side="left", fill="y", padx=4, pady=1)

        tk.Label(self._form_kb_row, text="Key:", bg=COLORS["bg_card"],
                 fg=COLORS["text_dim"], font=FONT_SMALL).pack(side="left")
        self._form_key_text_var = tk.StringVar()
        tk.Entry(self._form_kb_row, textvariable=self._form_key_text_var, width=14,
                 **entry_cfg).pack(side="left", padx=2)

        # Show click row by default
        self._form_click_row.pack(fill="x", padx=8, pady=(1, 1))

        # Add / Update button row
        f_form_btns = tk.Frame(form_frame, bg=COLORS["bg_card"])
        f_form_btns.pack(fill="x", padx=8, pady=(1, 4))

        self._form_add_btn = tk.Button(
            f_form_btns, text="+ Add", bg=COLORS["green"], fg="#ffffff",
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2", padx=6,
            command=self._form_add_action
        )
        self._form_add_btn.pack(side="left", padx=2)
        self._form_update_btn = tk.Button(
            f_form_btns, text="Update", bg=COLORS["accent"], fg="#ffffff",
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2", padx=6,
            command=self._form_update_action
        )
        self._form_cancel_edit_btn = tk.Button(
            f_form_btns, text="Cancel", bg=COLORS["bg_dark"], fg=COLORS["text"],
            font=FONT_SMALL, relief="flat", cursor="hand2", padx=6,
            command=self._form_cancel_edit
        )
        self._form_status_label = tk.Label(
            f_form_btns, text="", bg=COLORS["bg_card"],
            fg=COLORS["text_muted"], font=FONT_SMALL
        )
        self._form_status_label.pack(side="left", padx=4)

        self._form_btn_frame = f_form_btns

    def _form_toggle_type(self):
        if self._form_action_type_var.get() == "click":
            self._form_kb_row.pack_forget()
            self._form_click_row.pack(fill="x", padx=8, pady=(1, 1),
                                      before=self._form_add_btn.master)
        else:
            self._form_click_row.pack_forget()
            self._form_kb_row.pack(fill="x", padx=8, pady=(1, 1),
                                   before=self._form_add_btn.master)

    def _form_reset(self):
        self._form_action_type_var.set("click")
        self._form_label_var.set("")
        # Keep the last delay value — don't reset _form_delay_var
        self._form_x_var.set(0)
        self._form_y_var.set(0)
        self._form_button_var.set("left")
        self._form_clicks_var.set(1)
        self._form_key_action_var.set("press")
        self._form_key_text_var.set("")
        self._edit_panel = None
        self._edit_index = None
        self._form_update_btn.pack_forget()
        self._form_cancel_edit_btn.pack_forget()
        self._form_add_btn.pack(side="left", padx=2, before=self._form_status_label)
        self._form_status_label.config(text="")
        self._form_toggle_type()

    def _form_build_action(self):
        try:
            action_type = self._form_action_type_var.get()
            if action_type == "click":
                return ClickAction(
                    action_type="click",
                    x=self._form_x_var.get(), y=self._form_y_var.get(),
                    button=self._form_button_var.get(),
                    clicks=self._form_clicks_var.get(),
                    delay_ms=max(0, self._form_delay_var.get()),
                    label=self._form_label_var.get().strip(),
                )
            else:
                txt = self._form_key_text_var.get().strip()
                if not txt:
                    messagebox.showwarning("Missing key", "Please enter a key or text.")
                    return None
                return ClickAction(
                    action_type="keyboard",
                    key_text=txt,
                    key_action=self._form_key_action_var.get(),
                    delay_ms=max(0, self._form_delay_var.get()),
                    label=self._form_label_var.get().strip(),
                )
        except tk.TclError:
            messagebox.showwarning("Invalid input", "Please check numeric fields.")
            return None

    def _form_populate(self, action):
        self._form_action_type_var.set(action.action_type)
        self._form_label_var.set(action.label)
        self._form_delay_var.set(action.delay_ms)
        self._form_x_var.set(action.x)
        self._form_y_var.set(action.y)
        self._form_button_var.set(action.button)
        self._form_clicks_var.set(action.clicks)
        self._form_key_action_var.set(action.key_action)
        self._form_key_text_var.set(action.key_text)
        self._form_toggle_type()

    def _get_target_panel(self):
        return self.panel_a if self._form_target_var.get() == "a" else self.panel_b

    def _form_add_action(self):
        action = self._form_build_action()
        if action is None:
            return
        panel = self._get_target_panel()
        panel.module.actions.append(action)
        panel._refresh_list()
        self._form_reset()
        self.set_status(f"Action added to {panel.module.name}")

    def _form_update_action(self):
        if self._edit_index is None or self._edit_panel is None:
            return
        action = self._form_build_action()
        if action is None:
            return
        self._edit_panel.module.actions[self._edit_index] = action
        self._edit_panel._refresh_list()
        self._form_reset()
        self.set_status("Action updated")

    def _form_cancel_edit(self):
        self._form_reset()

    def _form_pick_xy(self):
        self.root.iconify()

        def on_picked(x, y):
            self._form_x_var.set(x)
            self._form_y_var.set(y)
            self.root.deiconify()

        self.root.after(300, lambda: CoordinatePicker(self.root, on_picked))

    def edit_action_on_panel(self, panel, idx, action):
        """Called by ModulePanel.Edit button to load an action into the shared form."""
        self._edit_panel = panel
        self._edit_index = idx
        # Set target selector to match the panel
        if panel is self.panel_a:
            self._form_target_var.set("a")
        else:
            self._form_target_var.set("b")
        self._form_populate(action)
        # Switch to Update/Cancel mode
        self._form_add_btn.pack_forget()
        self._form_update_btn.pack(side="left", padx=2, before=self._form_status_label)
        self._form_cancel_edit_btn.pack(side="left", padx=2, before=self._form_status_label)
        self._form_status_label.config(text=f"Editing #{idx + 1} on {panel.module.name}")

    def notify_delete(self, panel, indices):
        """Called by ModulePanel when deleting actions, to cancel edit if needed."""
        if self._edit_panel is not panel:
            return
        if self._edit_index is not None:
            if self._edit_index in indices:
                self._form_reset()
            else:
                shift = sum(1 for i in indices if i < self._edit_index)
                self._edit_index -= shift

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Enable per-monitor DPI awareness so tkinter reports true pixel coords
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    app = AutoClickerApp()
    app.run()
