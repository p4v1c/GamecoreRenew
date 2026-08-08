"""Shared fixtures for the audit repro tests.

These tests live OUTSIDE `testpaths` (backend/tests, catalog) on purpose: they
are red on main by construction, and the baseline must stay green. Run them
explicitly:

    python3 -m pytest AUDIT/repro -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import controller_profiles as cp    # noqa: E402
from backend.tests import characterisation as ch          # noqa: E402


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A fresh install: every pack seed deployed into a fake HOME, SDL stubbed.

    Same construction as backend/tests/test_controller_characterisation.py, so
    a repro here exercises the real generators against the real seeds.
    """
    home = tmp_path / "home"
    home.mkdir()
    ch.build_tree(home)
    ch.install_stubs(cp, home, monkeypatch)
    return home
