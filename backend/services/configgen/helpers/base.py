"""What every pack generator needs: the interface, the give-up type, and the
two write primitives.

Moved verbatim out of controller_profiles.py. The comments travel with the
code, because they are the record of what each line is defending against.
"""
from __future__ import annotations

import shutil
from collections.abc import Collection
from pathlib import Path

from ....utils import atomic_write as _atomic_write
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
    """Keep ONE copy of the file as it was before GameCore first touched it.

    The docstring used to say "copy before EVERY write", which is not what the
    guard below does and not what is wanted. A copy per write would, after two
    connections, hold a backup of a file GameCore had already rewritten — the
    thing worth keeping is the state the owner or the installer left, and the
    second write is exactly when that would be lost.

    A wrong write costs the owner their manual mapping; a truncated one costs
    them the whole config. This answers the first; `atomic_write` answers the
    second.
    """
    b = p.with_name(p.name + ".bak-ctrlmodel")
    if p.is_file() and not b.exists():
        shutil.copy2(p, b)


def atomic_write(p: Path, text: str) -> None:
    """The shared one, re-exported under the name every configgen helper
    imports. The power-cut reasoning lives with the implementation
    (backend/utils.py); what is configgen-specific is only WHEN it bites:
    this pipeline runs at backend startup, the exact moment the box is
    switched on — and off again.
    """
    _atomic_write(p, text)


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
