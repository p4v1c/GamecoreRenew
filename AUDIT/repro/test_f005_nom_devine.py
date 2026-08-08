"""F-005 — un nom de périphérique deviné est écrit dans la config sans un mot.

Famille : échecs silencieux (« toute écriture de configuration faite à partir
d'une valeur devinée »).

`resolve_name()` est une chaîne de repli à quatre étages :

    sdl3_names(...)              la vérité, demandée à libSDL3 en direct
    or SDL3_FALLBACK_NAMES       une table statique de pads connus
    or db_name_for(...)          la base communautaire SDL2
    or evdev_name                le nom brut du noyau

Seul le PREMIER étage signale son échec, et seulement s'il lève :

    except Exception:
        log.warning("configgen: SDL3 enumeration failed — falling back to "
                    "static names", exc_info=True)

Or l'échec le plus courant n'est pas une exception, c'est une ABSENCE : SDL3
répond correctement mais ne connaît pas ce pad-là. Le commentaire de
`SDL3_FALLBACK_NAMES` nomme lui-même le cas — *"the pad went back to sleep
between the evdev scan and this call"*. Dans ce cas `cached` est un dict valide
sans l'entrée, aucune exception n'est levée, et la chaîne descend jusqu'au nom
evdev en silence.

Ce que ça coûte est documenté juste au-dessus, dans le docstring de
`resolve_name` :

    "the SDL2 community-DB name only as a last resort — it is WRONG for SDL3 on
     some pads ('PS5 Controller' vs 'DualSense Wireless Controller'), which
     showed up live in RPCS3.log as 'SDL: Adding empty device' and a dead pad
     in game."

Le nom deviné n'est pas inerte : RPCS3 l'écrit dans `Device:` et Dolphin dans
`Device = SDL/<k>/<nom>`. Une valeur devinée devient donc une config écrite, et
la seule trace visible est dans le journal de l'émulateur, pas dans le nôtre.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp             # noqa: E402
from backend.services.configgen import controllers as cc           # noqa: E402
from backend.tests import characterisation as ch                   # noqa: E402

# Un vendor:product qui n'est ni dans SDL3_FALLBACK_NAMES ni dans
# gamecontrollerdb.txt : la chaîne descend alors jusqu'au dernier étage.
UNKNOWN_VENDOR, UNKNOWN_PRODUCT = "ffff", "fffe"
EVDEV_NAME = "Generic X-Box pad"


@pytest.fixture
def sdl3_muet(monkeypatch):
    """SDL3 répond, sans erreur, et ne connaît pas ce pad.

    C'est le cas que le code n'attrape pas : `sdl3_names` ne logge que sur
    exception, et ici il n'y en a aucune.
    """
    monkeypatch.setattr(cc, "sdl3_names", lambda want=None: {})
    monkeypatch.setattr(cp, "sdl3_names", lambda want=None: {}, raising=False)


def test_le_pad_choisi_est_bien_inconnu_des_deux_tables(sdl3_muet):
    """Garde-fou : si ce vendor:product était connu, la chaîne s'arrêterait
    avant le dernier étage et le test suivant ne prouverait rien."""
    assert (UNKNOWN_VENDOR, UNKNOWN_PRODUCT) not in cc.SDL3_FALLBACK_NAMES
    assert cc.db_name_for(UNKNOWN_VENDOR, UNKNOWN_PRODUCT) is None


def test_sdl3_qui_leve_est_bien_signale(monkeypatch, caplog):
    """Garde-fou : l'étage qui SAIT se plaindre se plaint bien.

    Le constat porte sur l'asymétrie entre ce cas-ci et le suivant, pas sur
    une absence totale de journalisation.
    """
    def boom(*_a, **_k):
        raise RuntimeError("libSDL3 introuvable")

    monkeypatch.setattr(cc, "_sdl3_live_names", boom)
    monkeypatch.setattr(cc, "_sdl3_cache", (0.0, {}))
    with caplog.at_level(logging.WARNING, logger=cc.log.name):
        cc.sdl3_names((UNKNOWN_VENDOR, UNKNOWN_PRODUCT))
    assert any("SDL3" in r.getMessage() for r in caplog.records)


def test_le_repli_sur_le_nom_evdev_laisse_une_trace(sdl3_muet, caplog):
    """LE CONSTAT — rouge sur main.

    SDL3 n'a pas levé, il a simplement répondu sans ce pad. Le nom rendu est
    le nom brut du noyau, que RPCS3 n'utilisera jamais pour nommer le
    périphérique.
    """
    with caplog.at_level(logging.DEBUG, logger=cc.log.name):
        name = cc.resolve_name(UNKNOWN_VENDOR, UNKNOWN_PRODUCT, EVDEV_NAME)

    assert name == EVDEV_NAME, "la chaîne n'est pas descendue au dernier étage"
    assert caplog.records, (
        f"resolve_name() a rendu {EVDEV_NAME!r} — le nom evdev brut, pas un nom "
        f"SDL3 — sans écrire une seule ligne de journal. Ce nom part directement "
        f"dans `Device:` de RPCS3 et dans `Device = SDL/<k>/…` de Dolphin. "
        f"Le docstring de resolve_name dit ce que ça produit : "
        f"'SDL: Adding empty device' et une manette morte en jeu. Seule "
        f"l'exception SDL3 est signalée ; l'absence, qui est le cas courant, "
        f"ne l'est pas.")


def test_le_nom_devine_atterrit_vraiment_dans_la_config(box, sdl3_muet, monkeypatch):
    """La conséquence, mesurée sur l'arbre de seeds réel.

    Ce test est VERT : il ne porte pas le constat, il en établit le coût. Ce
    qui est écrit dans le fichier est bien la valeur devinée.
    """
    monkeypatch.setattr(cc, "pad_has_hat", lambda v, p: True, raising=False)
    cp.apply_profile(1, UNKNOWN_VENDOR, UNKNOWN_PRODUCT, EVDEV_NAME, 0)

    yml = (box / ch.SEED_DEST["rpcs3"] /
           "input_configs/global/Default.yml").read_text()
    assert f"Device: {EVDEV_NAME} 1" in yml, (
        "le nom deviné n'a pas atteint la config RPCS3 — revérifier le chemin "
        "avant de conclure quoi que ce soit du test précédent")
