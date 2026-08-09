#!/usr/bin/env python3
"""Every repo path the documentation names must still exist — or be declared.

This does NOT check that the docs are *right*. No script can: a document can
name every file correctly and still explain the system backwards. What it
catches is the failure mode that actually happens here — a file gets renamed or
moved, and the document naming it keeps saying the old thing, confidently, for
months. Doc rot is silent and the rest of the baseline is blind to it.

Two things are verified:

  1. inline-code tokens that look like repo paths (`backend/services/paths.py`,
     with an optional `:123` or `:symbol()` citation suffix) resolve on disk;
  2. relative Markdown links between documents resolve.

The two allowlists below are the interesting part
-------------------------------------------------
The first version of this script flagged 24 references and **every single one
was a false positive**, in two distinct ways. Both are worth naming, because
both are things this repository does on purpose:

`RUNTIME_GENERATED` — `config/` is the box's identity. It is not in git, and
several of its files are written on first boot. A checkout legitimately has no
`config/auth_secret`. Skipping all of `config/` would have been the easy fix and
the wrong one: then a document could invent `config/setttings.json` and nothing
would notice. So the generated files are listed by name, and a new one has to be
added here deliberately.

`HISTORICAL` — this repo documents *what failure produced a rule*, which means
its best paragraphs name files that no longer exist:

    "a refactor deleted `install/firefox-profiles/` while `arch.sh` still
     read it. That install died at 66 %, on a fresh machine, months later."

That sentence is correct precisely because the directory is gone. A checker that
forces such prose to be deleted would strip the documentation of the only part
that cannot be recovered by reading the code. So those paths are listed too,
with the reason.

If you add an entry to either list, say why. A list of bare paths becomes a
place to silence this script, which is the opposite of the point.

Run:  python3 scripts/check-docs.py [--all]
      --all also scans docs/*.md, not just docs/architecture/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A token only counts as a repo path if it starts with one of these. Anything
# else is prose that happens to contain a slash.
TOP_LEVEL = {
    "assets", "backend", "catalog", "config", "distribution", "docs",
    "electron", "frontend", "install", "lib", "scripts", "update",
}

# Written at runtime, never in git — see the module docstring.
RUNTIME_GENERATED = {
    "config/auth.json",       # shared-password hash, written on first setup
    "config/auth_secret",     # session-signing secret, 0600
    "config/session.json",    # which session the box boots into
    "config/theme.json",      # the selected theme
    "config/standby.json",    # sleep/wake schedule
    "config/addons.json",     # installed addons registry
}

# Named on purpose although gone — the failure they describe is the point.
HISTORICAL = {
    # Deleted by a refactor while install/arch.sh still read it; the install
    # died at 66 % on a fresh machine, months later. It is the reason
    # test_installer_applier.py exists, and 10/TESTING both tell that story.
    "install/firefox-profiles/",
}

INLINE_CODE = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# `paths.py:111` and `main.py:lifespan()` are citations, not part of the path.
CITATION_SUFFIX = re.compile(r":(\d+(-\d+)?|[A-Za-z_][\w.]*\(\))$")

# `<id>`, `@GAMECORE_PATH@`, `logos|overlays`, globs: a shape, not a file.
PLACEHOLDER = re.compile(r"[<>@*?\[\]{}|\s]")


def is_candidate_path(tok: str) -> bool:
    if PLACEHOLDER.search(tok):
        return False
    if tok.startswith(("/", "~", "http://", "https://", ".venv")):
        return False
    if "/" not in tok:
        return False
    return tok.split("/", 1)[0] in TOP_LEVEL


def exists(clean: str) -> bool:
    p = ROOT / clean
    # `backend/config` names the module; backend/config.py is the file.
    return p.exists() or p.with_suffix(".py").exists()


def check_file(md: Path) -> list[str]:
    problems: list[str] = []
    text = md.read_text(encoding="utf-8")
    rel_md = md.relative_to(ROOT)

    for lineno, line in enumerate(text.splitlines(), 1):
        for tok in INLINE_CODE.findall(line):
            tok = tok.strip()
            if not is_candidate_path(tok):
                continue
            if tok in RUNTIME_GENERATED or tok in HISTORICAL:
                continue
            clean = CITATION_SUFFIX.sub("", tok).rstrip("/")
            if clean in RUNTIME_GENERATED or clean in HISTORICAL:
                continue
            if not exists(clean):
                problems.append(f"{rel_md}:{lineno}: `{tok}` does not exist")

        for target in LINK.findall(line):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).exists():
                problems.append(f"{rel_md}:{lineno}: link -> {target} is dead")

    return problems


def main() -> int:
    scan_all = "--all" in sys.argv
    docs = sorted((ROOT / "docs" / "architecture").glob("*.md"))
    if scan_all:
        docs += sorted((ROOT / "docs").glob("*.md"))

    problems: list[str] = []
    for md in docs:
        problems += check_file(md)

    if problems:
        print(f"check-docs: {len(problems)} stale reference(s)\n")
        for p in problems:
            print("  " + p)
        print("\nIf a path is gone on purpose and the prose is about that, add it")
        print("to HISTORICAL in this script with the reason.")
        return 1

    print(f"check-docs: {len(docs)} document(s), every path and link resolves")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
