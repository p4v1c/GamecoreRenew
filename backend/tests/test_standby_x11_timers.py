"""L'écran qui s'éteint en plein film, et le deuxième minuteur invisible.

Rapporté depuis le canapé : « la veille s'active même quand je lance une app ou
un jeu, en plein film l'écran se met en veille ». La veille de GameCore n'y
était pour rien, et le journal du boîtier le montre — Stremio 27 min, melonDS
43 min, Ryujinx 74 min, pas une seule transition `active → screensaver`
pendant. `_tick()` fait déjà ce qu'il faut : un jeu au premier plan compte comme
de l'activité.

Ce qui éteignait la télévision, c'est le serveur X lui-même. La session de
GameCore est une session X11 (`/usr/share/xsessions/gamecore.desktop`), et
PowerDevil n'y tourne PAS — rien ne le démarre. Le serveur X, lui, tourne, avec
son économiseur d'écran et ses délais DPMS à la valeur par défaut, et personne
ne les remettait à zéro : les boutons d'une DualShock 4 sont marqués
`ID_INPUT_JOYSTICK`, ce que le serveur X ne compte pas comme une entrée. Un film
dans un navigateur en kiosque et un jeu dans un émulateur sont deux silences
parfaits pour lui.

Le contre-mesure existante ne pouvait pas y arriver non plus : elle passe par
`org.freedesktop.ScreenSaver`, que personne ne possède dans cette session — le
backend le disait quinze fois par minute, « The name is not activatable ».
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import desktop_power as dp


# Ce que `xset q` répond vraiment. Non traduit, donc identique partout — et
# relevé sur le boîtier plutôt qu'inventé, la moitié XWayland comprise.
REAL_X = """Keyboard Control:
  auto repeat:  on    key click percent:  0
Screen Saver:
  prefer blanking:  yes    allow exposures:  yes
  timeout:  600    cycle:  600
Colors:
  default colormap:  0x20    BlackPixel:  0x0    WhitePixel:  0xffffff
DPMS (Display Power Management Signaling):
  Standby: 600    Suspend: 900    Off: 1200
  DPMS is Enabled
  Monitor is On
"""

# Le serveur de la session de bureau : l'économiseur est déjà à zéro et
# l'extension DPMS n'existe pas. Un boîtier avec UN minuteur, pas zéro.
XWAYLAND = """Screen Saver:
  prefer blanking:  yes    allow exposures:  yes
  timeout:  0    cycle:  0
DPMS (Display Power Management Signaling):
  Server does not have the DPMS Extension
"""


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def xserver(monkeypatch, tmp_path):
    """Un serveur X qui répond, et ce qu'on lui a demandé de faire.

    Pas de KDE ici : `kreadconfig6` refuse, donc seul le bras X agit — c'est la
    session de GameCore, où PowerDevil n'existe pas.
    """
    state = {"q": REAL_X, "argv": []}

    async def fake_run(*argv, **kw):
        if argv[0] == "xset" and argv[1:] == ("q",):
            return 0, state["q"]
        if argv[0] == "xset":
            state["argv"].append(list(argv))
            return 0, ""
        return 1, ""            # ni kreadconfig6 ni kwriteconfig6 ne répondent

    monkeypatch.setattr(dp, "_run", fake_run)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    return state


# ── prendre les minuteurs du serveur X ───────────────────────────────────────

def test_the_x_servers_idle_timers_are_stopped(xserver):
    assert run(dp.claim()) is True
    assert ["xset", "s", "0", "0"] in xserver["argv"]
    assert ["xset", "dpms", "0", "0", "0"] in xserver["argv"]


def test_the_extension_is_left_enabled(xserver):
    """`xset dpms 0 0 0`, jamais `xset -dpms`.

    Mettre les délais à zéro les empêche de se déclencher ; désactiver
    l'extension aurait emporté avec elle le `xset dpms force off` de la veille
    de GameCore — le correctif aurait cassé l'étage qu'il venait protéger.
    """
    run(dp.claim())
    assert not any("-dpms" in argv for argv in xserver["argv"])


def test_the_previous_delays_are_written_down(xserver):
    run(dp.claim())
    note = json.loads(dp._HANDOFF.read_text())
    assert note["x_previous"] == {"s": "600 600", "dpms": "600 900 1200"}


def test_releasing_gives_the_delays_back(xserver):
    run(dp.claim())
    xserver["argv"].clear()
    assert run(dp.release()) is True
    assert ["xset", "s", "600", "600"] in xserver["argv"]
    assert ["xset", "dpms", "600", "900", "1200"] in xserver["argv"]
    assert not dp._HANDOFF.exists()


def test_claiming_twice_does_not_forget_the_real_delays(xserver):
    run(dp.claim())
    xserver["q"] = REAL_X.replace("timeout:  600    cycle:  600",
                                  "timeout:  0    cycle:  0") \
                         .replace("Standby: 600    Suspend: 900    Off: 1200",
                                  "Standby: 0    Suspend: 0    Off: 0")
    run(dp.claim())
    note = json.loads(dp._HANDOFF.read_text())
    assert note["x_previous"] == {"s": "600 600", "dpms": "600 900 1200"}


# ── les serveurs qui n'ont rien à prendre ────────────────────────────────────

def test_xwayland_has_nothing_to_take(xserver):
    """L'économiseur est déjà à zéro et il n'y a pas de DPMS : rien à prendre,
    et surtout pas de note — c'est la session de bureau, où le minuteur qui
    compte est celui de PowerDevil et pas celui-ci."""
    xserver["q"] = XWAYLAND
    assert run(dp.claim()) is True
    assert xserver["argv"] == []
    assert not dp._HANDOFF.exists()


def test_a_server_with_only_a_screen_saver_is_still_claimed(xserver):
    """Les deux moitiés sont suivies séparément. Un serveur qui n'a que
    l'économiseur doit être pris pour celui-là, pas ignoré pour l'absence de
    l'autre."""
    xserver["q"] = XWAYLAND.replace("timeout:  0    cycle:  0",
                                    "timeout:  600    cycle:  600")
    assert run(dp.claim()) is True
    assert ["xset", "s", "0", "0"] in xserver["argv"]
    assert json.loads(dp._HANDOFF.read_text())["x_previous"] == {"s": "600 600"}


def test_a_server_that_will_not_answer_is_not_claimed(monkeypatch, tmp_path):
    async def silent(*argv, **kw):
        return 1, ""

    monkeypatch.setattr(dp, "_run", silent)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    assert run(dp.claim()) is False
    assert not (tmp_path / "handoff.json").exists()


def test_a_claim_that_could_not_write_leaves_no_note_behind(monkeypatch, tmp_path):
    """« Il y a une note » est ce que `release()` lit comme « on tient »."""
    async def read_ok_write_fails(*argv, **kw):
        if argv[0] == "xset" and argv[1:] == ("q",):
            return 0, REAL_X
        return 1, ""

    monkeypatch.setattr(dp, "_run", read_ok_write_fails)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    assert run(dp.claim()) is False
    assert not (tmp_path / "handoff.json").exists()
    assert run(dp.release()) is False


# ── les deux bras sur le même boîtier ────────────────────────────────────────

@pytest.fixture
def both(monkeypatch, tmp_path):
    state = {"kde": "900", "argv": []}

    async def fake_run(*argv, **kw):
        if argv[0] == "kreadconfig6":
            return 0, state["kde"]
        if argv[0] == "kwriteconfig6":
            state["kde"] = argv[-1]
            state["argv"].append(list(argv))
            return 0, ""
        if argv[0] == "xset" and argv[1:] == ("q",):
            return 0, REAL_X
        state["argv"].append(list(argv))
        return 0, ""

    monkeypatch.setattr(dp, "_run", fake_run)
    monkeypatch.setattr(dp, "available", lambda: True)
    monkeypatch.setattr(dp, "_HANDOFF", tmp_path / "handoff.json")
    return state


def test_both_arms_are_taken_and_both_are_given_back(both):
    assert run(dp.claim()) is True
    note = json.loads(dp._HANDOFF.read_text())
    assert note["previous"] == "900"
    assert note["x_previous"]["dpms"] == "600 900 1200"
    assert run(dp.release()) is True
    assert both["kde"] == "900"
    assert ["xset", "dpms", "600", "900", "1200"] in both["argv"]
    assert not dp._HANDOFF.exists()


def test_an_old_note_with_only_the_kde_half_still_reads(both, tmp_path):
    """Une note écrite avant que le bras X existe. Les bras sont retrouvés par
    clé et pas par compte, donc elle doit encore se rendre."""
    (tmp_path / "handoff.json").write_text(json.dumps({"previous": "900"}))
    both["kde"] = "-1"
    assert run(dp.release()) is True
    assert both["kde"] == "900"
    assert not dp._HANDOFF.exists()


# ── la revendication doit être REFAITE, pas faite une fois ───────────────────

@pytest.fixture
def watcher(monkeypatch):
    """Le veilleur, avec la revendication remplacée par un compteur."""
    from backend.services import standby
    from backend.services import process_manager as pm

    attempts = []

    async def fake_claim():
        attempts.append(time.monotonic())
        return True

    async def fake_run_cmd(*argv, **kw):
        return True

    monkeypatch.setattr(dp, "claim", fake_claim)
    monkeypatch.setattr(standby, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(type(pm.process_manager), "is_foreground",
                        property(lambda self: True))
    standby._last_claim_attempt = 0.0
    standby._state = "active"
    standby._last_input = time.monotonic()
    yield attempts
    standby._last_claim_attempt = 0.0
    standby._state = "active"


CFG_ON = {"enabled": True, "screensaver_mins": 10, "sleep_mins": 20}
CFG_OFF = {**CFG_ON, "enabled": False}


def test_the_watcher_claims_the_timers(watcher):
    """Le cœur du rapport. Le backend est un service SYSTÈME : il démarre au
    boot, avant qu'aucune session n'existe — mesuré sur le boîtier, boot à
    07:39:06 et le compositeur de la session à 07:39:20 — donc l'unique
    tentative du démarrage ne trouve rien à prendre. Et ce n'est pas une course
    que l'attente réglerait : le boîtier bascule entre sa session et le bureau,
    et chaque bascule est un nouveau serveur X aux délais par défaut."""
    from backend.services import standby
    asyncio.run(standby._tick(CFG_ON))
    assert len(watcher) == 1


def test_it_is_claimed_before_the_foreground_return(watcher):
    """Un jeu au premier plan est exactement le moment où les minuteurs doivent
    déjà être tenus — et c'est aussi la branche qui sort tôt."""
    from backend.services import standby
    asyncio.run(standby._tick(CFG_ON))
    assert watcher, "le retour anticipé du premier plan a sauté la revendication"


def test_it_is_not_re_attempted_every_fifteen_seconds(watcher):
    """Idempotente mais pas gratuite : elle lit avant d'écrire, donc une fois
    par minute suffit à réparer une bascule de session."""
    from backend.services import standby
    for _ in range(4):
        asyncio.run(standby._tick(CFG_ON))
    assert len(watcher) == 1


def test_a_minute_later_it_is_attempted_again(watcher):
    from backend.services import standby
    asyncio.run(standby._tick(CFG_ON))
    standby._last_claim_attempt -= standby._CLAIM_RETRY_SECS + 1
    asyncio.run(standby._tick(CFG_ON))
    assert len(watcher) == 2


def test_standby_switched_off_claims_nothing(watcher):
    """L'inverse du bogue : les deux désarmés à la fois est l'état que personne
    ne veut. Veille coupée, GameCore ne gère plus l'écran — il ne prend rien."""
    from backend.services import standby
    asyncio.run(standby._tick(CFG_OFF))
    assert watcher == []
