#!/usr/bin/env python3
"""GameCore — native graphical installer (QWizard).

A single-binary desktop installer (PyInstaller, see build.sh) in the
spirit of install4j/Windows installers: Welcome → System → Install type →
Emulators → Applications → Addons → API keys → Summary → Install progress.

It only collects choices; the actual work is done by arch.sh --unattended
(the same engine as the CLI), elevated through pkexec (polkit password
dialog) unless already running as root.

Runs from a repo checkout (uses the local arch.sh) or standalone: it then
downloads the latest gamecore-full.tar.gz release and installs from it.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QSpinBox, QVBoxLayout, QWizard, QWizardPage,
)

GITHUB_REPO = "p4v1c/GamecoreRenew"
ADDONS_REPO = "https://github.com/p4v1c/gamecore-addons.git"

# Progress markers emitted by arch.sh when GAMECORE_PROGRESS=1:
#   @GC-PROGRESS@ <0-100> <step label>
PROGRESS_RE = re.compile(r"^@GC-PROGRESS@\s+(\d{1,3})\s*(.*)$")

# The catalogue, generated from catalog/<id>/pack.json by
# scripts/gen-catalog.py. It is baked into a module rather than read at runtime
# because this wizard is a PyInstaller onefile binary: it runs BEFORE the
# repository exists on the machine.
#
# Hand-maintaining it here is how the N64 tick box went on offering "gopher64"
# long after that slot started launching Rosalie's Mupen GUI.
from catalog_data import APPS, EMULATORS

# Shown if the addons repo is unreachable at install time.
FALLBACK_ADDONS = [
    {"name": "rom-manager",   "label": "ROMs",  "description": "Upload ROMs from the browser", "default": True},
    {"name": "rpcs3-manager", "label": "RPCS3", "description": "Configure PS3 games remotely", "default": False},
    {"name": "save-manager",  "label": "Saves", "description": "Back up, restore & transfer emulator saves", "default": False},
]

DARK_QSS = """
QWizard, QWizardPage { background: #0e1117; }
QLabel { color: #dde1ed; font-size: 13px; }
QLabel#title { color: #ffffff; font-size: 22px; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #7d8499; font-size: 12px; }
QLineEdit, QSpinBox, QPlainTextEdit {
  background: #1c202c; color: #dde1ed; border: 1px solid #2a2f3d;
  border-radius: 7px; padding: 8px 10px; font-size: 13px;
  selection-background-color: #5c7cfa;
}
QLineEdit:focus, QSpinBox:focus { border-color: #5c7cfa; }
QCheckBox, QRadioButton { color: #dde1ed; font-size: 13px; spacing: 9px; padding: 4px; }
QCheckBox::indicator, QRadioButton::indicator { width: 17px; height: 17px; }
QCheckBox::indicator { border: 2px solid #7d8499; border-radius: 5px; background: transparent; }
QCheckBox::indicator:checked { background: #5c7cfa; border-color: #5c7cfa; }
QRadioButton::indicator { border: 2px solid #7d8499; border-radius: 10px; }
QRadioButton::indicator:checked { background: #5c7cfa; border-color: #5c7cfa; }
QPushButton {
  background: #5c7cfa; color: white; border: none; border-radius: 8px;
  padding: 9px 24px; font-size: 13px; font-weight: 600;
}
QPushButton:hover { background: #6d8afc; }
QPushButton:disabled { background: #2a2f3d; color: #596074; }
QPushButton[flat="true"] { background: transparent; color: #7d8499; border: 1px solid #2a2f3d; }
QProgressBar {
  background: #1c202c; border: none; border-radius: 6px; height: 10px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: #5c7cfa; border-radius: 6px; }
QPlainTextEdit { font-family: monospace; font-size: 11px; background: #07080c; color: #9aa3b8; }
"""


def repo_root() -> Path | None:
    """When running next to a GamecoreRenew checkout, install from it."""
    for base in (Path(__file__).resolve(), Path(sys.argv[0]).resolve()):
        for parent in [base, *base.parents]:
            if (parent / "install" / "arch.sh").is_file() and (parent / "backend").is_dir():
                return parent
    return None


def default_user() -> str:
    u = os.environ.get("SUDO_USER") or os.environ.get("USER", "")
    return u if u != "root" else ""


def addons_cache() -> Path:
    """Private per-user checkout for the addons list.

    Never a fixed name under /tmp: that path is world-writable and predictable,
    so any local account could plant a git repo there first and decide which
    addon names this wizard writes into the conf — names arch.sh then feeds to
    `gamecore-addon install` with root behind it.
    """
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    d = base / "gamecore-installer"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d / "addons"


# An addon name reaches `for addon in $ADDONS` in arch.sh unquoted, then
# `gamecore-addon install "$addon"`. It comes from a JSON file fetched over the
# network, so it is validated here rather than trusted there.
ADDON_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}$")


class AddonsFetcher(QThread):
    ready = Signal(list, str)

    def run(self):
        tmp = addons_cache()
        try:
            if (tmp / ".git").exists():
                subprocess.run(["git", "-C", str(tmp), "pull", "-q", "--ff-only"], timeout=30, check=False)
            else:
                subprocess.run(["git", "clone", "-q", "--depth", "1", ADDONS_REPO, str(tmp)],
                               timeout=60, check=True, capture_output=True)
            addons = []
            for f in sorted(tmp.glob("addons/*/addon.json")):
                if f.parent.name.startswith("_"):
                    continue
                try:
                    # utf-8-sig tolerates a UTF-8 BOM (Windows-saved JSON);
                    # skip a single malformed addon.json instead of dropping
                    # the whole list to the fallback.
                    meta = json.loads(f.read_text(encoding="utf-8-sig"))
                except (ValueError, OSError):
                    continue
                if not isinstance(meta, dict) or not ADDON_NAME_RE.fullmatch(str(meta.get("name", ""))):
                    continue
                addons.append(meta)
            self.ready.emit(addons or FALLBACK_ADDONS, "")
        except Exception as e:
            self.ready.emit(FALLBACK_ADDONS, f"addons repo unreachable ({e}) — showing known addons")


class Pages:
    WELCOME, SYSTEM, MODE, EMULATORS, APPS, ADDONS, KEYS, SUMMARY, INSTALL = range(9)


def title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("title")
    return lbl


def subtitle(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("subtitle")
    lbl.setWordWrap(True)
    return lbl


class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("Welcome to GameCore"))
        lay.addWidget(subtitle(
            "This wizard installs the GameCore living-room console on this machine: "
            "the TV interface, the emulators of your choice, curated controller "
            "configurations and optional addons.\n\n"
            "The installation modifies the system (packages, services, auto-login) — "
            "run it on the machine that will live under the TV."))
        lay.addStretch()


def data_path_problem(install_path: str, data_path: str) -> str:
    """Why this data path cannot be used with this install path, or "".

    The same alphabet arch.sh's _conf_path accepts (it lands unquoted in
    systemd units), and never NESTED inside the install unless it IS the
    install: the OTA rsyncs the install tree with a fixed list of excludes, and
    a data directory under it that is not on that list would be replaced by
    the release. Equal is fine — that is the layout every box had before the
    split, and every exclude exists for it.
    """
    if not re.fullmatch(r"/[A-Za-z0-9._/+-]*", data_path) or data_path.endswith("/") and data_path != "/":
        return ("The data path must be absolute and contain no spaces or special "
                "characters.")
    if data_path == "/":
        return "The data path must not be / — that is the whole filesystem."
    inst = install_path.rstrip("/")
    if data_path != inst and (data_path + "/").startswith(inst + "/"):
        return (f"The data path must not sit inside the install path ({inst}) — an "
                "update replaces that tree. Use the install path itself, or a "
                "directory outside it such as /userdata.")
    return ""


class SystemPage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("System"))
        lay.addWidget(subtitle("The Linux user that runs GameCore (created if missing, "
                               "auto-login is configured for it), the install location, "
                               "and the password protecting the web interface on your network."))
        self.user = QLineEdit(default_user())
        self.path = QLineEdit("/opt/GameCore")
        # Where the player's files go — ROMs, saves, covers, settings — as
        # opposed to where the code goes. Separate by default: a box installed
        # with its data inside the install works, but moving the data out later
        # is a migration (scripts/migrate-userdata.py), and every consumer of
        # the data root has to be told. Deciding it here costs one field and
        # saves that whole evening.
        self.data = QLineEdit("/userdata")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(8765)
        # Without this the box ends up with no config/auth.json: the LAN UI —
        # which is the documented way to upload ROMs — can never be logged
        # into, and recovery needs SSH access to a machine designed to be
        # driven by a gamepad.
        self.web_pw = QLineEdit(); self.web_pw.setEchoMode(QLineEdit.Password)
        self.web_pw2 = QLineEdit(); self.web_pw2.setEchoMode(QLineEdit.Password)
        fields = (
            ("Username", self.user),
            ("Install path", self.path),
            ("Data path (ROMs, saves, covers) — same as the install path to keep everything in one place", self.data),
            ("Backend port", self.port),
            ("Web password (ROM upload over the network)", self.web_pw),
            ("Confirm web password", self.web_pw2),
        )
        for cap, w in fields:
            c = QLabel(cap.upper()); c.setObjectName("hint")
            lay.addSpacing(8); lay.addWidget(c); lay.addWidget(w)
        lay.addStretch()

    def validatePage(self):
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", self.user.text().strip()):
            QMessageBox.warning(self, "GameCore", "Invalid username (lowercase, no space).")
            return False
        # arch.sh interpolates this path unquoted into systemd units and a
        # .desktop Exec= line; a space there silently produces a unit that
        # never loads while the installer still reports success.
        if not re.fullmatch(r"/[A-Za-z0-9._/+-]*", self.path.text().strip()):
            QMessageBox.warning(self, "GameCore",
                                "The install path must be absolute and contain no spaces "
                                "or special characters.")
            return False
        problem = data_path_problem(self.path.text().strip(), self.data.text().strip())
        if problem:
            QMessageBox.warning(self, "GameCore", problem)
            return False
        if not self.web_pw.text():
            QMessageBox.warning(self, "GameCore",
                                "A web password is required — it protects ROM upload and "
                                "the addon pages on your local network.")
            return False
        if self.web_pw.text() != self.web_pw2.text():
            QMessageBox.warning(self, "GameCore", "The two passwords do not match.")
            return False
        return True


class ModePage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("Install type"))
        self.full = QRadioButton("Full — GameCore + emulators + curated configs + living-room apps (recommended)")
        self.minimal = QRadioButton("Minimal — GameCore interface only, no emulator, no application")
        self.full.setChecked(True)
        lay.addSpacing(10); lay.addWidget(self.full); lay.addWidget(self.minimal)
        lay.addStretch()


class EmulatorsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.addWidget(title("Emulators"))
        self.info = subtitle("")
        self.lay.addWidget(self.info)
        bar = QHBoxLayout()
        self.btn_all = QPushButton("Select all"); self.btn_none = QPushButton("Select none")
        for b in (self.btn_all, self.btn_none):
            b.setProperty("flat", True); bar.addWidget(b)
        bar.addStretch()
        self.lay.addLayout(bar)
        grid = QGridLayout(); grid.setSpacing(6)
        self.checks: dict[str, QCheckBox] = {}
        for i, (eid, label, platform) in enumerate(EMULATORS):
            cb = QCheckBox(f"{label}  ·  {platform}")
            cb.setChecked(True)
            self.checks[eid] = cb
            grid.addWidget(cb, i // 2, i % 2)
        self.lay.addLayout(grid)
        self.lay.addStretch()
        self.btn_all.clicked.connect(lambda: [c.setChecked(True) for c in self.checks.values()])
        self.btn_none.clicked.connect(lambda: [c.setChecked(False) for c in self.checks.values()])

    def initializePage(self):
        minimal = self.wizard().page(Pages.MODE).minimal.isChecked()
        self.info.setText("Minimal install — emulators are skipped (go back to pick Full)." if minimal
                          else "All selected by default — uncheck what you don't need "
                               "(Flathub, plus DuckStation AppImage and Xenia via Wine).")
        for c in self.checks.values():
            c.setEnabled(not minimal)


class AppsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.addWidget(title("Applications"))
        self.info = subtitle("")
        self.lay.addWidget(self.info)
        bar = QHBoxLayout()
        self.btn_all = QPushButton("Select all"); self.btn_none = QPushButton("Select none")
        for b in (self.btn_all, self.btn_none):
            b.setProperty("flat", True); bar.addWidget(b)
        bar.addStretch()
        self.lay.addLayout(bar)
        grid = QGridLayout(); grid.setSpacing(6)
        self.checks: dict[str, QCheckBox] = {}
        for i, (aid, label, desc) in enumerate(APPS):
            cb = QCheckBox(f"{label}  ·  {desc}")
            cb.setChecked(True)
            self.checks[aid] = cb
            grid.addWidget(cb, i // 2, i % 2)
        self.lay.addLayout(grid)
        self.lay.addStretch()
        self.btn_all.clicked.connect(lambda: [c.setChecked(True) for c in self.checks.values()])
        self.btn_none.clicked.connect(lambda: [c.setChecked(False) for c in self.checks.values()])

    def initializePage(self):
        minimal = self.wizard().page(Pages.MODE).minimal.isChecked()
        self.info.setText("Minimal install — applications are skipped (go back to pick Full)." if minimal
                          else "Living-room apps shown as tiles in GameCore — uncheck what "
                               "you don't need: it is neither installed nor shown in the UI.")
        for c in self.checks.values():
            c.setEnabled(not minimal)


class AddonsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("Addons"))
        lay.addWidget(subtitle("Optional modules (own service + web UI each). "
                               "One command to add or remove later: gamecore-addon install <name>."))
        self.status = subtitle("Fetching available addons…")
        lay.addWidget(self.status)
        self.box = QVBoxLayout()
        lay.addLayout(self.box)
        lay.addStretch()
        self.checks: dict[str, QCheckBox] = {}
        self._fetcher = None

    def initializePage(self):
        # `self.checks` is only filled once the fetch LANDS, so it cannot be the
        # guard on its own: coming back to this page while the clone is still in
        # flight (it is allowed 60 s) started a second QThread and dropped the
        # last Python reference to the first one. PySide then deletes a running
        # QThread, which aborts the process — the wizard died on a Back/Next,
        # not on anything the user did wrong.
        if self.checks or self._fetcher is not None:
            return
        self._fetcher = AddonsFetcher(self)
        self._fetcher.ready.connect(self._fill)
        self._fetcher.start()

    def _fill(self, addons, warning):
        # Queued from the worker thread: an exception escaping here is an
        # unhandled exception in a slot, which under PySide6 takes the whole
        # wizard down rather than losing one checkbox.
        try:
            self.status.setText(warning or f"{len(addons)} addon(s) available.")
            for a in addons:
                name = a.get("name")
                if not name or name in self.checks:
                    continue
                cb = QCheckBox(f"{a.get('label', name)}  —  {a.get('description', '')}")
                cb.setChecked(bool(a.get("default")))
                self.checks[name] = cb
                self.box.addWidget(cb)
        except Exception as e:  # pragma: no cover — belt and braces
            sys.stderr.write(f"[installer] addons list: {e}\n")
            self.status.setText("Addon list unreadable — install them later with gamecore-addon.")


class KeysPage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("API keys — all optional"))
        lay.addWidget(subtitle("Leave empty to skip: EmberTV then runs in demo mode and covers are "
                               "fetched without TheGamesDB or ScreenScraper. You can add them later."))
        self.twitch_id = QLineEdit(); self.twitch_id.setPlaceholderText("dev.twitch.tv/console/apps")
        self.twitch_secret = QLineEdit(); self.twitch_secret.setEchoMode(QLineEdit.Password)
        self.tgdb = QLineEdit(); self.tgdb.setEchoMode(QLineEdit.Password)
        # ScreenScraper needs two accounts, and mixing them up is the usual
        # cause of a 403 — hence a caption per field rather than one per pair.
        self.ss_dev_id = QLineEdit()
        self.ss_dev_id.setPlaceholderText("developer pseudonym, not the devinfos.php number")
        self.ss_dev_password = QLineEdit(); self.ss_dev_password.setEchoMode(QLineEdit.Password)
        self.ss_user = QLineEdit()
        self.ss_user.setPlaceholderText("your screenscraper.fr account — carries the quota")
        self.ss_password = QLineEdit(); self.ss_password.setEchoMode(QLineEdit.Password)
        for cap, w in (("Twitch Client ID", self.twitch_id),
                       ("Twitch Client Secret", self.twitch_secret),
                       ("TheGamesDB API key (game covers)", self.tgdb),
                       ("ScreenScraper dev id (asked for on their forum)", self.ss_dev_id),
                       ("ScreenScraper dev password", self.ss_dev_password),
                       ("ScreenScraper member login", self.ss_user),
                       ("ScreenScraper member password", self.ss_password)):
            c = QLabel(cap.upper()); c.setObjectName("hint")
            lay.addSpacing(8); lay.addWidget(c); lay.addWidget(w)
        lay.addStretch()


class SummaryPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setCommitPage(True)
        self.setButtonText(QWizard.CommitButton, "⚡ Install")
        lay = QVBoxLayout(self)
        lay.addWidget(title("Summary"))
        lay.addWidget(subtitle("Last check before touching the system."))
        self.recap = QLabel()
        self.recap.setTextFormat(Qt.RichText)
        self.recap.setWordWrap(True)
        lay.addSpacing(8)
        lay.addWidget(self.recap)
        lay.addStretch()

    def initializePage(self):
        w: "InstallerWizard" = self.wizard()
        c = w.collect()
        emus = "—" if c["mode"] == "minimal" else (
            f"all ({len(EMULATORS)})" if c["emulators"] == "all" else (c["emulators"] or "none"))
        apps = "—" if c["mode"] == "minimal" else (
            f"all ({len(APPS)})" if c["apps"] == "all" else (c["apps"] or "none"))
        if w.local_repo:
            src = "local repository checkout"
        else:
            src = "latest GitHub release (downloaded)"
        rows = [
            ("User", c["user"]), ("Install path", c["path"]),
            ("Data path", c["data"] + (" (inside the install)" if c["data"] == c["path"] else "")),
            ("Backend port", str(c["port"])),
            ("Type", c["mode"]), ("Emulators", emus), ("Applications", apps),
            ("Addons", c["addons"] or "none"),
            ("Web password", "set" if c["web_password"] else "NOT SET"),
            ("Twitch (EmberTV)", "credentials set" if c["twitch_id"] else "demo mode"),
            ("TheGamesDB", "key set" if c["tgdb_key"] else "skipped"),
            ("ScreenScraper", ("configured" if c["ss_user"] else "developer only (level-0 quota)")
                              if c["ss_dev_id"] else "skipped"),
            ("Install source", src),
        ]
        self.recap.setText("<table cellspacing='6'>" + "".join(
            f"<tr><td style='color:#7d8499;padding-right:24px'>{k}</td><td><b>{v}</b></td></tr>"
            for k, v in rows) + "</table>")


class InstallPage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.head = title("Installing…")
        lay.addWidget(self.head)
        self.sub = subtitle("Packages and emulators take a while — open the logs for details.")
        lay.addWidget(self.sub)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        lay.addWidget(self.bar)
        self.step = subtitle("Waiting for the engine…")
        lay.addWidget(self.step)
        row = QHBoxLayout()
        self.btn_logs = QPushButton("Show logs")
        self.btn_logs.setProperty("flat", True)
        self.btn_logs.setCheckable(True)
        self.btn_logs.toggled.connect(self._toggle_logs)
        row.addWidget(self.btn_logs); row.addStretch()
        lay.addLayout(row)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.hide()
        lay.addWidget(self.log, stretch=1)
        # keeps the header/bar top-aligned while the log is hidden
        lay.addStretch()
        self.proc: QProcess | None = None
        self.done = False
        self.conf_path = ""
        self._tail = ""  # carry-over for a marker line split across chunks

    def _toggle_logs(self, checked):
        self.log.setVisible(checked)
        self.btn_logs.setText("Hide logs" if checked else "Show logs")

    def initializePage(self):
        w: "InstallerWizard" = self.wizard()
        c = w.collect()
        conf = "\n".join([
            "# gamecore-install.conf — generated by the GameCore installer",
            f"USER_NAME={shlex.quote(c['user'])}",
            f"GAMECORE_PATH={shlex.quote(c['path'])}",
            f"GAMECORE_DATA={shlex.quote(c['data'])}",
            f"WEB_PORT={c['port']}",
            f"MODE={c['mode']}",
            f"EMULATORS={shlex.quote(c['emulators'])}",
            f"APPS={shlex.quote(c['apps'])}",
            f"ADDONS={shlex.quote(c['addons'])}",
            f"TWITCH_CLIENT_ID={shlex.quote(c['twitch_id'])}",
            f"TWITCH_CLIENT_SECRET={shlex.quote(c['twitch_secret'])}",
            f"TGDB_API_KEY={shlex.quote(c['tgdb_key'])}",
            f"SS_DEV_ID={shlex.quote(c['ss_dev_id'])}",
            f"SS_DEV_PASSWORD={shlex.quote(c['ss_dev_password'])}",
            f"SS_USER={shlex.quote(c['ss_user'])}",
            f"SS_PASSWORD={shlex.quote(c['ss_password'])}",
            # shlex.quote matters here: arch.sh `source`s this file, and a
            # password containing $, a backtick or a space would otherwise be
            # mangled or executed.
            f"WEB_PASSWORD={shlex.quote(c['web_password'])}",
        ]) + "\n"
        fd, self.conf_path = tempfile.mkstemp(prefix="gamecore-install-", suffix=".conf")
        with os.fdopen(fd, "w") as f:
            f.write(conf)
        os.chmod(self.conf_path, 0o600)

        # GAMECORE_PROGRESS=1 makes arch.sh emit the @GC-PROGRESS@ markers
        # that drive the progress bar and the step label below.
        if w.local_repo:
            engine = (
                "export GAMECORE_PROGRESS=1; "
                f"bash {shlex.quote(str(w.local_repo / 'install' / 'arch.sh'))} --unattended {shlex.quote(self.conf_path)}"
            )
        else:
            # Standalone binary: fetch the latest full release then install from it.
            # Use the stable /releases/latest/download/ redirect instead of the
            # JSON API: the anonymous API is rate-limited to 60 req/h per IP and
            # its failure used to crash the json parser with an empty stream.
            # The tarball is extracted into $SRC/src, never alongside itself:
            # arch.sh copies its whole PROJECT_ROOT into the install dir, so a
            # flat extract shipped a 13 MB gc.tar.gz into /opt/GameCore. The
            # trap runs on success and on failure alike, so the download does
            # not sit in /tmp afterwards.
            engine = (
                "set -e; export GAMECORE_PROGRESS=1; "
                "SRC=$(mktemp -d /tmp/gamecore-src-XXXXXXXX); "
                "trap 'rm -rf \"$SRC\"' EXIT; mkdir -p \"$SRC/src\"; "
                "echo '@GC-PROGRESS@ 0 Downloading the latest GameCore release'; "
                "echo '[installer] Downloading the latest GameCore release…'; "
                f"URL=https://github.com/{GITHUB_REPO}/releases/latest/download/gamecore-full.tar.gz; "
                "curl -#fL --connect-timeout 15 --retry 3 --retry-delay 5 "
                "--speed-limit 1024 --speed-time 30 -o \"$SRC/gc.tar.gz\" \"$URL\" "
                "|| { echo '[installer] Download failed — check the network connection and retry.'; exit 1; }; "
                "echo '@GC-PROGRESS@ 1 Extracting the release'; "
                "echo '[installer] Extracting…'; tar -xzf \"$SRC/gc.tar.gz\" -C \"$SRC/src\"; "
                f"bash \"$SRC/src/install/arch.sh\" --unattended {shlex.quote(self.conf_path)}"
            )

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        if os.geteuid() == 0:
            self.proc.start("bash", ["-c", engine])
        elif shutil.which("pkexec"):
            self.log.appendPlainText("[installer] Requesting administrator rights (polkit)…")
            self.proc.start("pkexec", ["bash", "-c", engine])
        else:
            self.log.appendPlainText("pkexec not found — restart the installer with sudo.")
            self._finish(1)

    def _consume_progress(self, text: str) -> str:
        """Update bar/step from @GC-PROGRESS@ lines; return text without them."""
        buf = self._tail + text
        lines = buf.split("\n")
        self._tail = lines.pop()[-4096:]  # incomplete last line, kept for next chunk
        for line in lines:
            m = PROGRESS_RE.match(line.strip())
            if m:
                self.bar.setValue(min(100, int(m.group(1))))
                if m.group(2):
                    self.step.setText(m.group(2))
        return re.sub(r"^@GC-PROGRESS@[^\n]*\n?", "", text, flags=re.M)

    def _on_output(self):
        # Never let an exception escape this slot: under PySide6 an unhandled
        # exception in a Qt slot aborts the whole application, which would kill
        # an install that is otherwise running fine.
        try:
            text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
            # strip ANSI colors from arch.sh
            text = re.sub(r"\x1b\[[0-9;]*m", "", text)
            text = self._consume_progress(text)
            sb = self.log.verticalScrollBar()
            stick = sb.value() >= sb.maximum() - 4
            self.log.moveCursor(QTextCursor.MoveOperation.End)
            self.log.insertPlainText(text)
            if stick:
                sb.setValue(sb.maximum())
        except Exception as e:
            sys.stderr.write(f"[installer] _on_output error: {e}\n")

    def _on_finished(self, code, _status):
        self._finish(code)

    def _finish(self, code):
        self.done = True
        if code == 0:
            self.bar.setValue(100)
            self.head.setText("Installation complete 🎉")
            self.sub.setText("Reboot the machine — GameCore starts automatically on the TV. "
                             "ROM upload and addons are linked from the interface.")
            self.step.setText("Done.")
        else:
            self.head.setText("Installation failed")
            self.sub.setText(f"The engine exited with code {code}. Fix the issue in the logs and "
                             "run the installer again — it is safe to re-run.")
            self.step.setText("Failed — see the logs below.")
            self.btn_logs.setChecked(True)  # surface the log where the error is
        self.cleanup_conf()
        self.completeChanged.emit()

    def cleanup_conf(self):
        """Remove the generated conf — it holds the web password and API keys.

        Also called when the wizard is closed: the file used to be unlinked only
        on a normal finish, so quitting mid-install left every secret typed into
        the wizard readable in /tmp until the next reboot.
        """
        if not self.conf_path:
            return
        try:
            os.unlink(self.conf_path)
        except OSError:
            pass
        self.conf_path = ""

    def isComplete(self):
        return self.done


class InstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GameCore installer")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage)
        self.setOption(QWizard.NoCancelButtonOnLastPage)
        self.resize(760, 560)
        self.local_repo = repo_root()
        self.setPage(Pages.WELCOME, WelcomePage())
        self.setPage(Pages.SYSTEM, SystemPage())
        self.setPage(Pages.MODE, ModePage())
        self.setPage(Pages.EMULATORS, EmulatorsPage())
        self.setPage(Pages.APPS, AppsPage())
        self.setPage(Pages.ADDONS, AddonsPage())
        self.setPage(Pages.KEYS, KeysPage())
        self.setPage(Pages.SUMMARY, SummaryPage())
        self.setPage(Pages.INSTALL, InstallPage())
        for pid in self.pageIds():
            # QWizardPage ignores stylesheet backgrounds without this flag
            self.page(pid).setAttribute(Qt.WA_StyledBackground, True)

    def reject(self):
        """Esc and the window's close button both land here (QDialog::closeEvent).

        Two things must not happen silently: walking away from an install that
        is still running as root, and leaving the conf file — web password and
        API keys — behind in /tmp.
        """
        inst: InstallPage = self.page(Pages.INSTALL)
        if inst.proc is not None and inst.proc.state() != QProcess.NotRunning:
            if QMessageBox.question(
                    self, "GameCore",
                    "An installation is running with administrator rights.\n\n"
                    "Closing this window does NOT stop it — the machine would be "
                    "left half-installed with no log to look at.\n\nClose anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return
        inst.cleanup_conf()
        addons: AddonsPage = self.page(Pages.ADDONS)
        if addons._fetcher is not None and addons._fetcher.isRunning():
            # Destroying a running QThread aborts the process. The fetch is
            # bounded by git's own timeouts, so a short wait covers the normal
            # case (the clone answering) without freezing the window.
            addons._fetcher.wait(3000)
        super().reject()

    def collect(self) -> dict:
        sysp: SystemPage = self.page(Pages.SYSTEM)
        mode: ModePage = self.page(Pages.MODE)
        emus: EmulatorsPage = self.page(Pages.EMULATORS)
        apps: AppsPage = self.page(Pages.APPS)
        addons: AddonsPage = self.page(Pages.ADDONS)
        keys: KeysPage = self.page(Pages.KEYS)
        minimal = mode.minimal.isChecked()
        # In minimal mode the tick boxes are only DISABLED, so they stay ticked
        # and collect() reported "all" — a conf that says EMULATORS=all next to
        # MODE=minimal. arch.sh happens to gate the emulator phase on MODE, so
        # nothing was installed, but the file recorded the opposite of what ran
        # and anything else reading it (a re-run, uninstall.sh) would believe
        # it.
        checked = [] if minimal else [eid for eid, cb in emus.checks.items() if cb.isChecked()]
        checked_apps = [] if minimal else [aid for aid, cb in apps.checks.items() if cb.isChecked()]
        if addons.checks:
            addon_names = " ".join(n for n, cb in addons.checks.items() if cb.isChecked())
        else:
            # addons fetch still pending (user rushed through) — keep the default
            addon_names = "rom-manager"
        return {
            "user": sysp.user.text().strip(),
            "path": sysp.path.text().strip(),
            "data": sysp.data.text().strip(),
            "port": sysp.port.value(),
            "mode": "minimal" if mode.minimal.isChecked() else "full",
            "emulators": "all" if len(checked) == len(EMULATORS) else " ".join(checked),
            "apps": "all" if len(checked_apps) == len(APPS) else " ".join(checked_apps),
            "addons": addon_names,
            "twitch_id": keys.twitch_id.text().strip(),
            "twitch_secret": keys.twitch_secret.text().strip(),
            "tgdb_key": keys.tgdb.text().strip(),
            "ss_dev_id": keys.ss_dev_id.text().strip(),
            # Not .strip()ed: a password is taken as typed. The login above is,
            # because a trailing space pasted from a browser is never intended.
            "ss_dev_password": keys.ss_dev_password.text(),
            "ss_user": keys.ss_user.text().strip(),
            "ss_password": keys.ss_password.text(),
            "web_password": sysp.web_pw.text(),
        }


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    app.setFont(QFont(app.font().family(), 10))
    wiz = InstallerWizard()
    wiz.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
