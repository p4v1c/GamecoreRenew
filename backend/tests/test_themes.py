"""Unit tests for theme discovery and the completeness rule (services.themes).

A theme dresses the whole UI or it does not load: it must declare every surface
in SURFACES. These tests pin that rule, since the failure it prevents — half a
theme, e.g. a themed dashboard behind the stock splash — is silent and only
shows up on the TV.

Run under pytest:  pytest backend/tests/test_themes.py
Or directly:       python backend/tests/test_themes.py
"""
import json
import re
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
    assert full is not None and full["compatible"], "a complete theme is accepted"
    assert full["warnings"] == [], f"aucun avertissement ({full['warnings']})"


@pytest.mark.parametrize("absent,present", [("splash", ["shell"]), ("shell", ["splash"])])
def test_theme_missing_a_surface_is_incompatible_and_names_it(themes_root, absent, present):
    m = write_theme(themes_root, f"no_{absent}", provides=present)
    assert m is not None and not m["compatible"], f"sans {absent} → incompatible"
    assert any(absent in w for w in m["warnings"]), f"missing {absent} → a reason is given ({m['warnings']})"


def test_empty_provides_is_incompatible(themes_root):
    m = write_theme(themes_root, "empty", provides=[])
    assert m is not None and not m["compatible"], "provides vide → incompatible"


# ── manifest hygiene ─────────────────────────────────────────────────────────

def test_a_theme_from_a_future_sdk_is_incompatible(themes_root):
    m = write_theme(themes_root, "future", api=themes.SDK_VERSION + 1)
    assert m is not None and not m["compatible"], "SDK too new → incompatible"


def test_unknown_surface_is_dropped_reported_and_not_fatal(themes_root):
    m = write_theme(themes_root, "unknown_surface", provides=["splash", "shell", "toaster"])
    assert m is not None and "toaster" not in m["provides"], f"unknown surface ignored ({m['provides']})"
    assert any("toaster" in w for w in m["warnings"]), f"unknown surface reported ({m['warnings']})"
    assert m["compatible"], "surface inconnue seule n'invalide pas"


def test_manifest_id_must_equal_the_directory_name(themes_root):
    d = themes_root / "mismatch"
    d.mkdir()
    (d / "index.js").write_text("export default () => ({})\n")
    (d / "theme.json").write_text(json.dumps(
        {"id": "somethingelse", "name": "x", "version": "1", "api": 1, "provides": ["splash", "shell"]}))
    assert themes._read_manifest(d) is None, "id ≠ folder name → rejected"


def test_a_theme_without_its_entry_module_is_rejected(themes_root):
    d = themes_root / "noentry"
    d.mkdir()
    (d / "theme.json").write_text(json.dumps(
        {"id": "noentry", "name": "x", "version": "1", "api": 1, "provides": ["splash", "shell"]}))
    assert themes._read_manifest(d) is None, "missing entry → rejected"


def test_an_unreadable_manifest_is_rejected(themes_root):
    d = themes_root / "broken"
    d.mkdir()
    (d / "index.js").write_text("")
    (d / "theme.json").write_text("{ not json")
    assert themes._read_manifest(d) is None, "unreadable manifest → rejected"


# ── id safety: a theme id is a directory name, never a path ──────────────────

@pytest.mark.parametrize("bad", ["../escape", "a/b", "Upper", "", "x" * 65])
def test_theme_id_is_a_directory_name_never_a_path(bad):
    assert themes._safe_id(bad) is None, f"id refused: {bad!r}"


def test_a_plain_theme_id_is_accepted():
    assert themes._safe_id("summer") == "summer", "id accepted: 'summer'"


# ── set_active refuses what cannot load ──────────────────────────────────────
# Pointed at fixtures we built to be incomplete, rather than whatever happens to
# be installed on the machine running the tests.

def test_templates_are_hidden_from_the_picker(themes_root):
    # A leading underscore marks a template, not a theme: _safe_id refuses it,
    # so listing it would offer something that can never be selected.
    write_theme(themes_root, "_template")
    listed = {t["id"] for t in themes.list_themes()}
    assert "_template" not in listed, f"_-prefixed template hidden from the picker ({sorted(listed)})"
    assert themes._safe_id("_template") is None, "the template is not selectable anyway"


def test_valid_themes_are_listed(themes_root):
    write_theme(themes_root, "full")
    write_theme(themes_root, "no_splash", provides=["shell"])
    listed = {t["id"] for t in themes.list_themes()}
    assert listed >= {"full", "no_splash"}, f"the fixtures are listed ({sorted(listed)})"


def test_set_active_accepts_a_complete_theme_and_persists_it(themes_root):
    write_theme(themes_root, "full")
    assert themes.set_active("full") == "full", "set_active accepts a complete theme"
    assert themes.get_active() == "full", "the selection is persisted"


def test_set_active_refuses_an_incomplete_theme_and_keeps_the_selection(themes_root):
    write_theme(themes_root, "full")
    write_theme(themes_root, "no_splash", provides=["shell"])
    themes.set_active("full")

    with pytest.raises(ValueError) as e:
        themes.set_active("no_splash")
    assert "splash" in str(e.value), f"set_active refuses an incomplete theme ({e.value})"
    assert themes.get_active() == "full", "a refusal leaves the selection alone"


def test_set_active_none_returns_to_the_default(themes_root):
    write_theme(themes_root, "full")
    themes.set_active("full")
    assert themes.set_active(None) is None, "set_active(None) falls back to the default"


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


# ── no theme may leave a settings page unreachable ───────────────────────────
# Omitting one costs nothing at load and is invisible on screen: the page
# exists, the route exists, and nothing can open it. It has shipped twice —
# `catalog`, so neither bundled theme could install an emulator, and `storage`,
# which was missing from DefaultSettingsPages itself, so no theme could have
# offered safe-eject even if its author had thought of it.
#
# The check is here rather than only in scripts/check-theme.mjs because this
# suite is in the baseline and that script is not.

REPO = Path(__file__).resolve().parents[2]
DEFAULTS_TSX = REPO / "frontend" / "src" / "components" / "defaults.tsx"
SHIPPED_THEMES = REPO / "config" / "themes"


def host_settings_pages() -> list[str]:
    """The page ids the frontend exposes, read from the one place they exist.

    Parsed rather than copied: a list typed out here would be the third copy of
    it in the repo, and the first two both drifted.
    """
    src = DEFAULTS_TSX.read_text()
    block = re.search(r"export const DefaultSettingsPages = \{(.*?)\n\}", src, re.S)
    assert block, "DefaultSettingsPages not found — did the export move?"
    return re.findall(r"^  ([a-z][a-z0-9_-]*):", block.group(1), re.M)


def themes_with_their_own_menu():
    """Shipped themes that replace the host's settings menu with one of their own.

    Found by what they *do*, not by name: a test naming `summer` stops
    protecting the theme somebody adds next.

    "What they do" used to mean "some .js under here mentions
    DefaultSettingsPages", and that was wrong in a way nothing caught for a
    long time. The only file that mentioned it was the shared settings screen,
    which lived at `config/themes/_shared/` and carried a `theme.json` of its
    own so the updater would deliver it — so the ONLY directory these two tests
    ever ran against was `_shared`. Neither Shelf nor Summer was ever checked.
    Moving that screen into the frontend bundle emptied the set entirely, which
    is the only reason anyone found out.

    The honest signal is `provides: ["shell"]`: a theme that owns the shell owns
    everything the player sees, the host's settings menu included. There is no
    other way for it to offer these pages, and `settings.pages` is its
    declaration of which ones it still reaches.
    """
    if not SHIPPED_THEMES.is_dir():
        return
    for d in sorted(SHIPPED_THEMES.iterdir()):
        # `_`-prefixed the same way `list_themes()` skips them: a directory
        # the picker never offers is not something a player can end up in.
        # `_skeleton` is the template new themes are copied from, and holding a
        # template to a shipped theme's contract is how this test fails for
        # something nobody can select.
        if not d.is_dir() or d.name[0] in "._":
            continue
        manifest = d / "theme.json"
        if not manifest.is_file():
            continue
        try:
            m = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            continue        # a broken manifest is test_theme_manifests' business
        if "shell" in (m.get("provides") or []):
            yield d


def test_there_is_something_to_check():
    """The two tests below take their cases from the function above, and pytest
    SKIPS a parametrised test whose parameter set comes out empty — quietly, in
    a line nobody reads. That is exactly how they spent months checking a
    directory that was not a theme and no themes at all.

    A guard that silently passes forever is worse than no guard, which the
    regex above already has a test for. This is the same protection for the
    other half.
    """
    found = [d.name for d in themes_with_their_own_menu()]
    assert len(found) >= 2, (
        f"expected the shipped themes that build their own menu, found {found}"
    )


def test_the_host_page_list_is_readable():
    """The two tests below are vacuous if this regex stops matching, and a
    guard that silently passes forever is worse than no guard."""
    pages = host_settings_pages()
    assert len(pages) >= 8, f"suspiciously few settings pages parsed: {pages}"


@pytest.mark.parametrize("theme_dir", list(themes_with_their_own_menu()),
                         ids=lambda d: d.name)
def test_a_shipped_theme_menu_reaches_every_settings_page(theme_dir):
    m = json.loads((theme_dir / "theme.json").read_text())
    declared = (m.get("settings") or {}).get("pages")
    assert declared is not None, (
        f"{theme_dir.name} builds its own settings menu but declares no "
        "settings.pages — the host cannot tell what it left unreachable"
    )
    missing = [p for p in host_settings_pages() if p not in declared]
    assert not missing, f"{theme_dir.name} cannot open: {', '.join(missing)}"


@pytest.mark.parametrize("theme_dir", list(themes_with_their_own_menu()),
                         ids=lambda d: d.name)
def test_a_shipped_theme_declares_only_pages_that_exist(theme_dir):
    """The other direction: a menu entry pointing at a page that was renamed or
    removed resolves to undefined and renders nothing when it is selected."""
    m = json.loads((theme_dir / "theme.json").read_text())
    declared = (m.get("settings") or {}).get("pages") or []
    pages = host_settings_pages()
    unknown = [p for p in declared if p not in pages]
    assert not unknown, f"{theme_dir.name} declares pages that do not exist: {unknown}"


# ── the shipped default, and the rescue it must not swallow ──────────────────

def test_a_box_nobody_has_configured_gets_the_shipped_theme(tmp_path, monkeypatch):
    """A fresh install used to come up on the bare built-in UI, and the owner
    had to go and pick the theme the box ships with. It now starts on it."""
    monkeypatch.setattr(themes, "STATE_FILE", tmp_path / "theme.json")
    # The themes directory is a runtime path this suite points elsewhere, so the
    # installed set is stated here rather than read off the developer's disk.
    monkeypatch.setattr(themes, "list_themes",
                        lambda: [{"id": themes.SHIPPED_DEFAULT, "compatible": True}])
    assert not (tmp_path / "theme.json").exists()
    assert themes.get_active() == themes.SHIPPED_DEFAULT


def test_a_shipped_default_that_will_not_load_is_not_handed_out(tmp_path, monkeypatch):
    """Installed but refused — wrong SDK version, missing surface. Quoting it
    would send a fresh box to a theme that cannot render."""
    monkeypatch.setattr(themes, "STATE_FILE", tmp_path / "theme.json")
    monkeypatch.setattr(themes, "list_themes",
                        lambda: [{"id": themes.SHIPPED_DEFAULT, "compatible": False}])
    assert themes.get_active() is None


def test_choosing_the_built_in_ui_survives_and_is_not_overridden(tmp_path, monkeypatch):
    """The rescue's whole job is to escape the themed UI: holding L1+R1 writes
    an explicit null. A shipped default that could not tell that from an absent
    file would hand the theme straight back to somebody trying to get away from
    it — on a box where that theme is why nothing renders."""
    state = tmp_path / "theme.json"
    monkeypatch.setattr(themes, "STATE_FILE", state)
    state.write_text(json.dumps({"active": None}))
    assert themes.get_active() is None


def test_the_shipped_default_is_verified_before_it_is_handed_out(tmp_path, monkeypatch):
    """Naming a theme that is not installed would leave a fresh box quoting an
    id that loads nothing. The built-in UI is the honest answer then."""
    monkeypatch.setattr(themes, "STATE_FILE", tmp_path / "theme.json")
    monkeypatch.setattr(themes, "SHIPPED_DEFAULT", "a-theme-nobody-installed")
    assert themes.get_active() is None


def test_the_shipped_default_names_a_theme_this_repository_ships():
    """The constant and the directories drift apart silently otherwise: the id
    is only ever read back through `list_themes()`, so a typo — or deleting the
    theme it names — degrades every fresh box to the built-in UI, and nothing
    anywhere says why.

    Checked against the repository rather than against `list_themes()`, whose
    directory this suite deliberately points somewhere empty."""
    shipped = SHIPPED_THEMES / themes.SHIPPED_DEFAULT / "theme.json"
    assert shipped.is_file(), (
        f"SHIPPED_DEFAULT is {themes.SHIPPED_DEFAULT!r} but {shipped} does not exist"
    )
