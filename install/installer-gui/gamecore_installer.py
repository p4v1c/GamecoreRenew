#!/usr/bin/env python3
"""GameCore — native graphical installer (QWizard).

A single-binary desktop installer (PyInstaller, see build.sh) in the
spirit of install4j/Windows installers: Welcome → System → Install type →
Emulators → Addons → API keys → Summary → Install progress.

It only collects choices; the actual work is done by arch.sh --unattended
(same engine as the CLI and the future GameCore OS ISO), elevated through
pkexec (polkit password dialog) unless already running as root.

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
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
    QSpinBox, QVBoxLayout, QWizard, QWizardPage,
)

GITHUB_REPO = "p4v1c/GamecoreRenew"
ADDONS_REPO = "https://github.com/p4v1c/gamecore-addons.git"

EMULATORS = [
    ("azahar",      "Azahar",       "Nintendo 3DS"),
    ("rpcs3",       "RPCS3",        "PlayStation 3"),
    ("pcsx2",       "PCSX2",        "PlayStation 2"),
    ("duckstation", "DuckStation",  "PlayStation 1"),
    ("dolphin",     "Dolphin",      "GameCube / Wii"),
    ("melonds",     "melonDS",      "Nintendo DS"),
    ("gopher64",    "gopher64",     "Nintendo 64"),
    ("mgba",        "mGBA",         "Game Boy Advance"),
    ("ppsspp",      "PPSSPP",       "PSP"),
    ("cemu",        "Cemu",         "Wii U"),
    ("ryujinx",     "Ryujinx",      "Nintendo Switch"),
    ("shadps4",     "shadPS4",      "PlayStation 4"),
    ("xenia",       "Xenia Canary", "Xbox 360 (Wine)"),
    ("steam",       "Steam",        "PC"),
]

# Shown if the addons repo is unreachable at install time.
FALLBACK_ADDONS = [
    {"name": "rom-manager",   "label": "ROMs",  "description": "Upload ROMs from the browser", "default": True},
    {"name": "rpcs3-manager", "label": "RPCS3", "description": "Configure PS3 games remotely", "default": False},
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


class AddonsFetcher(QThread):
    ready = Signal(list, str)

    def run(self):
        tmp = Path(tempfile.gettempdir()) / "gamecore-installer-addons"
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
                meta = json.loads(f.read_text())
                addons.append(meta)
            self.ready.emit(addons, "")
        except Exception as e:
            self.ready.emit(FALLBACK_ADDONS, f"addons repo unreachable ({e}) — showing known addons")


class Pages:
    WELCOME, SYSTEM, MODE, EMULATORS, ADDONS, KEYS, SUMMARY, INSTALL = range(8)


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


class SystemPage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("System"))
        lay.addWidget(subtitle("The Linux user that runs GameCore (created if missing, "
                               "auto-login is configured for it) and the install location."))
        self.user = QLineEdit(default_user())
        self.path = QLineEdit("/opt/GameCore")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(8765)
        for cap, w in (("Username", self.user), ("Install path", self.path), ("Backend port", self.port)):
            c = QLabel(cap.upper()); c.setObjectName("hint")
            lay.addSpacing(8); lay.addWidget(c); lay.addWidget(w)
        lay.addStretch()

    def validatePage(self):
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", self.user.text().strip()):
            QMessageBox.warning(self, "GameCore", "Invalid username (lowercase, no space).")
            return False
        if not self.path.text().strip().startswith("/"):
            QMessageBox.warning(self, "GameCore", "The install path must be absolute.")
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
        if self.checks:
            return
        self._fetcher = AddonsFetcher()
        self._fetcher.ready.connect(self._fill)
        self._fetcher.start()

    def _fill(self, addons, warning):
        self.status.setText(warning or f"{len(addons)} addon(s) available.")
        for a in addons:
            cb = QCheckBox(f"{a.get('label', a['name'])}  —  {a.get('description', '')}")
            cb.setChecked(bool(a.get("default")))
            self.checks[a["name"]] = cb
            self.box.addWidget(cb)


class KeysPage(QWizardPage):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(title("API keys — all optional"))
        lay.addWidget(subtitle("Leave empty to skip: EmberTV then runs in demo mode and covers are "
                               "fetched without TheGamesDB. You can add them later."))
        self.twitch_id = QLineEdit(); self.twitch_id.setPlaceholderText("dev.twitch.tv/console/apps")
        self.twitch_secret = QLineEdit(); self.twitch_secret.setEchoMode(QLineEdit.Password)
        self.tgdb = QLineEdit(); self.tgdb.setEchoMode(QLineEdit.Password)
        for cap, w in (("Twitch Client ID", self.twitch_id),
                       ("Twitch Client Secret", self.twitch_secret),
                       ("TheGamesDB API key (game covers)", self.tgdb)):
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
        src = "local repository checkout" if w.local_repo else "latest GitHub release (downloaded)"
        rows = [
            ("User", c["user"]), ("Install path", c["path"]), ("Backend port", str(c["port"])),
            ("Type", c["mode"]), ("Emulators", emus), ("Addons", c["addons"] or "none"),
            ("Twitch (EmberTV)", "credentials set" if c["twitch_id"] else "demo mode"),
            ("TheGamesDB", "key set" if c["tgdb_key"] else "skipped"),
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
        self.sub = subtitle("Packages and emulators take a while — the log follows in real time.")
        lay.addWidget(self.sub)
        self.bar = QProgressBar(); self.bar.setRange(0, 0)
        lay.addWidget(self.bar)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        lay.addWidget(self.log, stretch=1)
        self.proc: QProcess | None = None
        self.done = False
        self.conf_path = ""

    def initializePage(self):
        w: "InstallerWizard" = self.wizard()
        c = w.collect()
        conf = "\n".join([
            "# gamecore-install.conf — generated by the GameCore installer",
            f"USER_NAME={shlex.quote(c['user'])}",
            f"GAMECORE_PATH={shlex.quote(c['path'])}",
            f"WEB_PORT={c['port']}",
            f"MODE={c['mode']}",
            f"EMULATORS={shlex.quote(c['emulators'])}",
            f"ADDONS={shlex.quote(c['addons'])}",
            f"TWITCH_CLIENT_ID={shlex.quote(c['twitch_id'])}",
            f"TWITCH_CLIENT_SECRET={shlex.quote(c['twitch_secret'])}",
            f"TGDB_API_KEY={shlex.quote(c['tgdb_key'])}",
        ]) + "\n"
        fd, self.conf_path = tempfile.mkstemp(prefix="gamecore-install-", suffix=".conf")
        with os.fdopen(fd, "w") as f:
            f.write(conf)
        os.chmod(self.conf_path, 0o600)

        if w.local_repo:
            engine = f"bash {shlex.quote(str(w.local_repo / 'install' / 'arch.sh'))} --unattended {shlex.quote(self.conf_path)}"
        else:
            # Standalone binary: fetch the latest full release then install from it.
            engine = (
                "set -e; SRC=$(mktemp -d /tmp/gamecore-src-XXXX); "
                f"echo '[installer] Downloading the latest GameCore release…'; "
                f"URL=$(curl -sf https://api.github.com/repos/{GITHUB_REPO}/releases/latest "
                "| python3 -c 'import json,sys;d=json.load(sys.stdin);"
                "print(next(a[\"browser_download_url\"] for a in d[\"assets\"] "
                "if a[\"name\"]==\"gamecore-full.tar.gz\"))'); "
                "curl -#L -o \"$SRC/gc.tar.gz\" \"$URL\"; "
                "echo '[installer] Extracting…'; tar -xzf \"$SRC/gc.tar.gz\" -C \"$SRC\"; "
                f"bash \"$SRC/install/arch.sh\" --unattended {shlex.quote(self.conf_path)}"
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

    def _on_output(self):
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        # strip ANSI colors from arch.sh
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        sb = self.log.verticalScrollBar()
        stick = sb.value() >= sb.maximum() - 4
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(text)
        if stick:
            sb.setValue(sb.maximum())

    def _on_finished(self, code, _status):
        self._finish(code)

    def _finish(self, code):
        self.done = True
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if code == 0 else 0)
        if code == 0:
            self.head.setText("Installation complete 🎉")
            self.sub.setText("Reboot the machine — GameCore starts automatically on the TV. "
                             "ROM upload and addons are linked from the interface.")
        else:
            self.head.setText("Installation failed")
            self.sub.setText(f"The engine exited with code {code}. Fix the issue above and "
                             "run the installer again — it is safe to re-run.")
        try:
            os.unlink(self.conf_path)  # holds API secrets
        except OSError:
            pass
        self.completeChanged.emit()

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
        self.setPage(Pages.ADDONS, AddonsPage())
        self.setPage(Pages.KEYS, KeysPage())
        self.setPage(Pages.SUMMARY, SummaryPage())
        self.setPage(Pages.INSTALL, InstallPage())
        for pid in self.pageIds():
            # QWizardPage ignores stylesheet backgrounds without this flag
            self.page(pid).setAttribute(Qt.WA_StyledBackground, True)

    def collect(self) -> dict:
        sysp: SystemPage = self.page(Pages.SYSTEM)
        mode: ModePage = self.page(Pages.MODE)
        emus: EmulatorsPage = self.page(Pages.EMULATORS)
        addons: AddonsPage = self.page(Pages.ADDONS)
        keys: KeysPage = self.page(Pages.KEYS)
        checked = [eid for eid, cb in emus.checks.items() if cb.isChecked()]
        if addons.checks:
            addon_names = " ".join(n for n, cb in addons.checks.items() if cb.isChecked())
        else:
            # addons fetch still pending (user rushed through) — keep the default
            addon_names = "rom-manager"
        return {
            "user": sysp.user.text().strip(),
            "path": sysp.path.text().strip(),
            "port": sysp.port.value(),
            "mode": "minimal" if mode.minimal.isChecked() else "full",
            "emulators": "all" if len(checked) == len(EMULATORS) else " ".join(checked),
            "addons": addon_names,
            "twitch_id": keys.twitch_id.text().strip(),
            "twitch_secret": keys.twitch_secret.text().strip(),
            "tgdb_key": keys.tgdb.text().strip(),
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
