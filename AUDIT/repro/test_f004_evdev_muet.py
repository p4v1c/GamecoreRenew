"""F-004 — quand evdev est inaccessible, la boîte n'a plus aucune manette et ne
le dit nulle part.

Famille : échecs silencieux.

`_find_gamepad_devices()` a deux sorties « il n'y a rien » qui ne sont pas des
constats d'absence mais des échecs :

    try:
        import evdev
    except ImportError:
        return {}                    # ← le module manque

    ...
        except (PermissionError, OSError):
            pass                     # ← chaque device refusé, un par un

Les deux rendent un dictionnaire vide, exactement comme « aucune manette n'est
branchée ». La boucle appelante ne distingue pas les deux : `was != live` est
faux, `_reconcile` n'est pas appelé, aucune ligne de journal n'est écrite.

Le docstring de la fonction ANTICIPE pourtant le cas :

    "Scans /dev/input/event* directly instead of relying on
     evdev.list_devices(), which reads /proc/bus/input/devices and may be
     inaccessible without input group."

Le groupe `input` manquant est donc un mode de panne connu, et c'est celui qui
ne produit aucun signal. Depuis le canapé : la manette ne fait rien, dans le
menu comme dans les jeux, et le journal est vide.
"""
from __future__ import annotations

import glob as glob_module
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import gamepad_monitor as gm       # noqa: E402

BTN_SOUTH = 0x130
FAKE_PATHS = ["/dev/input/event3", "/dev/input/event5"]


class _Pad:
    """Une manette qui répond normalement — pour le garde-fou."""

    def __init__(self, path):
        self.path, self.name, self.uniq = path, "Wireless Controller", "aa:bb"
        self.info = types.SimpleNamespace(vendor=0x054C, product=0x09CC,
                                          bustype=0x05)

    def capabilities(self):
        return {gm.EV_KEY: [BTN_SOUTH]}

    def close(self):
        pass


@pytest.fixture
def evdev_qui_refuse(monkeypatch):
    """evdev est là, les devices sont là, et chaque ouverture est refusée.

    C'est la boîte dont l'utilisateur du backend n'est pas dans le groupe
    `input` — le mode de panne que le docstring de la fonction nomme.
    """
    def refuse(path):
        raise PermissionError(13, "Permission denied", path)

    module = types.ModuleType("evdev")
    module.InputDevice = refuse
    module.list_devices = lambda: list(FAKE_PATHS)
    monkeypatch.setitem(sys.modules, "evdev", module)
    monkeypatch.setattr(gm.glob, "glob", lambda pattern: list(FAKE_PATHS))
    gm._logged_no_guide.clear()


@pytest.fixture
def evdev_normal(monkeypatch):
    module = types.ModuleType("evdev")
    module.InputDevice = _Pad
    module.list_devices = lambda: list(FAKE_PATHS)
    monkeypatch.setitem(sys.modules, "evdev", module)
    monkeypatch.setattr(gm.glob, "glob", lambda pattern: list(FAKE_PATHS))
    gm._logged_no_guide.clear()


def test_une_manette_lisible_est_bien_detectee(evdev_normal):
    """Garde-fou : le harnais du test trouve bien des manettes quand tout va
    bien. Sans lui, le test du constat serait vert pour la mauvaise raison —
    un dictionnaire vide parce que le faux evdev ne marche pas."""
    assert set(gm._find_gamepad_devices()) == set(FAKE_PATHS)


def test_le_refus_de_permission_est_bien_total(evdev_qui_refuse):
    """Garde-fou : dans ce scénario la boîte perd VRAIMENT toutes ses manettes."""
    assert gm._find_gamepad_devices() == {}


def test_un_refus_de_permission_laisse_une_trace(evdev_qui_refuse, caplog):
    """LE CONSTAT — rouge sur main.

    Zéro manette parce que zéro permission doit être distinguable de zéro
    manette parce que zéro manette. Aujourd'hui les deux sont le même `{}`
    muet.
    """
    with caplog.at_level(logging.DEBUG, logger=gm.log.name):
        gm._find_gamepad_devices()

    assert caplog.records, (
        "chaque /dev/input/event* a été refusé en PermissionError et "
        "_find_gamepad_devices() rend {} sans écrire une seule ligne de "
        "journal, à aucun niveau. C'est indistinguable d'une boîte sans "
        "manette branchée : _reconcile n'est même pas appelé (`was != live` "
        "est faux), donc rien en aval ne peut le rattraper. Le groupe `input` "
        "manquant est le mode de panne que le docstring de la fonction nomme "
        "explicitement.")


def test_evdev_absent_laisse_une_trace(monkeypatch, caplog):
    """Même famille, l'autre porte de sortie : `except ImportError: return {}`.

    Sur une boîte où le venv du backend a perdu python-evdev, plus aucune
    manette n'existe et le journal est vide.
    """
    monkeypatch.setitem(sys.modules, "evdev", None)   # `import evdev` → ImportError
    monkeypatch.setattr(gm.glob, "glob", lambda pattern: list(FAKE_PATHS))

    with caplog.at_level(logging.DEBUG, logger=gm.log.name):
        found = gm._find_gamepad_devices()

    assert found == {}
    assert caplog.records, (
        "python-evdev est introuvable : la boîte n'aura jamais aucune manette, "
        "et `except ImportError: return {}` ne l'écrit nulle part.")


def test_le_module_expose_bien_le_glob_que_ces_tests_remplacent():
    """Garde-fou du harnais : si la fonction cessait d'utiliser `glob.glob`,
    les monkeypatch ci-dessus ne patcheraient plus rien et tous les tests de ce
    fichier deviendraient vides sans devenir rouges."""
    assert gm.glob is glob_module
