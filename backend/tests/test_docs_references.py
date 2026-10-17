"""The architecture docs must not name files that no longer exist.

`docs/architecture/` is written to be read *instead of* the source, so a path in
it is a promise. Nothing else in the baseline reads those documents: a rename
lands, the prose keeps naming the old file, and it stays wrong for months
because being wrong costs nothing until somebody follows it.

This runs `scripts/check-docs.py`, which resolves every repo path and every
relative link the documents cite. It cannot tell whether an explanation is
*true* — only that the things it names are still there. That is the cheap half,
and it is the half that rots on its own.

The script carries two allowlists, and they are the reason it is a script rather
than a grep: `config/` files written at runtime are legitimately absent from a
checkout, and paths named *because they were deleted* ("a refactor deleted
`install/firefox-profiles/` while `arch.sh` still read it") are the repository's
most valuable sentences. Both are declared by name there.

Run under pytest:  pytest backend/tests/test_docs_references.py
Or directly:       python3 scripts/check-docs.py --all
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-docs.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, cwd=REPO)


def test_every_path_the_docs_cite_still_exists():
    r = _run("--all")
    assert r.returncode == 0, f"stale references in the docs:\n{r.stdout}{r.stderr}"


def test_the_checker_actually_fails_on_a_missing_path(tmp_path):
    """A doc checker that matches nothing passes forever.

    This repo has shipped two tests that went green while verifying nothing — a
    regex that matched only a comment, and a resolver that refused to expand the
    variables it existed to expand. So the guard is exercised against a document
    that is deliberately wrong, and the run above is only meaningful because
    this one fails.
    """
    bad = REPO / "docs" / "architecture" / "_tmp_check_docs_probe.md"
    bad.write_text(
        "Probe: `backend/services/definitely_not_here.py`\n"
        "and a dead [link](./nope-not-a-doc.md).\n",
        encoding="utf-8",
    )
    try:
        r = _run()
        assert r.returncode == 1, "the checker passed a document naming a missing file"
        assert "definitely_not_here.py" in r.stdout
        assert "nope-not-a-doc.md" in r.stdout
    finally:
        bad.unlink()


def _check_docs_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_site_check_fails_on_a_theme_left_out_or_gone():
    """The website kept "four looks" after Jelly shipped, with no check to say so."""
    cd = _check_docs_module()
    tracked = {f"docs/img/themes/{t}-{k}.webp" for t in ("default", "jelly") for k in ("home", "controller")}
    tracked.add("config/themes/jelly/preview.png")
    full = " ".join(f"img/themes/{t}-{k}.webp" for t in ("default", "jelly") for k in ("home", "controller"))
    site = full + " 34 systems 29 more systems"

    assert cd.site_problems(["default", "jelly"], tracked, {"docs/index.html": site}, 34) == []

    left_out = cd.site_problems(["default", "jelly"], tracked,
                                {"docs/index.html": site.replace("jelly-home", "x")}, 34)
    assert any("no jelly-home.webp" in p for p in left_out)

    gone = cd.site_problems(["default"], tracked, {"docs/index.html": site}, 34)
    assert any("`jelly`, which no longer ships" in p for p in gone)

    no_preview = cd.site_problems(["default", "jelly"], tracked - {"config/themes/jelly/preview.png"},
                                  {"docs/index.html": site}, 34)
    assert any("jelly/preview.png: missing" in p for p in no_preview)

    assert any("35 systems" in p for p in cd.site_problems(["default", "jelly"], tracked,
                                                            {"docs/index.html": site}, 35))
