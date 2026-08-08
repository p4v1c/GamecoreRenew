"""F-003 — `release_profile()` ignore les slots hors 1-4 sans un mot.

Famille : échecs silencieux.

`apply_profile()` traite exactement le même cas et le LOGGE, avec un commentaire
qui explique pourquoi :

    # The slot cap is deliberate, but a 5th pad used to get a player
    # number, a TV toast, and no config at all, without a word anywhere.
    log.warning("configgen: player %d is outside the 1-4 slots this box "
                "profiles — %s:%s left unconfigured", ...)

`release_profile()`, huit lignes plus bas, fait `return []` et se tait. La leçon
a été apprise d'un côté de la paire seulement.

Ce n'est pas symétrique par accident : c'est le même plafond, décidé au même
endroit, pour la même raison. Le jour où `maxPlayers` d'un pack passe à 8 — ce
que le schéma du catalogue autorise déjà — la libération redevient inopérante
et rien ne le signale.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp    # noqa: E402
from backend.tests import characterisation as ch          # noqa: E402

OUT_OF_RANGE = 5


def test_apply_profile_dit_pourquoi_il_ne_fait_rien(box, caplog):
    """Garde-fou : la moitié bavarde de la paire.

    Si ce test devenait rouge, c'est la prémisse du constat qui aurait bougé et
    non le défaut qui aurait été corrigé.
    """
    pad = ch.PADS["ds4"]
    with caplog.at_level(logging.WARNING):
        result = cp.apply_profile(OUT_OF_RANGE, pad.vendor, pad.product,
                                  pad.evdev_name, 0)

    assert list(result) == []
    # getMessage(), pas .message : ce dernier n'existe qu'après formatage et
    # vaut AttributeError sur un enregistrement brut — le test a été rouge une
    # fois pour cette raison, ce qui n'était pas le défaut cherché.
    assert any(str(OUT_OF_RANGE) in r.getMessage() for r in caplog.records), (
        "apply_profile ne logge plus le dépassement de slot — le constat F-003 "
        "compare les deux moitiés d'une paire, vérifier laquelle a changé")


def test_release_profile_dit_pourquoi_il_ne_fait_rien(box, caplog):
    """LE CONSTAT — rouge sur main.

    Même plafond, même décision, aucun signal.
    """
    with caplog.at_level(logging.DEBUG):
        result = cp.release_profile(OUT_OF_RANGE)

    assert list(result) == []
    assert caplog.records, (
        f"release_profile({OUT_OF_RANGE}) rend [] et n'émet AUCUN enregistrement "
        f"de journal, à aucun niveau. apply_profile traite le même cas au même "
        f"endroit et le logge en warning. Si maxPlayers d'un pack passe au-delà "
        f"de 4, la libération redevient inopérante en silence — exactement la "
        f"panne que le commentaire d'apply_profile dit avoir déjà coûté une "
        f"fois ('a 5th pad used to get a player number, a TV toast, and no "
        f"config at all, without a word anywhere').")


@pytest.mark.parametrize("slot", [0, -1, OUT_OF_RANGE, 99])
def test_release_profile_est_muet_sur_toute_la_plage_refusee(box, caplog, slot):
    """Le constat n'est pas une singularité de la valeur 5."""
    with caplog.at_level(logging.DEBUG):
        cp.release_profile(slot)
    assert caplog.records, f"release_profile({slot}) : aucun journal"
