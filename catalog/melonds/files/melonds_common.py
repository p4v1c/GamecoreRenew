"""Constants and logging shared by the melonDS layout toggle modules. Stdlib only."""

import os
import struct
import time

# Offsets for melonDS 1.1 (Flathub net.kuribo64.melonDS, commit 66752a19).
# Only HINTS: validated on attach and re-derived when they no longer fit.
HINT = {"vtable": 0x445790, "sizing": 0x54, "aspect": 0x5C, "numscr": 0x140}

OBJ_WIN = 0x400                    # object window inspected when re-deriving
BLOB_LO, BLOB_HI = 0x50, 0x120     # blob (fallback) mode only

STATE_B = {"sizing": 4, "aspect": 1}     # top screen only, 16:9
STATE_A = {"sizing": 0, "aspect": 0}     # normal DS, 4:3

# Trigger buttons read by the daemon (evdev codes: the same on every pad).
KEY_NAMES = {
    "L3": 0x13d,   # BTN_THUMBL
    "R3": 0x13e,   # BTN_THUMBR
    "L1": 0x136,   # BTN_TL
    "R1": 0x137,   # BTN_TR
    "PS": 0x13c,   # BTN_MODE
    "F":  33,      # KEY_F
}
TRIGGER_KEYCODES = {KEY_NAMES["L3"]}

# Synthetic keyboard key sent to melonDS (recalc mode "uinput"), bound in
# melonDS to Hotkeys → "Swap screen emphasis", KEYBOARD column. F12 by default;
# change with --hotkey-key on conflict.
UINPUT_KEYS = {"F9": 67, "F10": 68, "F11": 87, "F12": 88,
               "F13": 183, "F14": 184, "F15": 185,
               "SCROLLLOCK": 70, "PAUSE": 119}
HOTKEY_CODE = UINPUT_KEYS["F12"]

# The same key as melonDS stores it in its .toml: `getEventKeyVal()` =
# QKeyEvent::key() | modifiers (EmuInstanceInput.cpp). No modifier → the raw
# Qt::Key_* constant.
QT_KEYS = {67: 0x01000038,   # F9
           68: 0x01000039,   # F10
           87: 0x0100003A,   # F11
           88: 0x0100003B,   # F12
           183: 0x0100003C, 184: 0x0100003D, 185: 0x0100003E,   # F13-F15
           70: 0x01000026,   # ScrollLock
           119: 0x01000008}  # Pause

# melonDS config: Flatpak first, native package second.
MELONDS_TOMLS = [
    os.path.expanduser("~/.var/app/net.kuribo64.melonDS/config/melonDS/melonDS.toml"),
    os.path.expanduser("~/.config/melonDS/melonDS.toml"),
]
BINDING = "HK_SwapScreenEmphasis"

# ---- widescreen cheat ------------------------------------------------------
# An Action Replay "widescreen" code renders a 16:9 field of view in the same
# 256x192 framebuffer. In 4:3 it squashes the image, so it must be enabled in
# state B only. melonDS re-reads `code.Enabled` every frame
# (AREngine::RunCheats): a plain bool to flip.
CHEAT_NAME = "WIDESCREEN16_9"      # <= 15 chars → SSO, stored INSIDE the object

# melonDS::ARCode, libstdc++ x86-64 layout:
#   +0x00  ARCodeCat* Parent
#   +0x08  std::string Name         (32 B; SSO buffer at +0x10 of the string)
#   +0x28  std::string Description  (32 B)
#   +0x48  bool Enabled
#   +0x50  std::vector<u32> Code
OFF_NAME, OFF_ENABLED, SSO_OFF = 0x08, 0x48, 0x10

RESCAN_S    = 2.0        # pad hotplug
SCAN_IDLE_S = 3.0        # looking for the melonDS pid
DEBOUNCE_S  = 0.35
SETTLE_S    = 0.30       # time for melonDS to handle the hotkey (1 frame ~17 ms)

CALIB_PATH = os.path.expanduser("~/.config/melonds-layout-toggle/calib.json")
CACHE_PATH = os.path.expanduser("~/.cache/melonds-layout-toggle/offsets.json")

IEV     = struct.Struct("llHHi")     # struct input_event (x86-64)
EV_SYN, EV_KEY = 0x00, 0x01


def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)


def keyname(code):
    return next((k for k, v in UINPUT_KEYS.items() if v == code), str(code))


def expected_numscreens(sizing):
    """TopOnly(4) / BottomOnly(5) → 1 screen; everything else → 2.
    A melonDS invariant independent of the build: validates a candidate."""
    return 1 if sizing in (4, 5) else 2
