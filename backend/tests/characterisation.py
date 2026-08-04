"""Characterisation harness for the controller pipeline.

The mandatory gate before phase 4 moves a single line: capture what
`apply_profile` writes TODAY, for a matrix of pad × emulator × slot, and lock it
in. The refactor must reproduce it byte for byte. A divergence is a bug in the
refactor, not an improvement — unless it is argued against one of the documented
invariants.

This module is the harness only; `test_controller_characterisation.py` runs it.
`--update` on that test regenerates the fixtures, which is deliberately a
separate, explicit act.

## What is faked, and what is not

The per-emulator config trees are built from the REAL seeds
(`catalog/<id>/seed/`), so the "before" state is what a fresh install actually
has. Nothing is invented.

SDL is stubbed, because it must be: `resolve_name()` asks the system's libSDL3
about the pads physically connected, and `_sdl2_probe()` shells out to whichever
SDL2 an emulator bundles. Both answers are machine- and moment-dependent. The
values below are not invented either — they were MEASURED on the reference box
(see docs/proposals/01-catalog-packs.md §5.0):

    DualShock 4  054c:09cc   SDL3 "PS4 Controller"
                             Ryujinx's bundled SDL2 GUID 03008fe54c05...6800
    Xbox One S   045e:02fd   SDL3 "Xbox One Wireless Controller"
                             bundled SDL2 GUID 050018dc5e04...0000
    DualSense    054c:0ce6   SDL3 "DualSense Wireless Controller"

The DualSense line is the one pad not connected during the measurements; its
name comes from SDL3_FALLBACK_NAMES, which is what the code itself would use.
It is here because the mixed-model case is the one that matters and two pads of
different families were not enough to exercise three.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog"


@dataclass(frozen=True)
class Pad:
    key: str
    vendor: str
    product: str
    evdev_name: str
    sdl3_name: str
    sdl2_guid: str          # what the emulator's OWN SDL2 reports


# Measured on the reference box, two pads connected. See the module docstring.
DS4 = Pad("ds4", "054c", "09cc", "Wireless Controller", "PS4 Controller",
          "03008fe54c050000cc09000000006800")
# "Xbox One Controller", not "Xbox One Wireless Controller". The difference is
# SDL_GAMECONTROLLERCONFIG_FILE: SDL3's built-in HIDAPI name is the second, but
# the community DB overrides it with the first — and process_manager.py:180
# exports that variable to every emulator it launches, so the first is what
# RPCS3 and Dolphin actually enumerate. `_sdl3_live_names()` sets the same
# variable for exactly that reason.
#
# Measured both ways on the reference box. The first version of this file used
# the built-in name, taken from a probe that did not mirror the launch
# environment — a fixture that was self-consistent and would never have matched
# a real box.
XBOX = Pad("xbox", "045e", "02fd", "Xbox Wireless Controller",
           "Xbox One Controller", "050018dc5e040000fd02000003090000")
DUALSENSE = Pad("dualsense", "054c", "0ce6", "DualSense Wireless Controller",
                "DualSense Wireless Controller",
                "030000004c050000e60c000011810000")

PADS = {p.key: p for p in (DS4, XBOX, DUALSENSE)}


@dataclass(frozen=True)
class Step:
    """One call. `release` means release_profile instead of apply_profile."""
    pad: str | None
    slot: int
    dup: int = 0
    release: bool = False


@dataclass(frozen=True)
class Scenario:
    name: str
    why: str
    steps: tuple[Step, ...]


# ── The matrix ─────────────────────────────────────────────────────────────
# 1, 2, 3 and 4 pads; a mixed-model roster; and a hot unplug of player 2
# followed by a replug — the three cases docs/architecture/08 says break most
# often. `dup` is passed exactly as gamepad_monitor computes it: how many pads
# with the same RESOLVED NAME already sit in a lower slot.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario("one-ds4", "a single DualShock 4 — dup 0, the common case",
             (Step("ds4", 1),)),
    Scenario("one-xbox", "a single Xbox pad — a different SDL3 name entirely",
             (Step("xbox", 1),)),
    Scenario("one-dualsense", "the pad whose SDL3 name the community DB gets wrong",
             (Step("dualsense", 1),)),
    Scenario("ds4-in-slot-2", "one DS4 as Player 2: dup stays 0. RPCS3 writes "
                              "'PS4 Controller 1' and Dolphin SDL/0/ even so — "
                              "the number is NOT the player slot",
             (Step("ds4", 2),)),
    Scenario("two-ds4", "two identical pads: the second is dup 1",
             (Step("ds4", 1, 0), Step("ds4", 2, 1))),
    Scenario("two-mixed", "DS4 + Xbox: different names, so BOTH are dup 0. "
                          "A homogeneous test passes even when this is wrong",
             (Step("ds4", 1, 0), Step("xbox", 2, 0))),
    Scenario("three-mixed", "DS4 + DualSense + Xbox — the case the brief calls "
                            "the one that counts. Slot 3 also turns the "
                            "multitap on for PS1/PS2",
             (Step("ds4", 1, 0), Step("dualsense", 2, 0), Step("xbox", 3, 0))),
    Scenario("four-ds4", "four identical pads: dup 0..3, and the multitap",
             (Step("ds4", 1, 0), Step("ds4", 2, 1),
              Step("ds4", 3, 2), Step("ds4", 4, 3))),
    Scenario("four-mixed", "three families across four slots",
             (Step("ds4", 1, 0), Step("xbox", 2, 0),
              Step("dualsense", 3, 0), Step("ds4", 4, 1))),
    Scenario("slot-3-only", "a lone pad handed slot 3: the multitap must still "
                            "be enabled or the player cannot move",
             (Step("ds4", 3, 0),)),
    Scenario("slot-4-only", "same for slot 4",
             (Step("xbox", 4, 0),)),
    Scenario("unplug-player-2", "co-op, then player 2 leaves. Dolphin's Wiimote "
                                "keeps an emulated remote presented to the game "
                                "unless the slot is released",
             (Step("ds4", 1, 0), Step("xbox", 2, 0), Step(None, 2, release=True))),
    Scenario("unplug-then-replug", "the survivor's dup describes the ROSTER, so "
                                   "the slot is re-profiled on the way back",
             (Step("ds4", 1, 0), Step("ds4", 2, 1), Step(None, 2, release=True),
              Step("ds4", 2, 1))),
    Scenario("idempotence-ds4", "the same call twice: the second must write "
                                "NOTHING. _ryujinx used to rewrite 11 KB on "
                                "every connection",
             (Step("ds4", 1, 0), Step("ds4", 1, 0))),
)

# Files the profilers touch, relative to the fake HOME / install root. The
# backups (*.bak-ctrlmodel) are deliberately NOT captured: they are copies of
# the input, and comparing them would only restate the fixtures.
WATCHED = {
    "ryujinx": [".var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json"],
    "dolphin": [".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini",
                ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/WiimoteNew.ini"],
    "rpcs3": [".var/app/net.rpcs3.RPCS3/config/rpcs3/input_configs/global/Default.yml"],
    "pcsx2": [".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/PCSX2.ini"],
    "duckstation": [".local/share/duckstation/settings.ini"],
    "melonds": [".var/app/net.kuribo64.melonDS/config/melonDS/melonDS.toml"],
}

# Where each pack's seed lands in the fake HOME.
SEED_DEST = {
    "ryujinx": ".var/app/io.github.ryubing.Ryujinx/config/Ryujinx",
    "dolphin": ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu",
    "rpcs3": ".var/app/net.rpcs3.RPCS3/config/rpcs3",
    "pcsx2": ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis",
    "duckstation": ".local/share/duckstation",
    "melonds": ".var/app/net.kuribo64.melonDS/config/melonDS",
}


def build_tree(home: Path) -> None:
    """Deploy every seed into a fake HOME — the state a fresh install has."""
    for pack_id, rel in SEED_DEST.items():
        src = CATALOG / pack_id / "seed"
        if not src.is_dir():
            continue
        dest = home / rel
        dest.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if f.is_file():
                target = dest / f.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)


def install_stubs(cp, home: Path, monkeypatch) -> None:
    """Point the pipeline at the fake tree and make SDL deterministic.

    Both seam sets are patched, deliberately. Before phase 4 the paths and the
    SDL calls lived on `controller_profiles`; after it they live on
    `configgen` and `configgen.controllers`. Patching both, tolerantly, is what
    lets the SAME harness and the SAME fixtures run on either side of the move
    — which is the only thing that makes "byte for byte" mean anything.
    """
    from backend.services import configgen
    from backend.services.configgen import controllers as cc

    # ── post-refactor seams ────────────────────────────────────────────────
    monkeypatch.setattr(configgen, "HOME", home, raising=False)
    monkeypatch.setattr(configgen, "SNAP_DIR", home / "snapshots", raising=False)
    monkeypatch.setattr(configgen, "_generator_cache", {}, raising=False)

    # ── pre-refactor seams (no-ops once they are gone) ─────────────────────
    for attr, value in (
        ("HOME", home),
        ("RYUJINX_CFG", home / SEED_DEST["ryujinx"] / "Config.json"),
        ("DOLPHIN_DIR", home / SEED_DEST["dolphin"]),
        ("DUCK_INI", home / SEED_DEST["duckstation"] / "settings.ini"),
        ("AZAHAR", home / "azahar-absent.ini"),
        ("CEMU_PROFILES", home / "cemu-absent"),
        ("RMG_CFG", home / "rmg-absent.cfg"),
        ("SNAP_DIR", home / "snapshots"),
        ("rpcs3_default",
         lambda: home / SEED_DEST["rpcs3"] / "input_configs/global/Default.yml"),
        ("pcsx2_ini", lambda: home / SEED_DEST["pcsx2"] / "PCSX2.ini"),
        ("melonds_toml", lambda: home / SEED_DEST["melonds"] / "melonDS.toml"),
        ("mgba_config", lambda: home / "mgba-absent.ini"),
    ):
        monkeypatch.setattr(cp, attr, value, raising=False)

    by_vp = {(p.vendor, p.product): p for p in PADS.values()}

    def names(want=None):
        return {(p.vendor, p.product): p.sdl3_name for p in PADS.values()}

    def probe(vendor, product, lib=""):
        pad = by_vp.get((vendor.lower(), product.lower()))
        if pad is None:
            return {}
        # A GameController mapping matching what SDL reports for these pads —
        # melonDS binds raw joystick values and reads exactly this.
        mapping = ("leftshoulder:b9,rightshoulder:b10,start:b6,back:b4,"
                   "dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2"
                   if pad.vendor == "054c" else
                   "leftshoulder:b6,rightshoulder:b7,start:b11,back:b15,"
                   "dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2")
        return {"guid": pad.sdl2_guid,
                "map": f"{pad.sdl2_guid},{pad.sdl3_name},{mapping},"}

    for module, probe_name in ((cp, "_sdl2_probe"), (cc, "sdl2_probe")):
        monkeypatch.setattr(module, "sdl3_names", names, raising=False)
        monkeypatch.setattr(module, probe_name, probe, raising=False)
        monkeypatch.setattr(module, "bundled_sdl2",
                            lambda app_id: "/stub/libSDL2.so", raising=False)
        # `guid_for` refuses to answer when it cannot locate the flatpak, so
        # that it never hands back the HOST's GUID — the host disagrees with
        # Ryujinx's own SDL2 on the bus byte. That seam was added after this
        # harness was written, and it is not deterministic: it shells out to
        # `flatpak info`. Left unstubbed, the fixtures replayed differently
        # depending on whether the machine happened to have Ryujinx installed
        # — green here, red on a clean runner, which is exactly backwards.
        # A scenario declares its environment; it does not inherit ours.
        monkeypatch.setattr(module, "flatpak_location",
                            lambda app_id: "/stub/flatpak", raising=False)
    # evdev is not available in CI and the pads are not there anyway.
    monkeypatch.setattr(cp, "_pad_has_hat", lambda v, p: True, raising=False)
    monkeypatch.setattr(cc, "pad_has_hat", lambda v, p: True, raising=False)


def run_scenario(cp, scenario: Scenario) -> list[str]:
    """Execute the steps, returning the messages each call produced."""
    messages: list[str] = []
    for step in scenario.steps:
        if step.release:
            messages.append(f"release({step.slot}): "
                            + "; ".join(cp.release_profile(step.slot)))
            continue
        pad = PADS[step.pad]
        result = cp.apply_profile(step.slot, pad.vendor, pad.product,
                                  pad.evdev_name, step.dup)
        messages.append(f"apply({pad.key}, P{step.slot}, dup{step.dup}): "
                        + "; ".join(sorted(result)))
        if result.skipped:
            messages.append("    skipped: " + "; ".join(sorted(result.skipped)))
    return messages


def snapshot(home: Path) -> dict[str, dict[str, str]]:
    """{pack_id: {filename: contents}} for every watched file that exists."""
    out: dict[str, dict[str, str]] = {}
    for pack_id, rels in WATCHED.items():
        files = {}
        for rel in rels:
            p = home / rel
            if p.is_file():
                files[Path(rel).name] = p.read_text(encoding="utf-8")
        if files:
            out[pack_id] = files
    return out


def fixture_dir(pack_id: str, scenario: str) -> Path:
    """Fixtures live WITH the pack — a pack's tests arrive with the pack."""
    return CATALOG / pack_id / "tests" / "fixtures" / scenario
