# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build for the graphical installer.
#
# A .spec rather than a CLI invocation because there is no command-line flag to
# keep a library OUT of a bundle, and this binary has to keep several out.
#
# The bug that produced this file: every letter typed into any field of the
# wizard was a SIGSEGV. Core dump, PID 6488:
#
#     #0  /tmp/_MEIXnq5gc/libxkbcommon.so.0 + 0x20525          ← bundled
#     #1  /tmp/_MEIXnq5gc/libxkbcommon.so.0 + 0x215f2
#     #2  /tmp/_MEIXnq5gc/PySide6/Qt/lib/libQt6XcbQpa.so.6 + 0x67c57
#
# libxkbcommon and libxkbcommon-x11 are two halves of one library and share
# private structures across their boundary. PyInstaller bundled the first half
# from the Ubuntu 24.04 runner, could not see the second (nothing links it
# directly — Qt dlopens it), and left it to come from the host. _MEIPASS goes to
# the FRONT of the search path, so a Manjaro box ran its own
# libxkbcommon-x11 1.13.2 against a 1.6 libxkbcommon from the bundle. Neither is
# broken; the pair is. It only shows on the first key event, because that is the
# first thing to cross between the two halves — the window paints and the mouse
# works right up until then.
#
# The same split exists for libX11/libX11-xcb and for libxcb and its extension
# libraries, and the same runner-vs-rolling-distro version gap applies to them,
# so they are excluded on the same grounds rather than waiting for their turn.
# The host provides all of them: they are a hard requirement of any X11 session,
# which is what this installer is run from.
#
# Build:  pyinstaller --noconfirm --clean gamecore-installer.spec
# Output: dist/gamecore-installer

a = Analysis(
    ['gamecore_installer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Matched on the bundle's destination name, which is the SONAME
# ('libxkbcommon.so.0'), hence prefixes rather than exact names.
HOST_PROVIDED = (
    'libxkbcommon.so',
    'libxkbcommon-x11.so',
    'libX11.so',
    'libX11-xcb.so',
    'libxcb.so',
    'libxcb-',
)

a.binaries = [b for b in a.binaries
              if not any(b[0].startswith(p) for p in HOST_PROVIDED)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='gamecore-installer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
