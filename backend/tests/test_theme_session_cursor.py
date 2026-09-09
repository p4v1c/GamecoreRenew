"""Every theme's session menu must DRAW the option the pad is on.

The host owns this menu's navigation — `SessionBar.tsx` opens it on L2, moves
the selection with the d-pad and runs the action on ✕. It marks the current
action with `data-active="true"` and it deliberately does **not** move DOM
focus: the menu sits over a live screen, and focusing a button there would hand
that screen's own handlers a target they must not have.

Which means `:hover` and `:focus-visible` are dead states for a player on a
gamepad. A theme that styles only those has a menu that opens, a selection that
moves, and nothing on screen saying where it is — with "Resume" and "Close
game" one invisible step apart, on the one screen where guessing wrong ends a
session that cannot be brought back.

Orbit shipped exactly that. Shelf and Summer did not, which is why the owner
reported "the controller does not work on Orbit" and "Shelf works": with the
cursor visible, the same host bindings looked like working bindings.

This is a stylesheet test, and it has to be: the mark is in the DOM either way,
so the frontend suite cannot tell the two apart. jsdom applies no external CSS.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

THEMES = Path(__file__).resolve().parents[2] / "config" / "themes"


def _session_views():
    """Every shipped theme, with the file that draws its session menu.

    Found rather than listed: a theme added later must be covered without
    anybody remembering this file exists.
    """
    for d in sorted(THEMES.iterdir()):
        if not d.is_dir() or d.name[0] in "._":
            continue
        manifest = d / "theme.json"
        css = d / "theme.css"
        if not manifest.is_file() or not css.is_file():
            continue
        try:
            provides = json.loads(manifest.read_text()).get("provides") or []
        except json.JSONDecodeError:
            continue                    # test_theme_manifests' business, not ours
        if "shell" not in provides:
            continue
        for candidate in (d / "lib" / "session.js", d / "views" / "session.js"):
            if candidate.is_file() and "data-active" in candidate.read_text():
                yield pytest.param(d, candidate, id=d.name)
                break


CASES = list(_session_views())


def test_there_is_something_to_check():
    """A parametrised test with an empty parameter set is SKIPPED, quietly, in a
    line nobody reads — which is how a guard comes to protect nothing. The
    repository ships three themes with a session menu."""
    assert len(CASES) >= 3, f"expected the shipped themes' session menus, found {CASES}"


def _element_at(text: str, index: int) -> str:
    """The whole opening tag the attribute at `index` belongs to.

    Bounded properly rather than by looking backwards to the nearest `<`: Orbit
    writes `data-active` BEFORE its class and Shelf writes it after, and a scan
    that stopped at the attribute saw one of the two and not the other. `${...}`
    regions are skipped by depth, because a class expression contains `>` in its
    ternaries and `}` in its interpolations.
    """
    start = text.rfind("<", 0, index)
    i, depth = start, 0
    while i < len(text):
        if text.startswith("${", i):
            depth += 1
            i += 2
            continue
        if depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
        elif text[i] == ">":
            return text[start:i]
        i += 1
    return text[start:index]


def _attr_value(value: str) -> str:
    """Just this attribute's value, stopping where it ends.

    Without the bound it ran on into the attributes after it and collected
    `onClick=` and `data-active=` as class names. Harmless to the assertion —
    junk never matches a stylesheet — but a failure message listing them is a
    failure message nobody can act on.
    """
    value = value.lstrip()
    if not value:
        return ""
    if value[0] in "\"'":
        end = value.find(value[0], 1)
        return value[1:end] if end != -1 else value[1:]
    if not value.startswith("${"):
        return value.split()[0]
    i, depth = 2, 1
    while i < len(value) and depth:
        if value[i] == "{":
            depth += 1
        elif value[i] == "}":
            depth -= 1
        i += 1
    return value[2:i - 1]


def _classes_in(value: str) -> set[str]:
    """The class names an htm class expression can produce.

    Outside a nested interpolation the words are literal; inside one, only the
    string literals are — `action.danger ? 'cz-btn-danger' : ''` contributes
    `cz-btn-danger`, and neither `action` nor `danger`.
    """
    value = _attr_value(value).strip("`")
    out: set[str] = set()
    i, depth, literal = 0, 0, []
    while i < len(value):
        if value.startswith("${", i):
            depth += 1
            i += 2
            continue
        if depth:
            if value[i] == "{":
                depth += 1
            elif value[i] == "}":
                depth -= 1
            elif value[i] in "'\"":
                quote = value[i]
                end = value.find(quote, i + 1)
                if end == -1:
                    break
                out.update(value[i + 1:end].split())
                i = end
            i += 1
            continue
        literal.append(value[i])
        i += 1
    out.update("".join(literal).split())
    return {c for c in out if c and c[0].isalpha() and "=" not in c}


def _option_classes(view: Path) -> set[str]:
    """The class names on the elements that carry the pad's mark.

    The menu's options are the buttons built from the host's `actions`, so the
    marker to look for is `data-active=${actionIdx === i ...}` — the bar carries
    a `data-active` of its own meaning something else entirely ("this bar is
    live"), and a theme styling only that one is the bug, not the fix.
    """
    text = view.read_text()
    classes: set[str] = set()
    for match in re.finditer(r"data-active=\$\{\s*actionIdx", text):
        element = _element_at(text, match.start())
        for attr in re.finditer(r"class(?:Name)?=", element):
            classes |= _classes_in(element[attr.end():])
    return classes


@pytest.mark.parametrize("theme_dir,view", CASES)
def test_the_menu_marks_the_option_the_pad_is_on(theme_dir: Path, view: Path):
    """The half the host relies on: without the attribute there is nothing to
    style, and this test's sibling below would be vacuous."""
    assert _option_classes(view), (
        f"{theme_dir.name}: no class found on the element carrying "
        f"data-active=${{actionIdx ...}} in {view.name} — either the menu no "
        "longer marks its options, or it marks them some other way and this "
        "test can no longer see it"
    )


@pytest.mark.parametrize("theme_dir,view", CASES)
def test_the_stylesheet_draws_that_mark(theme_dir: Path, view: Path):
    """The half a player sees.

    Satisfied by any rule that pairs one of the option's own classes with
    `[data-active` — `.cz-btn[data-active='true']`,
    `.session-menu-option[data-active="true"]`, and so on. A bare
    `[data-active='true']` somewhere else in the sheet does not count: Orbit
    had five of those, all for library tiles, while its menu drew nothing.
    """
    sheet = (theme_dir / "theme.css").read_text()
    classes = _option_classes(view)
    drawn = [c for c in classes
             if re.search(rf"\.{re.escape(c)}\s*\[data-active", sheet)]
    assert drawn, (
        f"{theme_dir.name}: the session menu marks its options with "
        f"data-active (classes: {sorted(classes)}) but theme.css never draws "
        "it. The host does not move focus here, so :hover and :focus-visible "
        "never fire on a gamepad: the menu opens, the selection moves, and "
        "nothing shows the player which option ✕ is about to run."
    )


@pytest.mark.parametrize("theme_dir,view", CASES)
def test_the_action_that_cannot_be_undone_is_drawn_apart(theme_dir: Path, view: Path):
    """Closing a session is the one action here with no way back. When the pad
    is on it, it must not look like another row of the same colour."""
    sheet = (theme_dir / "theme.css").read_text()
    danger = [c for c in _option_classes(view) if "danger" in c]
    if not danger:
        pytest.skip(f"{theme_dir.name} does not mark a dangerous action by class")
    assert any(re.search(rf"\.{re.escape(c)}\s*\[data-active", sheet) for c in danger), (
        f"{theme_dir.name}: {danger} is the option that ends a session and it "
        "is drawn exactly like the others when the pad is on it"
    )
