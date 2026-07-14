"""Unit tests for the low-battery threshold logic (services.battery._check).

Run from anywhere:  python backend/tests/test_battery.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import battery


failures = []

def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def pad(level, charging=False, name="sony_controller_battery_aa"):
    return {"name": name, "label": "DualShock 4", "level": level, "charging": charging}


def main():
    battery._fired.clear()

    # Descente progressive : un toast par seuil, une seule fois
    check("100% → rien", battery._check([pad(100)]) == [])
    check("16% → rien", battery._check([pad(16)]) == [])
    a = battery._check([pad(15)])
    check("15% → toast seuil 15", len(a) == 1 and a[0]["threshold"] == 15, str(a))
    check("14% → rien (déjà signalé)", battery._check([pad(14)]) == [])
    a = battery._check([pad(10)])
    check("10% → toast seuil 10", len(a) == 1 and a[0]["threshold"] == 10, str(a))
    a = battery._check([pad(4)])
    check("4% → toast seuil 5", len(a) == 1 and a[0]["threshold"] == 5, str(a))
    check("3% → rien", battery._check([pad(3)]) == [])

    # Une manette branchée à 4% ne donne qu'UN toast (pas 15+10+5)
    battery._fired.clear()
    a = battery._check([pad(4)])
    check("connexion à 4% → un seul toast", len(a) == 1 and a[0]["threshold"] == 5, str(a))

    # La charge réarme tout
    battery._fired.clear()
    battery._check([pad(12)])
    check("charge → rien", battery._check([pad(30, charging=True)]) == [])
    a = battery._check([pad(15)])
    check("après charge, 15% re-signale", len(a) == 1, str(a))

    # Oscillation autour du seuil : pas de spam (marge de réarmement)
    battery._fired.clear()
    battery._check([pad(15)])
    check("16% n'est pas réarmé (marge)", battery._check([pad(16)]) == [] and battery._check([pad(15)]) == [])
    battery._check([pad(25)])  # > 15+5 → réarme
    a = battery._check([pad(15)])
    check("25% puis 15% re-signale", len(a) == 1, str(a))

    # Déconnexion → état oublié
    battery._fired.clear()
    battery._check([pad(12)])
    battery._check([])  # manette partie
    a = battery._check([pad(12)])
    check("reconnexion à 12% re-signale", len(a) == 1 and a[0]["threshold"] == 15, str(a))

    # Deux manettes indépendantes
    battery._fired.clear()
    a = battery._check([pad(14, name="pad_a"), pad(80, name="pad_b")])
    check("2 manettes: seule la faible alerte", len(a) == 1, str(a))

    print()
    if failures:
        print(f"{len(failures)} FAILURES: {failures}")
        sys.exit(1)
    print("All tests passed.")


if __name__ == "__main__":
    main()
