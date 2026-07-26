"""Unit tests for theme discovery and the completeness rule (services.themes).

A theme dresses the whole UI or it does not load: it must declare every surface
in SURFACES. These tests pin that rule, since the failure it prevents — half a
theme, e.g. a themed dashboard behind the stock splash — is silent and only
shows up on the TV.

Run from anywhere:  python backend/tests/test_themes.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import themes


failures = []

def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def write_theme(root, tid, *, provides=("splash", "shell"), api=None, entry="index.js", **extra):
    """Materialise a minimal theme directory and return its manifest, or None."""
    d = root / tid
    d.mkdir(parents=True, exist_ok=True)
    (d / entry).write_text("export default () => ({})\n")
    m = {
        "id": tid, "name": tid.title(), "version": "1.0.0",
        "api": themes.SDK_VERSION if api is None else api,
        "provides": list(provides), "entry": entry,
    }
    m.update(extra)
    (d / "theme.json").write_text(json.dumps(m))
    return themes._read_manifest(d)


def main():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)

    # ── completeness ──────────────────────────────────────────────────────────
    full = write_theme(root, "full")
    check("thème complet accepté", full is not None and full["compatible"])
    check("aucun avertissement", full is not None and full["warnings"] == [], str(full and full["warnings"]))

    for absent, present in (("splash", ["shell"]), ("shell", ["splash"])):
        m = write_theme(root, f"no_{absent}", provides=present)
        check(f"sans {absent} → incompatible", m is not None and not m["compatible"])
        check(f"sans {absent} → raison donnée",
              m is not None and any(absent in w for w in m["warnings"]), str(m and m["warnings"]))

    m = write_theme(root, "empty", provides=[])
    check("provides vide → incompatible", m is not None and not m["compatible"])

    # ── manifest hygiene ──────────────────────────────────────────────────────
    m = write_theme(root, "future", api=themes.SDK_VERSION + 1)
    check("SDK trop récent → incompatible", m is not None and not m["compatible"])

    m = write_theme(root, "unknown_surface", provides=["splash", "shell", "toaster"])
    check("surface inconnue ignorée", m is not None and "toaster" not in m["provides"], str(m and m["provides"]))
    check("surface inconnue signalée",
          m is not None and any("toaster" in w for w in m["warnings"]), str(m and m["warnings"]))
    check("surface inconnue seule n'invalide pas", m is not None and m["compatible"])

    d = root / "mismatch"
    d.mkdir()
    (d / "index.js").write_text("export default () => ({})\n")
    (d / "theme.json").write_text(json.dumps(
        {"id": "somethingelse", "name": "x", "version": "1", "api": 1, "provides": ["splash", "shell"]}))
    check("id ≠ nom du dossier → rejeté", themes._read_manifest(d) is None)

    d = root / "noentry"
    d.mkdir()
    (d / "theme.json").write_text(json.dumps(
        {"id": "noentry", "name": "x", "version": "1", "api": 1, "provides": ["splash", "shell"]}))
    check("entrée manquante → rejeté", themes._read_manifest(d) is None)

    d = root / "broken"
    d.mkdir()
    (d / "index.js").write_text("")
    (d / "theme.json").write_text("{ not json")
    check("manifeste illisible → rejeté", themes._read_manifest(d) is None)

    # ── id safety: a theme id is a directory name, never a path ───────────────
    for bad in ("../escape", "a/b", "Upper", "", "x" * 65):
        check(f"id refusé: {bad!r}", themes._safe_id(bad) is None)
    check("id accepté: 'summer'", themes._safe_id("summer") == "summer")

    # ── set_active refuses what cannot load ───────────────────────────────────
    # Pointed at the fixtures above, so the refusal is tested against a theme we
    # built to be incomplete rather than whatever happens to be installed.
    themes.THEMES_DIR = root
    themes.STATE_FILE = root / "theme-state.json"

    check("les fixtures sont bien listées", {t["id"] for t in themes.list_themes()} >= {"full", "no_splash"},
          str([t["id"] for t in themes.list_themes()]))

    check("set_active accepte un thème complet", themes.set_active("full") == "full")
    check("la sélection est persistée", themes.get_active() == "full")

    try:
        themes.set_active("no_splash")
        check("set_active refuse un thème incomplet", False, "accepté")
    except ValueError as e:
        check("set_active refuse un thème incomplet", "splash" in str(e), str(e))

    check("un refus ne change pas la sélection", themes.get_active() == "full")

    check("set_active(None) revient au défaut", themes.set_active(None) is None)

    try:
        themes.set_active("nope_does_not_exist")
        check("set_active refuse un id inconnu", False, "accepté")
    except LookupError:
        check("set_active refuse un id inconnu", True)

    try:
        themes.set_active("../etc")
        check("set_active refuse un chemin", False, "accepté")
    except ValueError:
        check("set_active refuse un chemin", True)

    tmp.cleanup()

    print()
    if failures:
        print(f"{len(failures)} FAILURES: {failures}")
        sys.exit(1)
    print("All tests passed.")


if __name__ == "__main__":
    main()
