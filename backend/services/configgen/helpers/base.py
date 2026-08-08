"""What every pack generator needs: the interface, the give-up type, and the
two write primitives.

Moved verbatim out of controller_profiles.py. The comments travel with the
code, because they are the record of what each line is defending against.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Collection
from pathlib import Path
from typing import Protocol


class Skip(str):
    """Why a step wrote nothing — a real answer, not an absence of one.

    Every writer used to return `str | None`, and apply_profile only collected
    the truthy ones. So "I retargeted Player 2" reached the log and "there is
    no Player 1 pad to clone from" reached nobody: a give-up was byte-for-byte
    indistinguishable from a success. RPCS3's players 2-4 sat dead for a week
    that way, and `scan_mapping()` answered `{"ok": True}` on a snapshot it had
    taken of the wrong controller.

    A Skip is a str, so it logs and joins like any other message; it is a
    distinct type, so apply_profile can file it apart and log it as a warning.
    `None` keeps its old meaning and only it: nothing to do, nothing to say.
    """
    __slots__ = ()


def backup(p: Path) -> None:
    """Copy before EVERY write. A wrong write costs the user their manual
    mapping; a truncated one costs them the whole config."""
    b = p.with_name(p.name + ".bak-ctrlmodel")
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)


def atomic_write(p: Path, text: str) -> None:
    """Write through a temp file in the same directory, then os.replace().

    `write_text()` truncates first and writes second. This pipeline runs at
    backend startup — the exact moment someone powers the box on, and the exact
    moment they can cut the power again with the wall switch. A Config.json
    caught between the two is invalid JSON, and Ryujinx starts over from
    defaults. os.replace() is atomic within a filesystem, so a reader sees
    either the whole old file or the whole new one.
    """
    tmp = p.with_name(p.name + ".gamecore-tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, p)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


class Generator(Protocol):
    """What a pack's `generator.py` exposes.

    Writes ONLY the sections GameCore owns and leaves the rest of the file
    intact, to the byte. That is the deliberate divergence from Batocera, which
    regenerates everything at launch: it would erase the owner's own tweaks,
    which contradicts the whole `.bak-preinstall` / snapshot_restore design.
    """

    def generate(self, player_index: int, pad, opts: dict) -> str | None:
        """Return a message describing what was written, a `Skip` explaining
        why nothing was, or None for "nothing to do"."""
        ...

    def release(self, player_index: int, opts: dict,
                occupied: Collection[int] = ()) -> list[str]:
        """Un-write the slot, touching only the sections GameCore owns.

        `occupied` is the roster that remains. A generator whose emulator
        stores anything about the roster rather than about the slot — a
        multitap, a port count — cannot answer without it, and one that stores
        nothing of the sort simply ignores it.
        """
        ...
