"""What `scripts/gen-catalog.py` promises: drop a directory, get a system.

That promise was false. The grid order was two lists of ids inside the script,
and the render was `[tile(packs[i]) for i in SYSTEM_ORDER if i in packs]` — so a
pack missing from the list was DROPPED. A new `catalog/<id>/` passed
check-catalog, generated nothing, and appeared neither on the grid nor in the
installer's tick list, with no output saying so. It was documented as working in
the README and in docs/architecture/10.

These tests are the promise, written down.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog.loader import Pack


@pytest.fixture(scope="module")
def gc():
    spec = importlib.util.spec_from_file_location("gen_catalog", ROOT / "scripts" / "gen-catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def packs(gc):
    return gc.load_catalog(ROOT / "catalog", ROOT / "config" / "catalog.d")


def _fake(pid: str, kind: str = "emulator", **extra) -> Pack:
    data = {"id": pid, "kind": kind, "label": "Some Console", "platform": "SOMECON",
            "color": "#1e90ff", "launch": {"path": "flatpak", "args": f"run org.x.{pid}"}}
    if kind == "emulator":
        data["roms"] = {"dir": f"emu/{pid}", "extensions": ["*.bin"]}
    data.update(extra)
    return Pack(id=pid, data=data, path=ROOT / "catalog" / pid, origin="shipped")


# ── the promise ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["emulator", "app"])
def test_a_new_pack_reaches_the_grid_without_being_listed_anywhere(gc, packs, kind):
    """The regression this file exists for. No `order`, no mention in any list."""
    plus = dict(packs, newcomer=_fake("newcomer", kind))
    systems, apps = gc.render(plus)
    rendered = json.loads(systems if kind == "emulator" else apps)
    assert "newcomer" in [t["id"] for t in rendered]


@pytest.mark.parametrize("kind", ["emulator", "app"])
def test_a_new_pack_reaches_the_installer_tick_list(gc, packs, kind):
    """Same failure, other half: baked into the binary at build time, so a pack
    absent here can never be selected, and is therefore never installed."""
    plus = dict(packs, newcomer=_fake("newcomer", kind))
    assert "newcomer" in gc.render_installer_data(plus)


def test_a_pack_with_no_order_sorts_last_rather_than_vanishing(gc, packs):
    """Badly placed is recoverable by editing one file. Absent is not."""
    plus = dict(packs, newcomer=_fake("newcomer"))
    ids = [t["id"] for t in json.loads(gc.render(plus)[0])]
    assert ids[-1] == "newcomer"


def test_order_decides_the_grid(gc, packs):
    """cemu ships with order 1. A newcomer at 0 goes ahead of it, at 99 behind —
    equal orders fall back to the id, which is why this compares to a neighbour
    rather than to position zero."""
    def place(order):
        plus = dict(packs, newcomer=_fake("newcomer", order=order))
        ids = [t["id"] for t in json.loads(gc.render(plus)[0])]
        return ids.index("newcomer"), ids.index("cemu")

    early, cemu_early = place(0)
    late, cemu_late = place(99)
    assert early < cemu_early
    assert late > cemu_late


def test_the_shipped_catalogue_still_declares_its_order(packs):
    """Every pack we ship is placed deliberately. A missing `order` here would
    silently move a console to the end of the grid on the next regeneration."""
    unordered = sorted(p.id for p in packs.values() if "order" not in p.data)
    assert not unordered, f"packs with no order: {unordered}"
