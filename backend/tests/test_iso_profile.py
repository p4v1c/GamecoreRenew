"""The installation ISO, checked without building one.

`mkarchiso` needs root, installs packages and mounts loop devices, so nothing
here builds an image — and neither does CI's own lint job. That leaves a profile
whose failures all appear in the same place: on a stranger's machine, after they
burned a stick, with no log to send back.

So the profile is resolved statically instead. Every test below stands for a
failure that has no other detector:

  · a package added to arch.sh and not to the ISO is a box installed offline
    with no Vulkan driver, and pacman has no mirror to fix it from;
  · a live-session file the disk installer forgets to strip is a machine that
    boots the INSTALLER off its own disk, for ever;
  · an ISO label with a lowercase letter in it is an image that boots to
    "Waiting for device" and stops.

None of that is visible to shellcheck, and none of it is visible until the ISO
has already shipped.
"""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ISO = REPO / "install/iso"
ARCH_SH = REPO / "install/arch.sh"
DISK_INSTALL = ISO / "airootfs/usr/local/bin/gamecore-disk-install.sh"


def _uncommented(path: Path) -> str:
    """File text with whole-line comments dropped.

    Every one of these files explains itself at length, and several of them
    discuss the very strings being searched for — `packages.x86_64` names
    `pacman -S --needed` in prose, and a test that counted that as a package
    would pass on a profile that shipped none.
    """
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))


def iso_package_list() -> set[str]:
    return {ln.strip() for ln in _uncommented(ISO / "packages.x86_64").splitlines() if ln.strip()}


def arch_sh_packages() -> set[str]:
    """Package names install/arch.sh asks pacman for.

    Four shapes carry them: the PKGS array, the `PKGS+=(…)` the GPU and kernel
    branches append, `add_lib32`, and `pacman_optional`. Names built from a
    variable are skipped — `linux${KSHORT}${KRT}-headers` cannot be resolved
    without knowing the machine, and is not this test's business.
    """
    body = _uncommented(ARCH_SH)
    names: set[str] = set()
    for m in re.finditer(r"PKGS\+?=\(([^)]*)\)", body, re.S):
        names.update(m.group(1).split())
    for m in re.finditer(r"^\s*add_lib32\s+(.+)$", body, re.M):
        names.update(m.group(1).split())
    for m in re.finditer(r"^\s*pacman_optional\s+(\S+)", body, re.M):
        names.add(m.group(1))
    return {n.strip("\"'") for n in names if not re.search(r"[${}@]", n.strip("\"'"))}


# The ISO pins the stock `linux` kernel (packages.x86_64), so arch.sh's other
# kernel branches cannot be taken on a machine installed from it: the zen
# headers are for a kernel the image does not contain, and the Manjaro
# `linux<NN>-headers` names are built from `uname -r` and are already skipped as
# dynamic. Listing the exception here rather than widening the parser keeps the
# next person from quietly adding a second one.
KERNEL_VARIANTS = {"linux-zen-headers"}


def test_the_iso_ships_every_package_the_installer_asks_pacman_for():
    """The drift that turns an offline install into a degraded box.

    Adding a package to arch.sh is a one-line change nobody thinks of as
    touching the ISO. But an install from the ISO is a copy of the live root
    with no mirror behind it: `pacman -S --needed` cannot fetch what the image
    did not ship, and arch.sh's offline branch can only report it by name.
    """
    missing = sorted(arch_sh_packages() - iso_package_list() - KERNEL_VARIANTS)
    assert missing == [], (
        "install/arch.sh installs packages the ISO does not carry:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd them to install/iso/packages.x86_64 — an offline install "
          "has no way to fetch them.")


def test_the_profile_carries_the_three_files_mkarchiso_requires():
    for name in ("profiledef.sh", "packages.x86_64", "pacman.conf"):
        assert (ISO / name).is_file(), f"install/iso/{name} is missing — mkarchiso will not start"


def test_the_volume_label_is_a_legal_iso9660_identifier():
    """A lowercase letter here is an image that boots to "Waiting for device".

    The label is the ONLY thing the archiso initramfs hook has to find the
    squashfs by (`archisolabel=` on the kernel command line), and ISO-9660
    allows A-Z, 0-9 and underscore in 32 characters. mkisofs does not reject a
    bad one — it silently writes something else, and the boot then hangs
    looking for a device that will never appear.
    """
    m = re.search(r"^iso_label=(.+)$", (ISO / "profiledef.sh").read_text(encoding="utf-8"), re.M)
    assert m, "profiledef.sh no longer sets iso_label"
    value = m.group(1).strip()
    # Only the literal prefix — the part a human types. The rest is a `$(date …)`
    # substitution that mkarchiso expands, and it contains quotes of its own, so
    # it cannot be matched with a quoted-string pattern. Digits are all it can
    # ever produce anyway.
    literal = value.lstrip('"').split("$")[0]
    assert literal, f"iso_label {value} starts with a substitution — nothing to check"
    assert re.fullmatch(r"[A-Z0-9_]+", literal), (
        f"iso_label {value} has a character ISO-9660 does not allow "
        "(A-Z, 0-9, underscore only) — the image would boot to 'Waiting for device'")


def test_every_bootmode_has_the_configuration_it_needs():
    """A bootmode listed with no config is an entry that boots to a blank menu.

    mkarchiso does not check this: it copies whatever the profile has and
    produces an image regardless.
    """
    profile = (ISO / "profiledef.sh").read_text(encoding="utf-8")
    m = re.search(r"bootmodes=\((.*?)\)", profile, re.S)
    assert m, "profiledef.sh no longer declares bootmodes"
    modes = re.findall(r"'([^']+)'", m.group(1))
    assert modes, "bootmodes is empty — the ISO would boot on nothing"

    for mode in modes:
        if mode.startswith("bios."):
            assert (ISO / "syslinux/syslinux.cfg").is_file(), \
                f"bootmode '{mode}' needs syslinux/syslinux.cfg"
        elif mode.startswith("uefi-"):
            entries = list((ISO / "efiboot/loader/entries").glob("*.conf"))
            assert entries, f"bootmode '{mode}' needs efiboot/loader/entries/*.conf"
            assert (ISO / "efiboot/loader/loader.conf").is_file(), \
                f"bootmode '{mode}' needs efiboot/loader/loader.conf"


@pytest.mark.parametrize(
    "entry", sorted((ISO / "efiboot/loader/entries").glob("*.conf")), ids=lambda p: p.name)
def test_boot_entries_use_the_placeholders_mkarchiso_substitutes(entry):
    """A hardcoded path or label here survives every rename silently.

    mkarchiso rewrites %INSTALL_DIR% and %ARCHISO_LABEL% when it stages these
    files. An entry that spells either one out keeps booting until the day
    profiledef.sh changes, and then boots nothing.
    """
    text = entry.read_text(encoding="utf-8")
    assert "%INSTALL_DIR%" in text, f"{entry.name} hardcodes the install dir"
    assert "%ARCHISO_LABEL%" in text or "%ARCHISO_UUID%" in text, \
        f"{entry.name} does not tell the initramfs which medium to look for"


def test_the_live_session_starts_from_either_login_shell():
    """The failure that looks exactly like a working ISO.

    archiso's own profile ships only .zlogin because releng pins root's shell to
    zsh. This profile does not pin one, and a root shell of /bin/bash reads
    neither .zlogin nor .zprofile — the ISO would boot, autologin would work,
    and the operator would be sitting at a root prompt with no installer and
    nothing anywhere saying why.
    """
    root = ISO / "airootfs/root"
    for shell_file in (".zlogin", ".bash_profile"):
        assert (root / shell_file).is_file(), f"airootfs/root/{shell_file} is missing"
        assert ".automated_script.sh" in (root / shell_file).read_text(encoding="utf-8"), \
            f"airootfs/root/{shell_file} no longer reaches .automated_script.sh"


def test_every_script_the_profile_ships_is_marked_executable():
    """profiledef.sh's file_permissions is the only thing that sets the mode.

    Git records an exec bit, mkarchiso does not read it — it applies
    file_permissions and nothing else. A script missing from that table lands in
    the image mode 644, and `startx` then exits with "no such file" on a file
    that is plainly there.
    """
    profile = (ISO / "profiledef.sh").read_text(encoding="utf-8")
    declared = set(re.findall(r'\["([^"]+)"\]=', profile))
    airootfs = ISO / "airootfs"
    missing = []
    for script in sorted((airootfs / "usr/local/bin").glob("*")):
        target = "/" + str(script.relative_to(airootfs))
        if target not in declared:
            missing.append(target)
    assert missing == [], (
        "these ship in the image with no mode set in profiledef.sh's "
        "file_permissions:\n  " + "\n  ".join(missing))


# ── the disk installer ─────────────────────────────────────────────────────

def test_the_disk_installer_refuses_to_run_outside_the_live_iso():
    """The one check that protects the machine this repository is edited on.

    gamecore-disk-install.sh takes a disk and erases it, and it lives in a git
    checkout people open in an editor. /run/archiso exists on a booted GameCore
    ISO and nowhere else.

    The guard is also asserted to come BEFORE the first destructive command:
    ordering is the whole point, and a check that runs after `sgdisk --zap-all`
    is not a check.
    """
    text = DISK_INSTALL.read_text(encoding="utf-8")
    lines = text.splitlines()
    guard = next((i for i, ln in enumerate(lines)
                  if re.match(r"\s*\[\[\s*-d\s+/run/archiso\s*\]\]", ln)), None)
    assert guard is not None, (
        "gamecore-disk-install.sh no longer refuses to run outside the live ISO")

    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#"):
            continue
        if re.search(r"^\s*run\s+(sgdisk|mkfs|partprobe)\b", ln):
            assert i > guard, (
                f"line {i + 1} touches the disk before the /run/archiso guard on "
                f"line {guard + 1}")


def test_the_disk_installer_strips_every_live_only_file_the_profile_ships():
    """Otherwise the installed box boots the installer off its own disk.

    The install is a copy of the live root, so everything that makes the ISO
    auto-start a wizard is copied too. Each of these has to be removed on the
    target, and the list is derived from what the profile actually ships rather
    than typed out — a new autostart file added to airootfs/ and forgotten here
    is exactly the bug this catches.
    """
    text = DISK_INSTALL.read_text(encoding="utf-8")
    airootfs = ISO / "airootfs"

    live_only = [airootfs / "etc/systemd/system/getty@tty1.service.d/autologin.conf"]
    live_only += sorted((airootfs / "usr/local/bin").glob("*"))
    live_only += [p for p in sorted((airootfs / "root").glob(".*")) if p.is_file()]

    not_stripped = []
    for path in live_only:
        target = "/" + str(path.relative_to(airootfs))
        if f"/mnt{target}" not in text:
            not_stripped.append(target)
    assert not_stripped == [], (
        "gamecore-disk-install.sh copies these to the target and never removes "
        "them:\n  " + "\n  ".join(not_stripped)
        + "\n\nEach one makes the installed machine boot the installer again.")


def test_the_disk_installer_hands_over_to_arch_sh_rather_than_running_it():
    """arch.sh cannot run under arch-chroot, and the split is load-bearing.

    It calls `systemctl enable --now` on several units with no guard, and inside
    a chroot there is no systemd to answer: the first one fails, `set -e` fires,
    and the install ends with a partitioned disk and no bootloader. If someone
    ever "simplifies" this by calling arch.sh directly, this is what says no.
    """
    text = DISK_INSTALL.read_text(encoding="utf-8")
    # An INVOCATION, not a mention: the script names arch.sh in a `die` message
    # and in its header, and both have to stay allowed. Only `bash …/arch.sh`,
    # `source …/arch.sh` or an arch-chroot carrying it are the mistake.
    invocations = [
        ln for ln in _uncommented(DISK_INSTALL).splitlines()
        if re.search(r"(?:^|[;&|]|\barch-chroot\b.*)\s*(?:bash|sh|source|\.)\s+\S*arch\.sh", ln)
    ]
    assert invocations == [], (
        "gamecore-disk-install.sh runs arch.sh itself — it cannot, there is no "
        "systemd inside arch-chroot. Arm gamecore-firstboot.service instead:\n  "
        + "\n  ".join(invocations))
    assert "gamecore-firstboot.service" in text, \
        "nothing arms the first-boot install — the disk would boot to a bare Arch"


def test_the_firstboot_script_reads_the_installers_exit_code_not_tees():
    """`$?` after a pipe into tee is tee's status, which is always 0.

    That turns a failed install into a success, a reboot, and a black screen in
    somebody's living room.
    """
    # Comment-stripped, and that is not fussiness: the line above the real one
    # says "PIPESTATUS, not $?", so a version that had regressed to `rc="$?"`
    # still contained the word and this test passed on it.
    body = _uncommented(REPO / "install/bin/gamecore-firstboot")
    assert "PIPESTATUS" in body, (
        "gamecore-firstboot no longer reads PIPESTATUS — a failed arch.sh piped "
        "into tee would report success")


# ── arch.sh, offline ───────────────────────────────────────────────────────

@pytest.mark.parametrize("command", ["pacman -Syu", "npm install"])
def test_the_steps_that_need_a_network_are_guarded(command):
    """An unguarded download is an ISO install that dies partway through.

    `pacman -Syu` with no route fails at 6 %, before the user account and before
    a single service; the frontend's `npm install` fails at 93 %, after
    everything is wired up.
    """
    lines = _uncommented(ARCH_SH).splitlines()
    hits = [i for i, ln in enumerate(lines) if command in ln]
    assert hits, f"'{command}' is gone from arch.sh — this test needs updating"
    for i in hits:
        window = "\n".join(lines[max(0, i - 6):i + 1])
        assert "NET_OK" in window, (
            f"'{command}' on line {i + 1} of the comment-stripped script runs "
            "with no offline guard")


def test_pip_can_install_from_the_wheelhouse_the_iso_stages():
    body = _uncommented(ARCH_SH)
    assert "--find-links" in body and "GAMECORE_OFFLINE" in body, (
        "arch.sh no longer uses the staged wheelhouse — an offline install "
        "would have no backend at all")


# ── the unattended conf, exercised for real ────────────────────────────────

def _run_validate(tmp_path: Path, conf_body: str) -> subprocess.CompletedProcess:
    """Run arch.sh's OWN validate_conf against a conf file.

    The function is extracted from the shipped script rather than copied here:
    a copy would keep passing after the real one was deleted. arch.sh cannot
    simply be executed — it demands root on its 200th line — so the validation
    block is sourced on its own, with the three reporting helpers stubbed.
    """
    block = subprocess.run(
        ["sed", "-n", "/^# ── Unattended conf validation ───/,/^\\[\\[ \\$EUID -eq 0 \\]\\]/p",
         str(ARCH_SH)],
        capture_output=True, text=True, check=True).stdout
    block = "\n".join(block.splitlines()[:-1])          # drop the EUID line itself
    assert "validate_conf()" in block, \
        "the validation block moved — this harness no longer extracts it"

    conf = tmp_path / "gamecore-install.conf"
    conf.write_text(conf_body, encoding="utf-8")
    harness = tmp_path / "harness.sh"
    harness.write_text(textwrap.dedent(f"""\
        set -euo pipefail
        die()  {{ echo "DIE: $*" >&2; exit 1; }}
        warn() {{ echo "WARN: $*"; }}
        info() {{ :; }}
        SCRIPT_DIR={REPO / 'install'}
        CONF="$1"
        source "$CONF"
        GAMECORE_PATH="${{GAMECORE_PATH:-/opt/GameCore}}"
        WEB_PORT="${{WEB_PORT:-8765}}"
        {block}
        validate_conf
        echo ACCEPTED
        """), encoding="utf-8")
    return subprocess.run(["bash", str(harness), str(conf)],
                          capture_output=True, text=True, timeout=30)


def test_a_well_formed_conf_is_accepted(tmp_path):
    """The half that keeps the other half honest.

    A validator that rejects everything passes every rejection test there is.
    """
    r = _run_validate(tmp_path, "USER_NAME=pavic\nGAMECORE_PATH=/opt/GameCore\nWEB_PORT=8765\n")
    assert "ACCEPTED" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("field,body", [
    # Each of these installed a box that came up broken, with the failure
    # surfacing somewhere that never mentions the conf.
    ("USER_NAME",     "USER_NAME='pa vic'"),                             # visudo rejects the drop-in, at 84 %
    ("GAMECORE_PATH", 'USER_NAME=pavic\nGAMECORE_PATH="/opt/Game Core"'),  # systemd splits ExecStart in two
    ("GAMECORE_PATH", "USER_NAME=pavic\nGAMECORE_PATH=/"),                # the whole filesystem
    ("GAMECORE_PATH", "USER_NAME=pavic\nGAMECORE_PATH=/opt/GameCore/"),   # trailing slash
    ("GAMECORE_DATA", 'USER_NAME=pavic\nGAMECORE_DATA="relative/path"'),
    ("WEB_PORT",      "USER_NAME=pavic\nWEB_PORT=http"),                  # Caddy never answers
    ("WEB_PORT",      "USER_NAME=pavic\nWEB_PORT=99999"),
    ("ADDONS",        'USER_NAME=pavic\nADDONS="rom-manager ../../etc"'),  # reaches gamecore-addon as root
])
def test_a_malformed_conf_is_refused_before_anything_is_installed(tmp_path, field, body):
    r = _run_validate(tmp_path, body + "\n")
    assert r.returncode != 0, f"{field} accepted '{body}':\n{r.stdout}{r.stderr}"
    assert field in r.stderr, f"the refusal does not name {field}:\n{r.stderr}"


def documented_conf_keys() -> set[str]:
    """The keys install.conf.example describes, commented-out ones included.

    This is the same list arch.sh's validate_conf reads at run time to decide
    what counts as a typo — so it is the definition of "a known key", not a
    second copy of it.
    """
    example = (REPO / "install/install.conf.example").read_text(encoding="utf-8")
    return set(re.findall(r"^#?([A-Za-z_][A-Za-z0-9_]*)=", example, re.M))


def test_every_conf_key_the_installers_write_is_documented():
    """An undocumented key makes arch.sh warn "unknown key" on every install.

    Three things write this file — the wizard, the ISO's guided install, and
    whoever scripts a fleet — and arch.sh checks what it is given against
    install.conf.example. A key added to a writer and not to the example turns
    a correct conf into a warning that says the setting was ignored, which is
    the opposite of what happened and sends the reader hunting for a typo that
    is not there.
    """
    writers = {
        # `f"KEY={…}"` — the `{` is what separates a conf line from the shell
        # snippets in the same file, which look like `"SRC=$(mktemp -d …); "`
        # and are variables of the install engine, not keys of the conf.
        "install/installer-gui/gamecore_installer.py": re.compile(
            r'^\s*f"([A-Z][A-Z0-9_]*)=\{'),
        "install/iso/airootfs/usr/local/bin/gamecore-disk-install.sh": re.compile(
            r'^\s*echo "([A-Z][A-Z0-9_]*)='),
    }
    documented = documented_conf_keys()
    undocumented = []
    for name, pattern in writers.items():
        for line in (REPO / name).read_text(encoding="utf-8").splitlines():
            m = pattern.match(line)
            if m and m.group(1) not in documented:
                undocumented.append(f"{name}: {m.group(1)}")
    assert undocumented == [], (
        "these are written into a gamecore-install.conf but are not documented "
        "in install/install.conf.example, so arch.sh reports them as unknown:\n  "
        + "\n  ".join(undocumented))


def test_the_wizard_partitions_on_the_iso_and_downloads_nowhere():
    """On the live medium the release is already there — reaching for GitHub is
    both pointless and a hard failure on a machine with no network.
    """
    text = (REPO / "install/installer-gui/gamecore_installer.py").read_text(encoding="utf-8")
    assert "gamecore-disk-install.sh" in text, \
        "the wizard no longer runs the guided disk install on the ISO"
    # The ISO branch must come FIRST: the download engine is the else-of-last
    # resort, and `local_repo` is truthy on the ISO too (the payload is a
    # checkout), so an ISO test placed after it would never be reached.
    iso_at = text.index("if w.iso_src is not None:")
    repo_at = text.index("elif w.local_repo:")
    assert iso_at < repo_at, \
        "the ISO branch is tested after local_repo, so it can never be taken"


def test_a_mistyped_key_is_reported_rather_than_silently_ignored(tmp_path):
    """`EMULATOR=rpcs3` leaves EMULATORS at its default and installs all thirteen.

    A warning and not a refusal: a fleet script may legitimately carry its own
    variables in the same file.
    """
    r = _run_validate(tmp_path, "USER_NAME=pavic\nEMULATOR=rpcs3\n")
    assert "ACCEPTED" in r.stdout, r.stdout + r.stderr
    assert "EMULATOR" in r.stdout, f"the unknown key was not reported:\n{r.stdout}"
