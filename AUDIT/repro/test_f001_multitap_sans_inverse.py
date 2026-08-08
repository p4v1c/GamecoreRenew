"""F-001 — le multitap s'allume tout seul et ne s'éteint jamais.

Famille : écriture sans inverse.

`tier0.apply()` écrit la clé multitap dès qu'un joueur >= `fromPlayer` arrive
(PCSX2 `Pad/MultitapPort1 = true`, DuckStation `ControllerPorts/MultitapMode =
Port1Only`). C'est correct : sans ça le slot 3 est refusé au niveau SIO2 et le
troisième joueur ne peut pas bouger.

Mais `release_profile()` ne traverse que les générateurs qui exposent
`release()`, et seul dolphin en a un. Donc la clé reste à `true` pour toujours,
y compris après que le troisième joueur soit parti.

Le test ne nomme aucun pack : il interroge le catalogue pour trouver les packs
qui DÉCLARENT un bloc `controllers.multitap`, exactement comme demandé.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp    # noqa: E402
from backend.tests import characterisation as ch          # noqa: E402


def _packs_declaring_a_multitap():
    """Les packs dont le pack.json déclare `controllers.multitap`.

    Lu depuis le catalogue, jamais codé en dur : un pack ajouté demain avec un
    multitap est couvert sans que personne ait à éditer une liste.
    """
    out = []
    for pack_dir in sorted((ROOT / "catalog").iterdir()):
        meta_path = pack_dir / "pack.json"
        if pack_dir.name.startswith("_") or not meta_path.is_file():
            continue
        ctl = (json.loads(meta_path.read_text()).get("controllers") or {})
        tap = ctl.get("multitap")
        if tap:
            out.append((pack_dir.name, ctl, tap))
    return out


MULTITAP_PACKS = _packs_declaring_a_multitap()
assert MULTITAP_PACKS, "aucun pack ne déclare de multitap — le catalogue a bougé"


def _watched_file(home: Path, pack_id: str) -> Path:
    """Le fichier de config que le harnais surveille pour ce pack."""
    rels = ch.WATCHED[pack_id]
    assert len(rels) == 1, f"{pack_id} surveille plusieurs fichiers"
    return home / rels[0]


@pytest.mark.parametrize("pack_id,ctl,tap", MULTITAP_PACKS,
                         ids=[p[0] for p in MULTITAP_PACKS])
def test_le_multitap_est_bien_allume_par_le_slot_declencheur(box, pack_id, ctl, tap):
    """Garde-fou : on vérifie d'abord que l'écriture a lieu.

    Sans ça, le test suivant pourrait passer au vert parce que rien n'écrit
    jamais rien — un test vacant, exactement ce que la passe 5 traque.
    """
    from_player = tap["fromPlayer"]
    pad = ch.PADS["ds4"]
    cp.apply_profile(from_player, pad.vendor, pad.product, pad.evdev_name, 0)

    text = _watched_file(box, pack_id).read_text()
    assert f"{tap['key']} = {tap['value']}" in text, (
        f"{pack_id}: le slot {from_player} n'a pas allumé le multitap — "
        f"la prémisse du constat est fausse, revérifier tier0.apply()")


@pytest.mark.parametrize("pack_id,ctl,tap", MULTITAP_PACKS,
                         ids=[p[0] for p in MULTITAP_PACKS])
def test_relacher_le_dernier_slot_multitap_eteint_le_multitap(box, pack_id, ctl, tap):
    """LE CONSTAT — rouge sur main.

    Scénario : une session à trois joueurs, puis les joueurs 3 (et au-delà)
    s'en vont. Une fois qu'aucun slot au-dessus de `fromPlayer` n'est occupé,
    l'accessoire virtuel n'a plus de raison d'être branché — mais il l'est
    encore, parce que rien ne l'éteint jamais.
    """
    max_players = ctl["maxPlayers"]
    target = _watched_file(box, pack_id)

    before = target.read_text()
    assert f"{tap['key']} = {tap['value']}" not in before, (
        f"{pack_id}: le seed livre déjà le multitap allumé — le constat serait vide")

    pad = ch.PADS["ds4"]
    for slot in range(1, max_players + 1):
        cp.apply_profile(slot, pad.vendor, pad.product, pad.evdev_name, slot - 1)

    # Tout le monde débranche, du dernier au premier.
    for slot in range(max_players, 0, -1):
        cp.release_profile(slot)

    after = target.read_text()
    assert f"{tap['key']} = {tap['value']}" not in after, (
        f"{pack_id}: après le départ de tous les joueurs, "
        f"[{tap['section']}] {tap['key']} vaut toujours {tap['value']!r}. "
        f"release_profile() n'a aucun inverse pour cette écriture : seul "
        f"dolphin expose release(). La box garde un multitap virtuel branché "
        f"pour toutes les sessions solo suivantes.")
