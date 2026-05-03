#!/usr/bin/env python3
"""Run this while an emulator is open to find its WM_CLASS."""
from Xlib import display as xdisplay

d = xdisplay.Display()
root = d.screen().root

IGNORE = {'gnome-shell', 'gsd-xsettings', 'ibus-x11', 'gamecore-electron',
          'electron', 'discord', 'code', 'code - oss'}

atom = d.intern_atom('_NET_CLIENT_LIST')
prop = root.get_full_property(atom, 0)
wids = list(prop.value) if prop else []

print(f"\nClient windows via _NET_CLIENT_LIST ({len(wids)} total):")
print("-" * 60)
for wid in wids:
    try:
        win  = d.create_resource_object('window', wid)
        cls  = win.get_wm_class()
        name = win.get_wm_name()
        if cls:
            key = cls[0].lower()
            marker = '  ← EMULATOR?' if not any(i in key for i in IGNORE) else ''
            print(f"  WM_CLASS : {cls}{marker}")
            print(f"  Title    : {name}")
            print(f"  ID       : {hex(wid)}")
            print()
    except Exception:
        pass
