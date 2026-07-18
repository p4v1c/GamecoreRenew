"""Unit tests for the controller player-slot registry
(services.controller_registry) and the player passthrough in battery._check.

Run from anywhere:  python backend/tests/test_controller_registry.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import battery, controller_registry as reg


failures = []

def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def reset():
    reg._slots.clear()
    reg._labels.clear()


def main():
    # ── normalize_mac ────────────────────────────────────────────────────
    check("uniq evdev (majuscules)",
          reg.normalize_mac("84:30:95:07:C8:1C") == "84:30:95:07:c8:1c")
    check("supply hid-playstation",
          reg.normalize_mac("ps-controller-battery-84:30:95:07:c8:1c") == "84:30:95:07:c8:1c")
    check("supply hid-sony",
          reg.normalize_mac("sony_controller_battery_a4:53:85:11:22:33") == "a4:53:85:11:22:33")
    check("pas de MAC → ''", reg.normalize_mac("hid-generic-battery") == "")
    check("None → ''", reg.normalize_mac(None) == "")

    # ── attribution des slots ────────────────────────────────────────────
    reset()
    p1 = reg.connect("aa:aa:aa:aa:aa:aa", "DualShock 4 #1")
    p2 = reg.connect("bb:bb:bb:bb:bb:bb", "DualShock 4 #2")
    check("1re manette → slot 1", p1 == 1)
    check("2e manette (1re connectée) → slot 2", p2 == 2)
    check("reconnexion d'une clé connue → même slot",
          reg.connect("aa:aa:aa:aa:aa:aa") == 1)

    # Déconnexion du player 1 : le slot 1 redevient le plus petit libre
    freed = reg.disconnect("aa:aa:aa:aa:aa:aa")
    check("déconnexion → renvoie le slot libéré", freed == 1)
    p3 = reg.connect("cc:cc:cc:cc:cc:cc", "8BitDo")
    check("nouvelle manette réutilise le slot 1", p3 == 1)
    p4 = reg.connect("dd:dd:dd:dd:dd:dd")
    check("suivante → slot 3 (2 occupé)", p4 == 3)

    check("disconnect clé inconnue → None", reg.disconnect("ee:ee:ee:ee:ee:ee") is None)

    # ── clé de repli sans MAC (pad filaire sans uniq) ────────────────────
    check("key_for MAC", reg.key_for("AA:BB:CC:DD:EE:FF", "/dev/input/event7") == "aa:bb:cc:dd:ee:ff")
    check("key_for sans uniq → devnode", reg.key_for("", "/dev/input/event7") == "/dev/input/event7")

    # ── jointure batterie par MAC ────────────────────────────────────────
    reset()
    reg.connect("84:30:95:07:c8:1c", "Wireless Controller")
    check("player_for_mac depuis un nom de supply",
          reg.player_for_mac("ps-controller-battery-84:30:95:07:C8:1C") == 1)
    check("player_for_mac MAC inconnue → None",
          reg.player_for_mac("ps-controller-battery-00:00:00:00:00:00") is None)
    check("player_for_mac sans MAC → None", reg.player_for_mac("BAT0") is None)

    check("snapshot ordonné par slot",
          reg.snapshot() == [{"player": 1, "label": "Wireless Controller"}])

    # ── _check propage player dans l'alerte ──────────────────────────────
    battery._fired.clear()
    alerts = battery._check([{
        "name": "ps-controller-battery-84:30:95:07:c8:1c",
        "label": "Wireless Controller",
        "player": 2,
        "level": 9,
        "charging": False,
    }])
    check("alerte batterie porte player", len(alerts) == 1 and alerts[0].get("player") == 2, str(alerts))

    print()
    if failures:
        print(f"{len(failures)} test(s) en échec : {failures}")
        sys.exit(1)
    print("Tous les tests passent.")


if __name__ == "__main__":
    main()
