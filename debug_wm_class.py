#!/usr/bin/env python3
"""Run this while an emulator is open to find its WM_CLASS."""
from Xlib import display as xdisplay

d = xdisplay.Display()
root = d.screen().root

results = []

def scan(win):
    try:
        cls = win.get_wm_class()
        name = win.get_wm_name()
        if cls:
            results.append((cls, name))
    except Exception:
        pass
    try:
        for child in win.query_tree().children:
            scan(child)
    except Exception:
        pass

scan(root)

# Filter out common system windows
IGNORE = {'gnome-shell', 'gsd-xsettings', 'ibus-x11', 'gamecore-electron',
          'electron', 'discord', 'code', 'code - oss'}

print("\nAll app windows (excluding system/DE):")
print("-" * 60)
for cls, name in results:
    key = cls[0].lower() if cls else ''
    if not any(i in key for i in IGNORE):
        print(f"  WM_CLASS : {cls}")
        print(f"  Title    : {name}")
        print()
