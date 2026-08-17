"""Les boutons de face de la Switch se lient par POSITION, pas par lettre.

Nintendo dessine A à droite et B en bas ; SDL — et toute manette que cette
boîte verra — met A en bas et B à droite. Le seed livrait `button_a = A`, qui
ressemble à une identité et n'en est pas une : il branchait le A de la Switch,
dessiné à DROITE de chaque invite à l'écran, sur le bouton du BAS de la
manette.

Rapporté depuis le canapé, DualShock 4 : « X -> O, carré -> triangle ».
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


# ── le seed ──────────────────────────────────────────────────────────────────

def test_le_seed_lie_par_position_sur_les_quatre_slots():
    config = json.loads(SEED.read_text())
    slots = config["input_config"]
    assert len(slots) == 4, "le seed doit décrire les quatre joueurs"
    for entry in slots:
        joycon = entry["right_joycon"]
        got = {k: joycon[k] for k in BY_POSITION}
        assert got == BY_POSITION, (
            f"{entry['player_index']} : {got} — le A de la Switch est à "
            f"droite, il doit venir du bouton droit de la manette (SDL B)")


def test_le_seed_ne_porte_plus_la_table_lettre_pour_lettre():
    config = json.loads(SEED.read_text())
    for entry in config["input_config"]:
        joycon = entry["right_joycon"]
        assert {k: joycon[k] for k in LETTER_IDENTITY} != LETTER_IDENTITY


# ── la réparation de l'existant ──────────────────────────────────────────────

def test_repare_tous_les_slots_pas_seulement_celui_qui_est_profile(gen):
    slots = [_slot(f"Player{n}") for n in range(1, 5)]
    assert gen._repair_face_buttons(slots) == 4
    for entry in slots:
        assert {k: entry["right_joycon"][k] for k in BY_POSITION} == BY_POSITION


def test_ne_touche_pas_une_table_deja_correcte(gen):
    slots = [_slot("Player1", right_joycon=dict(BY_POSITION))]
    assert gen._repair_face_buttons(slots) == 0


def test_respecte_un_remappage_fait_a_la_main(gen):
    """Un propriétaire qui a rebindé ses boutons dans Ryujinx a fait un choix.

    La réparation ne se déclenche que sur la table exacte de l'ancien seed.
    """
    perso = dict(LETTER_IDENTITY) | {"button_a": "Y"}
    slots = [_slot("Player1", right_joycon=perso)]
    assert gen._repair_face_buttons(slots) == 0
    assert slots[0]["right_joycon"]["button_a"] == "Y"


def test_ignore_un_slot_sans_right_joycon(gen):
    """Un slot clavier n'a pas de `right_joycon` — il ne doit pas faire lever
    d'exception sur le chemin de branchement à chaud."""
    slots = [{"backend": "WindowKeyboard", "player_index": "Player1"},
             _slot("Player2")]
    assert gen._repair_face_buttons(slots) == 1


def test_est_idempotent(gen):
    slots = [_slot("Player1")]
    assert gen._repair_face_buttons(slots) == 1
    assert gen._repair_face_buttons(slots) == 0


# ── la garde qui aurait sauté la réparation ──────────────────────────────────

def test_le_retour_anticipe_ne_masque_pas_la_reparation(gen, tmp_path, monkeypatch):
    """Le cas exact de la boîte de référence : id et name déjà bons, boutons
    faux. Sans le `not repaired`, `generate()` sortait sur « already correct »
    et la table restait fausse pour toujours."""
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

    assert result is not None, "la passe ne doit pas sortir sur « already correct »"
    written = json.loads(path.read_text())["input_config"][0]["right_joycon"]
    assert {k: written[k] for k in BY_POSITION} == BY_POSITION
    assert "face buttons" in result
