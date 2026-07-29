"""Unit tests for theme discovery and the completeness rule (services.themes).

A theme dresses the whole UI or it does not load: it must declare every surface
in SURFACES. These tests pin that rule, since the failure it prevents — half a
theme, e.g. a themed dashboard behind the stock splash — is silent and only
shows up on the TV.

Run under pytest:  pytest backend/tests/test_themes.py
Or directly:       python backend/tests/test_themes.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import themes


@pytest.fixture
def themes_root(tmp_path, monkeypatch):
    """A themes directory of our own, with the module globals aimed at it.

    monkeypatch restores THEMES_DIR/STATE_FILE afterwards, so the suite never
    leaves `themes` pointing at a tmpdir that has since been deleted.
    """
    monkeypatch.setattr(themes, "THEMES_DIR", tmp_path)
    monkeypatch.setattr(themes, "STATE_FILE", tmp_path / "theme-state.json")
    return tmp_path


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


# ── completeness ─────────────────────────────────────────────────────────────

def test_complete_theme_is_accepted_without_warnings(themes_root):
    full = write_theme(themes_root, "full")
    assert full is not None and full["compatible"], "thème complet accepté"
    assert full["warnings"] == [], f"aucun avertissement ({full['warnings']})"


@pytest.mark.parametrize("absent,present", [("splash", ["shell"]), ("shell", ["splash"])])
def test_theme_missing_a_surface_is_incompatible_and_names_it(themes_root, absent, present):
    m = write_theme(themes_root, f"no_{absent}", provides=present)
    assert m is not None and not m["compatible"], f"sans {absent} → incompatible"
    assert any(absent in w for w in m["warnings"]), f"sans {absent} → raison donnée ({m['warnings']})"


def test_empty_provides_is_incompatible(themes_root):
    m = write_theme(themes_root, "empty", provides=[])
    assert m is not None and not m["compatible"], "provides vide → incompatible"


# ── manifest hygiene ─────────────────────────────────────────────────────────

def test_a_theme_from_a_future_sdk_is_incompatible(themes_root):
    m = write_theme(themes_root, "future", api=themes.SDK_VERSION + 1)
    assert m is not None and not m["compatible"], "SDK trop récent → incompatible"


def test_unknown_surface_is_dropped_reported_and_not_fatal(themes_root):
    m = write_theme(themes_root, "unknown_surface", provides=["splash", "shell", "toaster"])
    assert m is not None and "toaster" not in m["provides"], f"surface inconnue ignorée ({m['provides']})"
    assert any("toaster" in w for w in m["warnings"]), f"surface inconnue signalée ({m['warnings']})"
    assert m["compatible"], "surface inconnue seule n'invalide pas"


def test_manifest_id_must_equal_the_directory_name(themes_root):
    d = themes_root / "mismatch"
    d.mkdir()
    (d / "index.js").write_text("export default () => ({})\n")
    (d / "theme.json").write_text(json.dumps(
        {"id": "somethingelse", "name": "x", "version": "1", "api": 1, "provides": ["splash", "shell"]}))
    assert themes._read_manifest(d) is None, "id ≠ nom du dossier → rejeté"


def test_a_theme_without_its_entry_module_is_rejected(themes_root):
    d = themes_root / "noentry"
    d.mkdir()
    (d / "theme.json").write_text(json.dumps(
        {"id": "noentry", "name": "x", "version": "1", "api": 1, "provides": ["splash", "shell"]}))
    assert themes._read_manifest(d) is None, "entrée manquante → rejeté"


def test_an_unreadable_manifest_is_rejected(themes_root):
    d = themes_root / "broken"
    d.mkdir()
    (d / "index.js").write_text("")
    (d / "theme.json").write_text("{ not json")
    assert themes._read_manifest(d) is None, "manifeste illisible → rejeté"


# ── id safety: a theme id is a directory name, never a path ──────────────────

@pytest.mark.parametrize("bad", ["../escape", "a/b", "Upper", "", "x" * 65])
def test_theme_id_is_a_directory_name_never_a_path(bad):
    assert themes._safe_id(bad) is None, f"id refusé: {bad!r}"


def test_a_plain_theme_id_is_accepted():
    assert themes._safe_id("summer") == "summer", "id accepté: 'summer'"


# ── set_active refuses what cannot load ──────────────────────────────────────
# Pointed at fixtures we built to be incomplete, rather than whatever happens to
# be installed on the machine running the tests.

def test_templates_are_hidden_from_the_picker(themes_root):
    # A leading underscore marks a template, not a theme: _safe_id refuses it,
    # so listing it would offer something that can never be selected.
    write_theme(themes_root, "_template")
    listed = {t["id"] for t in themes.list_themes()}
    assert "_template" not in listed, f"gabarit _ masqué du sélecteur ({sorted(listed)})"
    assert themes._safe_id("_template") is None, "gabarit non sélectionnable de toute façon"


def test_valid_themes_are_listed(themes_root):
    write_theme(themes_root, "full")
    write_theme(themes_root, "no_splash", provides=["shell"])
    listed = {t["id"] for t in themes.list_themes()}
    assert listed >= {"full", "no_splash"}, f"les fixtures sont bien listées ({sorted(listed)})"


def test_set_active_accepts_a_complete_theme_and_persists_it(themes_root):
    write_theme(themes_root, "full")
    assert themes.set_active("full") == "full", "set_active accepte un thème complet"
    assert themes.get_active() == "full", "la sélection est persistée"


def test_set_active_refuses_an_incomplete_theme_and_keeps_the_selection(themes_root):
    write_theme(themes_root, "full")
    write_theme(themes_root, "no_splash", provides=["shell"])
    themes.set_active("full")

    with pytest.raises(ValueError) as e:
        themes.set_active("no_splash")
    assert "splash" in str(e.value), f"set_active refuse un thème incomplet ({e.value})"
    assert themes.get_active() == "full", "un refus ne change pas la sélection"


def test_set_active_none_returns_to_the_default(themes_root):
    write_theme(themes_root, "full")
    themes.set_active("full")
    assert themes.set_active(None) is None, "set_active(None) revient au défaut"


def test_set_active_refuses_an_unknown_id(themes_root):
    with pytest.raises(LookupError):
        themes.set_active("nope_does_not_exist")


def test_set_active_refuses_a_path(themes_root):
    with pytest.raises(ValueError):
        themes.set_active("../etc")


if __name__ == "__main__":
    # Same tests, without pytest: hand-roll the themes_root fixture.
    import contextlib

    @contextlib.contextmanager
    def themes_root_ctx():
        saved = (themes.THEMES_DIR, themes.STATE_FILE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            themes.THEMES_DIR = root
            themes.STATE_FILE = root / "theme-state.json"
            try:
                yield root
            finally:
                themes.THEMES_DIR, themes.STATE_FILE = saved

    def run(fn, *args, needs_root=True):
        if needs_root:
            with themes_root_ctx() as root:
                fn(root, *args)
        else:
            fn(*args)
        label = fn.__name__ + (f"[{','.join(map(str, args))}]" if args else "")
        print(f"[OK ] {label}")

    run(test_complete_theme_is_accepted_without_warnings)
    run(test_theme_missing_a_surface_is_incompatible_and_names_it, "splash", ["shell"])
    run(test_theme_missing_a_surface_is_incompatible_and_names_it, "shell", ["splash"])
    run(test_empty_provides_is_incompatible)
    run(test_a_theme_from_a_future_sdk_is_incompatible)
    run(test_unknown_surface_is_dropped_reported_and_not_fatal)
    run(test_manifest_id_must_equal_the_directory_name)
    run(test_a_theme_without_its_entry_module_is_rejected)
    run(test_an_unreadable_manifest_is_rejected)
    for _bad in ("../escape", "a/b", "Upper", "", "x" * 65):
        run(test_theme_id_is_a_directory_name_never_a_path, _bad, needs_root=False)
    run(test_a_plain_theme_id_is_accepted, needs_root=False)
    run(test_templates_are_hidden_from_the_picker)
    run(test_valid_themes_are_listed)
    run(test_set_active_accepts_a_complete_theme_and_persists_it)
    run(test_set_active_refuses_an_incomplete_theme_and_keeps_the_selection)
    run(test_set_active_none_returns_to_the_default)
    run(test_set_active_refuses_an_unknown_id)
    run(test_set_active_refuses_a_path)
    print("\nAll tests passed.")
