# AutoClicker Pro v1.0.0

A standalone Windows 11 auto-clicker with keyboard action support, built with Python and tkinter.

## Features

- **Dual Module System** — Two independent click modules (A & B) that run simultaneously
- **Mouse Clicks** — Left, right, middle button; single or double click at any screen coordinate
- **Keyboard Actions** — Press keys, hotkey combos (ctrl+c), or type text strings
- **Add Click Position** — Minimizes app, shows live X,Y coordinates following your cursor, click to capture
- **Grid Overlay** — 8x6 labeled grid overlay for quick coordinate picking
- **Drag to Reorder** — Drag actions in the list to rearrange sequence order
- **Loop Control** — Per-module looping with configurable count (0 = infinite)
- **Save/Load Configs** — Save and load full configs (both modules) or individual module configs
- **Global Hotkeys** — Work even when the app is not focused
- **Live Mouse Tracker** — Current mouse position shown in the title bar
- **Emergency Stop** — Move mouse to top-left corner to abort all actions (pyautogui failsafe)
- **Dark Theme** — GitHub-style dark mode UI

## Hotkeys

| Key | Action |
|-----|--------|
| F6  | Run Module A |
| F7  | Run Module B |
| F8  | Stop All Modules |
| F9  | Quick Pick — copies current mouse position to clipboard as `x,y` |

## Setup

### Option 1: Run directly
Double-click `LAUNCH.bat` — it installs dependencies and runs the app.

### Option 2: Build standalone EXE
Double-click `BUILD_EXE.bat` — it creates `dist/AutoClickerPro.exe`.

### Option 3: Manual
```
pip install pyautogui keyboard pynput
python auto_clicker_pro.py
```

## Requirements

- Python 3.10+
- Windows 11 (tested), Windows 10 (should work)
- Dependencies: pyautogui, keyboard, pynput

## Config Format

Configs are saved as JSON. Full config contains both modules:

```json
{
  "version": "1.0",
  "module_a": {
    "name": "Module A",
    "actions": [
      {"action_type": "click", "x": 500, "y": 300, "button": "left", "clicks": 1, "delay_ms": 200, "label": "Login"}
    ],
    "loop": true,
    "loop_count": 5
  },
  "module_b": { ... }
}
```

Individual module saves use `{"version": "1.0", "module": {...}}`.
"# AutoclickerSuckMyClick" 
"# AutoclickerSuckMyClick" 
