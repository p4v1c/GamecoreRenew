"""Shared RetroArch generator contract for the Legacy Batch."""
from __future__ import annotations

from pathlib import Path

from backend.services.configgen import inputs
from backend.services.configgen.helpers import retroarch


class Pad:
    vendor = "054c"
    product = "09cc"
    dup_index = 0


def test_semantic_gamecontroller_uses_roster_slot_and_official_probe(tmp_path, monkeypatch):
    target = tmp_path / "x.cfg"
    target.write_text('#include "/etc/retroarch.cfg"\n')
    monkeypatch.setattr(
        retroarch.controllers, "sdl2_probe",
        lambda vendor, product, lib="": {"guid": "0" * 32, "map": "mapped"},
    )
    monkeypatch.setattr(retroarch.controllers, "bundled_sdl2", lambda app: "")
    out = retroarch.generate(
        "probe", 4, 3, Pad(),
        {"target": target, "app_id": "", "snap_dir": tmp_path / "snap"},
    )
    text = target.read_text()
    assert out == "probe: configured P3"
    assert 'input_player3_joypad_index = "2"' in text
    assert 'input_player3_b_btn = "0"' in text
    assert text.index("input_player3_joypad_index") < text.index("#include")


def test_wizard_mapping_becomes_gamecontroller_at_runtime(tmp_path, monkeypatch):
    target = tmp_path / "x.cfg"
    target.write_text("")
    model = inputs.PadInputs("g", "wizard", {"a": inputs.Input("button", 44)})
    monkeypatch.setattr(
        retroarch.controllers, "sdl2_probe",
        lambda vendor, product, lib="": {"guid": "0" * 32},
    )
    monkeypatch.setattr(retroarch.inputs, "for_pad", lambda pad, app_id="": model)
    retroarch.generate(
        "probe", 4, 1, Pad(),
        {"target": target, "app_id": "", "snap_dir": tmp_path / "snap"},
    )
    # Served wizard mappings make SDL recognise the controller; physical b44
    # must not be written where RetroArch expects SDL semantic enums.
    text = target.read_text()
    assert 'input_player1_b_btn = "0"' in text
    assert '"44"' not in text


def test_skip_text_never_contains_absolute_target(tmp_path, monkeypatch):
    target = tmp_path / "ephemeral" / "missing.cfg"
    msg = retroarch.generate(
        "probe", 2, 1, Pad(),
        {"target": target, "app_id": "", "snap_dir": tmp_path / "snap"},
    )
    assert str(tmp_path) not in str(msg)
    assert str(msg) == "probe: controller config is missing"


def test_shared_helper_has_no_private_subprocess_probe():
    import ast
    source = Path(retroarch.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert "subprocess" not in imports
    assert "controllers.sdl2_probe" in source


def test_release_is_a_list_like_every_other_generator(tmp_path):
    """configgen extends its results with release(): None raised TypeError on
    every unplug, and a bare string would be split into characters."""
    target = tmp_path / "nes.cfg"
    assert retroarch.release("nes", 2, 1, {"target": str(target)}) == []
    assert retroarch.release("nes", 2, 5, {"target": str(target)}) == []
    target.write_text('input_player1_a_btn = "0"  # gamecore:p1\n')
    out = retroarch.release("nes", 2, 1, {"target": str(target)})
    assert isinstance(out, list)
