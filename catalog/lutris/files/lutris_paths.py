"""Where the Flatpak Lutris keeps its library, its config and its runners.

Read from Lutris 0.5.22 and 0.5.23 (`lutris/settings.py`), Flathub's stable
and beta builds, and checked against the stable Flatpak. Inside the sandbox
XDG_CONFIG_HOME and XDG_DATA_HOME are `~/.var/app/<app id>/config` and
`.../data`, and Lutris then decides:

    config   ~/.config/lutris only if that directory already exists,
             otherwise everything lives in ~/.local/share/lutris
    runners  `runner_dir` in lutris.conf, else <data>/runners
    library  `pga_path` in lutris.conf, else <data>/pga.db
    covers   <data>/coverart/<slug>.jpg

So a fresh install keeps system.yml and runners/wine.yml under data/, and
creating config/lutris ourselves would move Lutris's config out from under it.

Stdlib only: imported by the setup daemon (system python3) and by the
library sync (the backend).
"""
from __future__ import annotations

import configparser
from pathlib import Path

LUTRIS_CONF = "lutris.conf"


def app_root(home: Path, app_id: str) -> Path:
    return home / ".var" / "app" / app_id


def data_dir(home: Path, app_id: str) -> Path:
    return app_root(home, app_id) / "data" / "lutris"


def config_dir(home: Path, app_id: str) -> Path:
    legacy = app_root(home, app_id) / "config" / "lutris"
    return legacy if legacy.is_dir() else data_dir(home, app_id)


def read_setting(home: Path, app_id: str, key: str) -> str:
    """A value from lutris.conf's [lutris] section, "" when absent or unreadable."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config_dir(home, app_id) / LUTRIS_CONF, encoding="utf-8")
        return parser.get("lutris", key, fallback="").strip()
    except (configparser.Error, OSError, UnicodeDecodeError):
        return ""


def runner_dir(home: Path, app_id: str) -> Path:
    custom = read_setting(home, app_id, "runner_dir")
    return Path(custom).expanduser() if custom else data_dir(home, app_id) / "runners"


def wine_dir(home: Path, app_id: str) -> Path:
    """Where Lutris lists Wine builds, and the first place it looks for Proton."""
    return runner_dir(home, app_id) / "wine"


def db_path(home: Path, app_id: str) -> Path:
    custom = read_setting(home, app_id, "pga_path")
    return Path(custom).expanduser() if custom else data_dir(home, app_id) / "pga.db"


def coverart_dir(home: Path, app_id: str) -> Path:
    return data_dir(home, app_id) / "coverart"
