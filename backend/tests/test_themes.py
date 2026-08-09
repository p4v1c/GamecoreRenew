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


# ── a theme may ask for its own dashboard grid ───────────────────────────────
# The grid is layout, and layout is the theme's side of the line. A theme that
# wants one long row of big icons cannot fake it: HomeScreen.navigate() walks
# COLS × ROWS and wraps at the row end, so a rail drawn as one continuous line
# would silently skip half its contents whenever ROWS > 1.

def test_a_theme_that_says_nothing_gets_the_hosts_grid():
    """The whole compatibility argument: every theme written before this said
    nothing, and must keep looking exactly as it did."""
    assert themes._home_grid(None, "t") is None
    assert themes._home_grid({}, "t") is None


def test_a_grid_is_passed_through():
    assert themes._home_grid({"cols": 8, "rows": 1}, "t") == {"cols": 8, "rows": 1}
    assert themes._home_grid({"rows": 1}, "t") == {"rows": 1}, "one of the two is enough"


def test_an_unusable_grid_is_dropped_not_obeyed():
    """A theme is code its owner installed, but 0 divides by zero in pageCount
    and 400 asks the host to render every system on one page. Neither is a
    look; both are a broken screen."""
    for bad in ({"cols": 0}, {"cols": -4}, {"cols": 999}, {"cols": 1.5},
                {"cols": "8"}, {"cols": True}, {"cols": None}):
        assert themes._home_grid(bad, "t") is None, bad
    # A bad value does not take a good one down with it.
    assert themes._home_grid({"cols": 8, "rows": 0}, "t") == {"cols": 8}
    # Not an object at all.
    assert themes._home_grid("one row please", "t") is None
    assert themes._home_grid([8, 1], "t") is None


def test_the_grid_reaches_the_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(themes, "THEMES_DIR", tmp_path)
    d = tmp_path / "row"
    d.mkdir()
    (d / "index.js").write_text("export default () => ({})")
    (d / "theme.json").write_text(json.dumps({
        "id": "row", "name": "Row", "version": "1.0.0", "api": 1,
        "provides": ["shell"], "home": {"cols": 8, "rows": 1},
    }))
    m = next(t for t in themes.list_themes() if t["id"] == "row")
    assert m["home"] == {"cols": 8, "rows": 1}


def test_a_theme_can_ask_for_no_pages():
    """`cols` cannot express this: a number in the manifest is right until the
    owner installs one more system. The host derives it from the list."""
    assert themes._home_grid({"rows": 1, "paged": False}, "t") == {"paged": False, "rows": 1}
    # True is the default and says nothing new.
    assert themes._home_grid({"paged": True}, "t") is None
    # Anything else is not a boolean and is dropped, without taking rows down.
    assert themes._home_grid({"paged": "no", "rows": 1}, "t") == {"rows": 1}
    assert themes._home_grid({"paged": 0, "rows": 1}, "t") == {"rows": 1}


# ── a theme may replace the UI sounds ────────────────────────────────────────
# The five host sounds are fired by the input bus, which sits UNDER the theme
# layer: before this, a shell that redrew every screen still answered every
# press with the stock bip and had no hook to take it over. The manifest names
# files; the module may also hand back functions (see themeLoader).


@pytest.fixture
def sound_theme(tmp_path):
    """A theme directory with one real audio file in it, ready to be pointed at."""
    d = tmp_path / "noisy"
    (d / "assets").mkdir(parents=True)
    (d / "assets" / "move.wav").write_bytes(b"RIFF....WAVE")
    return d


def test_a_theme_that_declares_no_sounds_keeps_the_hosts(sound_theme):
    """Every theme written before this said nothing, and must still sound
    exactly as it did."""
    assert themes._sounds(None, sound_theme) is None
    assert themes._sounds({}, sound_theme) is None


def test_a_declared_sound_reaches_the_manifest(sound_theme):
    assert themes._sounds({"move": "assets/move.wav"}, sound_theme) == {"move": "assets/move.wav"}


def test_a_sound_path_may_not_leave_the_theme_folder(sound_theme):
    """The frontend turns these straight into a fetch, so the theme directory is
    the boundary. Checked rather than trusted: a theme is code somebody
    downloaded."""
    for bad in ("../../../etc/passwd", "/etc/passwd", "assets/../../secrets.wav"):
        assert themes._sounds({"move": bad}, sound_theme) is None, bad


def test_a_sound_whose_file_is_missing_falls_back_instead_of_failing(sound_theme):
    """Dropped, not fatal: the cascade gives that one name back to the host, so
    a typo'd path costs one bip rather than the whole theme."""
    assert themes._sounds({"move": "assets/nope.wav"}, sound_theme) is None
    # And it does not take a good sibling down with it.
    assert themes._sounds(
        {"move": "assets/move.wav", "back": "assets/nope.wav"}, sound_theme,
    ) == {"move": "assets/move.wav"}


def test_an_unusable_sound_entry_is_dropped(sound_theme):
    assert themes._sounds({"move": 42}, sound_theme) is None
    assert themes._sounds({"move": ""}, sound_theme) is None
    assert themes._sounds({"MOVE": "assets/move.wav"}, sound_theme) is None
    assert themes._sounds({"../x": "assets/move.wav"}, sound_theme) is None
    assert themes._sounds("loud please", sound_theme) is None
    assert themes._sounds([["move", "assets/move.wav"]], sound_theme) is None


def test_a_theme_may_name_a_sound_the_host_does_not_have(sound_theme):
    """The cascade ends in silence, not an error, so a theme can add its own
    names as well as replace the five."""
    assert themes._sounds({"coin": "assets/move.wav"}, sound_theme) == {"coin": "assets/move.wav"}


def test_the_sounds_reach_the_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(themes, "THEMES_DIR", tmp_path)
    d = tmp_path / "noisy"
    (d / "assets").mkdir(parents=True)
    (d / "assets" / "move.wav").write_bytes(b"RIFF....WAVE")
    (d / "index.js").write_text("export default () => ({})")
    (d / "theme.json").write_text(json.dumps({
        "id": "noisy", "name": "Noisy", "version": "1.0.0", "api": 1,
        "provides": ["splash", "shell"], "sounds": {"move": "assets/move.wav"},
    }))
    m = next(t for t in themes.list_themes() if t["id"] == "noisy")
    assert m["sounds"] == {"move": "assets/move.wav"}
