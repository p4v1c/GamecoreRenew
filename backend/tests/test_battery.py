"""Unit tests for the low-battery threshold logic (services.battery._check).

Run under pytest:  pytest backend/tests/test_battery.py
Or directly:       python backend/tests/test_battery.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import battery


@pytest.fixture(autouse=True)
def fresh_alert_state():
    """_check remembers which thresholds already fired — start every test clean."""
    battery._fired.clear()
    yield
    battery._fired.clear()


def pad(level, charging=False, name="sony_controller_battery_aa"):
    return {"name": name, "label": "DualShock 4", "level": level, "charging": charging}


def test_each_threshold_fires_once_on_the_way_down():
    assert battery._check([pad(100)]) == [], "100% → rien"
    assert battery._check([pad(26)]) == [], "26% → rien"

    a = battery._check([pad(25)])
    assert len(a) == 1 and a[0]["threshold"] == 25, f"25% → toast seuil 25 ({a})"

    assert battery._check([pad(16)]) == [], "16% → rien (25 déjà signalé)"

    a = battery._check([pad(15)])
    assert len(a) == 1 and a[0]["threshold"] == 15, f"15% → toast seuil 15 ({a})"

    assert battery._check([pad(14)]) == [], "14% → rien (déjà signalé)"

    a = battery._check([pad(10)])
    assert len(a) == 1 and a[0]["threshold"] == 10, f"10% → toast seuil 10 ({a})"

    a = battery._check([pad(4)])
    assert len(a) == 1 and a[0]["threshold"] == 5, f"4% → toast seuil 5 ({a})"

    assert battery._check([pad(3)]) == [], "3% → rien"


def test_pad_connecting_at_4_percent_gives_one_toast_not_three():
    a = battery._check([pad(4)])
    assert len(a) == 1 and a[0]["threshold"] == 5, f"connexion à 4% → un seul toast ({a})"


def test_charging_rearms_the_thresholds():
    battery._check([pad(12)])
    assert battery._check([pad(30, charging=True)]) == [], "charge → rien"

    a = battery._check([pad(15)])
    assert len(a) == 1, f"après charge, 15% re-signale ({a})"


def test_oscillating_around_a_threshold_does_not_spam():
    battery._check([pad(15)])
    assert battery._check([pad(16)]) == [], "16% n'est pas réarmé (marge)"
    assert battery._check([pad(15)]) == [], "15% déjà signalé"

    battery._check([pad(25)])  # > 15+5 → réarme
    a = battery._check([pad(15)])
    assert len(a) == 1, f"25% puis 15% re-signale ({a})"


def test_disconnecting_forgets_the_alert_state():
    battery._check([pad(12)])
    battery._check([])  # manette partie
    a = battery._check([pad(12)])
    assert len(a) == 1 and a[0]["threshold"] == 15, f"reconnexion à 12% re-signale ({a})"


def test_two_pads_alert_independently():
    a = battery._check([pad(14, name="pad_a"), pad(80, name="pad_b")])
    assert len(a) == 1, f"2 manettes: seule la faible alerte ({a})"


if __name__ == "__main__":
    for fn in (
        test_each_threshold_fires_once_on_the_way_down,
        test_pad_connecting_at_4_percent_gives_one_toast_not_three,
        test_charging_rearms_the_thresholds,
        test_oscillating_around_a_threshold_does_not_spam,
        test_disconnecting_forgets_the_alert_state,
        test_two_pads_alert_independently,
    ):
        battery._fired.clear()
        fn()
        print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")
