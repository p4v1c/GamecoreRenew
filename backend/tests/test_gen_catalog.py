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
    """Compared against a neighbour picked from the catalogue, never a named
    one: reordering the grid is a legitimate change and must not fail this."""
    emulators = sorted((p for p in packs.values() if p.kind == "emulator"),
                       key=lambda p: p.data.get("order", 10_000))
    middle = emulators[len(emulators) // 2]
    its_order = middle.data["order"]

    def place(order):
        plus = dict(packs, newcomer=_fake("newcomer", order=order))
        ids = [t["id"] for t in json.loads(gc.render(plus)[0])]
        return ids.index("newcomer"), ids.index(middle.id)

    before, neighbour = place(its_order - 1)
    assert before < neighbour
    after, neighbour = place(its_order + 1)
    assert after > neighbour


def test_the_shipped_catalogue_still_declares_its_order(packs):
    """Every pack we ship is placed deliberately. A missing `order` here would
    silently move a console to the end of the grid on the next regeneration."""
    unordered = sorted(p.id for p in packs.values() if "order" not in p.data)
    assert not unordered, f"packs with no order: {unordered}"


# ── the same promise, for the controller pipeline ──────────────────────────

def test_a_new_pack_is_profiled_without_being_listed_anywhere(packs):
    """The other half of the same bug, and the nastier one.

    `configgen.profilable_packs` walked a tuple of ten ids and used
    `packs.get(pid)`, so an emulator absent from it was never profiled: it
    shipped a generator.py and a controllers block, and its bindings were
    silently never written. The only symptom is a pad that does nothing, in
    that one emulator, on a real box.
    """
    from backend.services.configgen import profilable_packs

    newcomer = _fake("newcomer", controllers={"maxPlayers": 4,
                                              "strategy": "snapshot-restore"})
    got = [p.id for p in profilable_packs(dict(packs, newcomer=newcomer))]
    assert "newcomer" in got
    assert got[-1] == "newcomer", "no declared order means last, not missing"


def test_a_pack_that_profiles_nothing_stays_out(packs):
    """`strategy: none` is a declaration, not an omission."""
    from backend.services.configgen import profilable_packs

    quiet = _fake("quiet", controllers={"maxPlayers": 0, "strategy": "none"})
    assert "quiet" not in [p.id for p in profilable_packs(dict(packs, quiet=quiet))]
