"""Unit tests for the controller player-slot registry
(services.controller_registry) and the player passthrough in battery._check.

Run under pytest:  pytest backend/tests/test_controller_registry.py
Or directly:       python backend/tests/test_controller_registry.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import battery, controller_registry as reg


@pytest.fixture(autouse=True)
def empty_registry():
    """Slots and labels are module state — no test may inherit another's pads."""
    reg._slots.clear()
    reg._labels.clear()
    yield
    reg._slots.clear()
    reg._labels.clear()


# ── normalize_mac ────────────────────────────────────────────────────────────

def test_normalize_mac_reads_every_shape_a_mac_arrives_in():
    assert reg.normalize_mac("84:30:95:07:C8:1C") == "84:30:95:07:c8:1c", "uniq evdev (majuscules)"
    assert reg.normalize_mac("ps-controller-battery-84:30:95:07:c8:1c") == "84:30:95:07:c8:1c", \
        "supply hid-playstation"
    assert reg.normalize_mac("sony_controller_battery_a4:53:85:11:22:33") == "a4:53:85:11:22:33", \
        "supply hid-sony"
    assert reg.normalize_mac("hid-generic-battery") == "", "pas de MAC → ''"
    assert reg.normalize_mac(None) == "", "None → ''"


# ── attribution des slots ────────────────────────────────────────────────────

def test_slots_are_handed_out_lowest_free_first():
    p1 = reg.connect("aa:aa:aa:aa:aa:aa", "DualShock 4 #1")
    p2 = reg.connect("bb:bb:bb:bb:bb:bb", "DualShock 4 #2")
    assert p1 == 1, "1re manette → slot 1"
    assert p2 == 2, "2e manette (1re connectée) → slot 2"
    assert reg.connect("aa:aa:aa:aa:aa:aa") == 1, "reconnexion d'une clé connue → même slot"


def test_a_freed_slot_is_reused_before_a_new_one():
    reg.connect("aa:aa:aa:aa:aa:aa", "DualShock 4 #1")
    reg.connect("bb:bb:bb:bb:bb:bb", "DualShock 4 #2")

    freed = reg.disconnect("aa:aa:aa:aa:aa:aa")
    assert freed == 1, "déconnexion → renvoie le slot libéré"
    assert reg.connect("cc:cc:cc:cc:cc:cc", "8BitDo") == 1, "nouvelle manette réutilise le slot 1"
    assert reg.connect("dd:dd:dd:dd:dd:dd") == 3, "suivante → slot 3 (2 occupé)"


def test_disconnecting_an_unknown_key_is_a_noop():
    assert reg.disconnect("ee:ee:ee:ee:ee:ee") is None, "disconnect clé inconnue → None"


# ── clé de repli sans MAC (pad filaire sans uniq) ────────────────────────────

def test_key_for_falls_back_to_the_devnode():
    assert reg.key_for("AA:BB:CC:DD:EE:FF", "/dev/input/event7") == "aa:bb:cc:dd:ee:ff", "key_for MAC"
    assert reg.key_for("", "/dev/input/event7") == "/dev/input/event7", "key_for sans uniq → devnode"


# ── un pad, plusieurs nœuds event* ───────────────────────────────────────────

def test_a_bluetooth_pad_with_several_nodes_is_one_controller():
    """Une DualShock 4 publie trois nœuds — pavé tactile, capteurs, manette —
    et un seul porte les BOUTONS. Lequel n'est pas décidable par la position :
    l'ordre de création dépend du noyau et change d'un démarrage à l'autre.

    Le wizard de mappage lit TOUS les nœuds du pad, et c'est cette fonction qui
    dit lesquels. Regrouper par nœud plutôt que par MAC donnerait un wizard où
    la moitié des boutons ne répondent pas, par intermittence.
    """
    nodes = [
        ("84:30:95:07:C8:1C", "/dev/input/event18"),   # capteurs de mouvement
        ("84:30:95:07:c8:1c", "/dev/input/event19"),   # pavé tactile
        ("84:30:95:07:c8:1c", "/dev/input/event20"),   # la manette
        ("a4:53:85:11:22:33", "/dev/input/event21"),   # une SECONDE manette
    ]

    grouped = reg.nodes_by_key(nodes)

    assert len(grouped) == 2, f"trois nœuds d'un même pad comptés séparément : {grouped}"
    assert grouped["84:30:95:07:c8:1c"] == [
        "/dev/input/event18", "/dev/input/event19", "/dev/input/event20"], \
        "les trois nœuds du pad, dans l'ordre, sous sa MAC"
    assert grouped["a4:53:85:11:22:33"] == ["/dev/input/event21"]


def test_pads_without_a_mac_stay_separate():
    """Le repli sur le devnode ne doit pas fusionner deux manettes filaires :
    sans `uniq`, chaque nœud EST une identité, et les regrouper ferait
    disparaître le deuxième joueur."""
    grouped = reg.nodes_by_key([(None, "/dev/input/event3"), ("", "/dev/input/event4")])

    assert grouped == {"/dev/input/event3": ["/dev/input/event3"],
                       "/dev/input/event4": ["/dev/input/event4"]}


def test_the_first_node_stays_the_one_pads_by_key_would_pick():
    """`gamepad_monitor.pads_by_key()` prend le premier nœud rencontré. Les deux
    fonctions doivent désigner le même, sinon le pad que le wizard mappe n'est
    pas celui à qui le registre a donné un slot."""
    nodes = [("84:30:95:07:c8:1c", "/dev/input/event18"),
             ("84:30:95:07:c8:1c", "/dev/input/event20")]

    assert reg.nodes_by_key(nodes)["84:30:95:07:c8:1c"][0] == "/dev/input/event18"


# ── jointure batterie par MAC ────────────────────────────────────────────────

def test_player_for_mac_joins_a_power_supply_name_to_its_slot():
    reg.connect("84:30:95:07:c8:1c", "Wireless Controller")
    assert reg.player_for_mac("ps-controller-battery-84:30:95:07:C8:1C") == 1, \
        "player_for_mac depuis un nom de supply"
    assert reg.player_for_mac("ps-controller-battery-00:00:00:00:00:00") is None, \
        "player_for_mac MAC inconnue → None"
    assert reg.player_for_mac("BAT0") is None, "player_for_mac sans MAC → None"


def test_snapshot_is_ordered_by_slot():
    reg.connect("84:30:95:07:c8:1c", "Wireless Controller")
    assert reg.snapshot() == [{"player": 1, "label": "Wireless Controller"}], "snapshot ordonné par slot"


# ── _check propage player dans l'alerte ──────────────────────────────────────

def test_battery_alert_carries_the_player_slot():
    battery._fired.clear()
    alerts = battery._check([{
        "name": "ps-controller-battery-84:30:95:07:c8:1c",
        "label": "Wireless Controller",
        "player": 2,
        "level": 9,
        "charging": False,
    }])
    assert len(alerts) == 1 and alerts[0].get("player") == 2, f"alerte batterie porte player ({alerts})"


if __name__ == "__main__":
    for fn in (
        test_normalize_mac_reads_every_shape_a_mac_arrives_in,
        test_slots_are_handed_out_lowest_free_first,
        test_a_freed_slot_is_reused_before_a_new_one,
        test_disconnecting_an_unknown_key_is_a_noop,
        test_key_for_falls_back_to_the_devnode,
        test_a_bluetooth_pad_with_several_nodes_is_one_controller,
        test_pads_without_a_mac_stay_separate,
        test_the_first_node_stays_the_one_pads_by_key_would_pick,
        test_player_for_mac_joins_a_power_supply_name_to_its_slot,
        test_snapshot_is_ordered_by_slot,
        test_battery_alert_carries_the_player_slot,
    ):
        reg._slots.clear()
        reg._labels.clear()
        fn()
        print(f"[OK ] {fn.__name__}")
    print("\nTous les tests passent.")
