"""Switch face buttons bind by POSITION, not by letter.

Nintendo draws A on the right and B at the bottom; SDL (and every pad this box
sees) puts A at the bottom and B on the right. The seed shipped
`button_a = A`, which wired the Switch's right-hand A to the pad's BOTTOM
button. Reported from the couch, DualShock 4: "X -> O, square -> triangle".
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "catalog/ryujinx/seed/Config.json"

BY_POSITION = {"button_a": "B", "button_b": "A", "button_x": "Y", "button_y": "X"}
LETTER_IDENTITY = {"button_a": "A", "button_b": "B", "button_x": "X", "button_y": "Y"}


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location(
        "ryu_gen", ROOT / "catalog/ryujinx/generator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _slot(player: str, **overrides) -> dict:
    entry = {
        "backend": "GamepadSDL2",
        "player_index": player,
        "id": "",
        "name": "",
        "right_joycon": dict(LETTER_IDENTITY),
    }
    entry.update(overrides)
    return entry


# ── the seed ─────────────────────────────────────────────────────────────────────

def test_seed_binds_by_position_on_all_four_slots():
    config = json.loads(SEED.read_text())
    slots = config["input_config"]
    assert len(slots) == 4, "the seed must describe four players"
    for entry in slots:
        joycon = entry["right_joycon"]
        got = {k: joycon[k] for k in BY_POSITION}
        assert got == BY_POSITION, (
            f"{entry['player_index']}: {got} — the Switch's A is on the right, "
            f"it must come from the pad's right button (SDL B)")


def test_seed_no_longer_carries_the_letter_identity_table():
    config = json.loads(SEED.read_text())
    for entry in config["input_config"]:
        joycon = entry["right_joycon"]
        assert {k: joycon[k] for k in LETTER_IDENTITY} != LETTER_IDENTITY


# ── repairing an existing config ─────────────────────────────────────────────

def test_repairs_every_slot_not_only_the_profiled_one(gen):
    slots = [_slot(f"Player{n}") for n in range(1, 5)]
    assert gen._repair_face_buttons(slots) == 4
    for entry in slots:
        assert {k: entry["right_joycon"][k] for k in BY_POSITION} == BY_POSITION


def test_leaves_a_correct_table_alone(gen):
    slots = [_slot("Player1", right_joycon=dict(BY_POSITION))]
    assert gen._repair_face_buttons(slots) == 0


def test_respects_a_hand_made_remap(gen):
    """A remap made in Ryujinx is a choice: repair only the old seed's exact table."""
    custom = dict(LETTER_IDENTITY) | {"button_a": "Y"}
    slots = [_slot("Player1", right_joycon=custom)]
    assert gen._repair_face_buttons(slots) == 0
    assert slots[0]["right_joycon"]["button_a"] == "Y"


def test_skips_a_slot_without_right_joycon(gen):
    """A keyboard slot has no `right_joycon`; it must not raise on hotplug."""
    slots = [{"backend": "WindowKeyboard", "player_index": "Player1"},
             _slot("Player2")]
    assert gen._repair_face_buttons(slots) == 1


def test_is_idempotent(gen):
    slots = [_slot("Player1")]
    assert gen._repair_face_buttons(slots) == 1
    assert gen._repair_face_buttons(slots) == 0


# ── the guard that would have skipped the repair ─────────────────────────────────

def test_early_return_does_not_hide_the_repair(gen, tmp_path, monkeypatch):
    """Reference box case: id and name already right, buttons wrong. Without
    `not repaired`, `generate()` returned on "already correct" forever."""
    guid = "00000003-054c-0000-cc09-000000006800"
    cfg = {"input_config": [_slot("Player1", id=f"0-{guid}",
                                  name="PS4 Controller (0)")]}
    path = tmp_path / "Config.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n")

    class Pad:
        vendor, product, dup_index, name = "054c", "09cc", 0, "PS4 Controller"

        def guid_for(self, _app_id):
            return guid, ""

    monkeypatch.setattr(gen, "backup", lambda _p: None)
    result = gen.generate(1, Pad(), {"target": path, "app_id": ""})

    assert result is not None, "the pass must not stop on 'already correct'"
    written = json.loads(path.read_text())["input_config"][0]["right_joycon"]
    assert {k: written[k] for k in BY_POSITION} == BY_POSITION
    assert "face buttons" in result
