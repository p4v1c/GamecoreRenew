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


# ── mDNS ───────────────────────────────────────────────────────────────────
#
# The box is reached over the LAN at one address, and that address is a DHCP
# lease. mDNS is what replaces it with a name. Every failure below produces the
# same symptom — the name does not resolve — from a different cause, and none of
# them says anything on the box itself.


def test_the_installer_asks_for_both_halves_of_mdns():
    """Either package alone resolves nothing.

    avahi answers mDNS queries for this host; nss-mdns is the glibc plugin that
    makes the box ASK. Installing avahi alone gives a box that other machines
    can find and that cannot find anything — and the half that is missing is
    never the one named in a bug report.
    """
    pkgs = arch_sh_packages()
    for half in ("avahi", "nss-mdns"):
        assert half in pkgs, (
            f"install/arch.sh no longer installs {half} — mDNS needs both "
            f"halves, and the box is back to being reachable by IP only.")


def test_the_installer_wires_mdns_into_nsswitch_rather_than_only_installing_it():
    """The step everyone forgets, and the one with no symptom of its own.

    Installing nss-mdns does not make glibc consult it: the plugin is only
    reached when `hosts:` in /etc/nsswitch.conf names it, and the package does
    not edit that file. Skip this and avahi runs, advertises correctly, `ss`
    shows it listening — and the name still does not resolve. That is
    indistinguishable from the daemon being stopped, which is where anyone
    debugging it will look first.
    """
    body = _uncommented(ARCH_SH)
    assert "nsswitch.conf" in body, (
        "install/arch.sh installs nss-mdns but never edits /etc/nsswitch.conf. "
        "The plugin is then present and never consulted.")
    assert "mdns_minimal" in body, (
        "arch.sh touches nsswitch.conf but does not add the mdns_minimal "
        "entry — nothing routes .local lookups to avahi.")


def _run_nsswitch_edit(tmp_path: Path, hosts_line: str, runs: int = 1) -> str:
    """Run arch.sh's OWN nsswitch edit against a throwaway nsswitch.conf.

    Extracted from the shipped script rather than reimplemented, for the reason
    `_run_validate` above gives: a copy keeps passing after the real one has
    been broken. Only the path is substituted — the logic under test is the
    text that ships.
    """
    body = ARCH_SH.read_text(encoding="utf-8")
    start = body.index("NSS=/etc/nsswitch.conf")
    end = body.index("# ── Bluetooth", start)
    block = body[start:end]
    # Everything after the assignment; the harness supplies the path instead.
    block = block.split("\n", 1)[1]
    assert "mdns_minimal" in block, "the nsswitch block moved — this harness no longer extracts it"

    nss = tmp_path / "nsswitch.conf"
    nss.write_text(f"passwd: files\n{hosts_line}\nnetworks: files\n", encoding="utf-8")

    harness = tmp_path / "harness.sh"
    harness.write_text(textwrap.dedent(f"""\
        set -euo pipefail
        ok()   {{ :; }}
        warn() {{ echo "WARN: $*"; }}
        manifest_set() {{ :; }}
        NSS="{nss}"
        for _ in $(seq 1 {runs}); do
        {textwrap.indent(block, '  ')}
        done
        """), encoding="utf-8")
    r = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"the edit failed:\n{r.stdout}{r.stderr}"
    return nss.read_text(encoding="utf-8")


# The shapes a real hosts: line comes in. Arch and Manjaro do not agree, and the
# line grows entries over releases — so the edit is exercised against each
# rather than against one known-good example.
HOSTS_LINES = [
    "hosts: mymachines resolve [!UNAVAIL=return] files myhostname dns",
    "hosts: files dns myhostname",
    "hosts: files resolve myhostname dns",
]


@pytest.mark.parametrize("hosts_line", HOSTS_LINES)
def test_the_mdns_entry_lands_before_the_resolver_that_would_answer_first(tmp_path, hosts_line):
    """Order inside the hosts: line decides whether any of this works.

    `resolve` (systemd-resolved) and `dns` answer for a .local name before
    avahi ever sees the query, so an entry sitting after them is never reached.
    This is not hypothetical: the first version of the edit was a sed
    substitution, ERE has no lazy quantifier, `(hosts:.*)(resolve|dns)` matched
    greedily, and mdns_minimal landed AFTER resolve. The file read as correctly
    patched and the name did not resolve.
    """
    out = _run_nsswitch_edit(tmp_path, hosts_line)
    line = next(ln for ln in out.splitlines() if ln.lstrip().startswith("hosts:"))
    fields = line.split()
    assert "mdns_minimal" in fields, f"the edit did not add mdns_minimal: {line}"
    for resolver in ("resolve", "dns"):
        if resolver in fields:
            assert fields.index("mdns_minimal") < fields.index(resolver), (
                f"mdns_minimal is placed after {resolver}, which answers for "
                f".local first — avahi is never consulted: {line}")
    assert "[NOTFOUND=return]" in line, (
        f"the mdns_minimal entry has no [NOTFOUND=return] guard, so every "
        f"failed lookup on the box waits on mDNS: {line}")


@pytest.mark.parametrize("hosts_line", HOSTS_LINES)
def test_the_nsswitch_edit_survives_being_run_twice(tmp_path, hosts_line):
    """arch.sh is idempotent by contract, and re-running it is the documented
    way to repair a box.

    A second pass that appends a second mdns_minimal leaves a hosts: line glibc
    still parses and nobody can read — and the third pass makes it worse. The
    first version of this test asserted the guard by grepping arch.sh for
    `grep -qE …hosts:…mdns`, and passed with the guard deleted: it was matching
    the *other* grep, the one that validates the rewritten file. Hence running
    the real thing instead.
    """
    once = _run_nsswitch_edit(tmp_path, hosts_line, runs=1)
    twice = _run_nsswitch_edit(tmp_path, hosts_line, runs=2)
    assert once == twice, (
        f"a second run changed the file again:\n  once:  {once!r}\n"
        f"  twice: {twice!r}")
    line = next(ln for ln in twice.splitlines() if ln.lstrip().startswith("hosts:"))
    assert line.split().count("mdns_minimal") == 1, (
        f"the entry was added twice: {line}")


def test_the_iso_enables_avahi_the_same_way_it_enables_networkmanager():
    """An installed box is a copy of the live root, symlinks included.

    /etc/systemd/system/multi-user.target.wants is how this profile enables a
    unit — gamecore-disk-install.sh strips the live-only files and this
    directory is not among them, so what is enabled here is enabled on the
    installed machine. A package shipped with no symlink is avahi installed and
    `disabled`, which is exactly the state the production box was found in.
    """
    wants = ISO / "airootfs/etc/systemd/system/multi-user.target.wants"
    unit = wants / "avahi-daemon.service"
    assert unit.is_symlink(), (
        f"{unit.relative_to(REPO)} is missing or is not a symlink — the ISO "
        f"ships avahi and leaves it disabled.")
    # Same target shape as the NetworkManager link beside it: a relative link
    # would resolve against the build host, not the image.
    assert str(unit.readlink()).startswith("/usr/lib/systemd/system/"), (
        f"{unit.name} points at {unit.readlink()} — it must point into "
        f"/usr/lib/systemd/system, like the NetworkManager link beside it.")


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


# ── the microcode, and the two places that have to agree ───────────────────
#
# The failure this section stands for: the ISO booted on nothing — no machine,
# neither firmware — and the build that produced it was green. Every boot entry
# asked for `intel-ucode.img` and `amd-ucode.img` beside the kernel, and neither
# file was in the image.
#
# It is not that archiso stopped shipping them. mkarchiso inspects the built
# initramfs (`_check_if_initramfs_has_ucode`) and stages the external images ONLY
# when the initramfs does not already contain microcode. mkinitcpio's `microcode`
# hook puts it inside; the moment that hook is in the hook list, the separate
# files correctly stop existing, and any boot configuration still naming them
# names nothing. The two halves are one decision, and they live in different
# files — which is exactly the shape of thing that drifts.
#
# So this asserts the equivalence rather than either half: microcode in the hooks
# if and only if no boot configuration names a ucode image. Whichever half moves,
# the other has to move with it or the suite says so — in milliseconds, where
# install/iso/build.sh's post-build check needs a forty-minute build to say the
# same thing about the image it actually produced.

# mkarchiso's own list (`readonly ucodes=(…)`) — the definition of "a microcode
# image staged beside the kernel", rather than a guess at what one is called.
UCODE_IMAGES = ("intel-uc.img", "intel-ucode.img", "amd-uc.img", "amd-ucode.img",
                "early_ucode.cpio", "microcode.cpio")

ARCHISO_CONF = ISO / "airootfs/etc/mkinitcpio.conf.d/archiso.conf"
ISO_PRESET = ISO / "airootfs/etc/mkinitcpio.d/linux.preset"


def boot_configs() -> dict[str, str]:
    """Every boot configuration the profile ships, comment-stripped.

    Comment-stripped and not raw, and that is load-bearing here: these files
    explain at length why they no longer name a ucode image, so a test reading
    them raw would fail on the very prose that documents the fix.
    """
    files = sorted((ISO / "efiboot/loader/entries").glob("*.conf"))
    files += sorted((ISO / "syslinux").glob("*.cfg"))
    return {str(f.relative_to(REPO)): _uncommented(f) for f in files}


def iso_initramfs_hooks() -> list[str]:
    m = re.search(r"^\s*HOOKS=\(([^)]*)\)", _uncommented(ARCHISO_CONF), re.M)
    assert m, f"{ARCHISO_CONF.relative_to(REPO)} no longer sets HOOKS"
    return m.group(1).split()


def ucode_references() -> list[str]:
    return [f"{name}: {image}"
            for name, text in boot_configs().items()
            for image in UCODE_IMAGES if image in text]


def test_the_microcode_is_either_in_the_initramfs_or_named_by_the_boot_configs():
    """Never both, never neither — and the two live in different files.

    With the `microcode` hook, mkarchiso stages no separate ucode image and a
    boot entry naming one names a file that is not there: systemd-boot fails the
    whole entry ("Error preparing initrd: Not found"), syslinux abandons the boot
    and silently redraws its menu, so the countdown restarts for ever.

    Without the hook, the images are staged and a configuration that does not
    name them boots every machine with no microcode update at all — quiet, and
    only ever visible as a CPU erratum months later.
    """
    hooked = "microcode" in iso_initramfs_hooks()
    named = ucode_references()

    if hooked:
        assert named == [], (
            "the initramfs carries the microcode (the `microcode` hook is in "
            "HOOKS), so mkarchiso stages no separate ucode image — but these "
            "boot configurations still ask for one:\n  "
            + "\n  ".join(named)
            + "\n\nRemove the ucode lines. Do not put the files back: "
              "recreating the old layout is what this profile was fixed out of.")
    else:
        assert named, (
            f"{ARCHISO_CONF.relative_to(REPO)} has no `microcode` hook and no "
            "boot configuration names a ucode image either, so nothing puts "
            "microcode anywhere. Add the hook — that is the arrangement archiso "
            "moved to, and the one the rest of this profile is written for.")


def test_the_iso_puts_the_microcode_inside_the_initramfs():
    """Pins which half of the choice above is the shipped one.

    The equivalence alone is satisfied by going back to the old layout, and the
    old layout is what stopped working: it depends on mkarchiso staging files it
    stages only conditionally, and the condition is not the profile's to control.
    """
    assert "microcode" in iso_initramfs_hooks(), (
        f"{ARCHISO_CONF.relative_to(REPO)} lost the `microcode` hook. The ISO "
        "would boot every machine with no microcode update, and the ucode images "
        "are not a supported way back — mkarchiso stages them only when the "
        "initramfs lacks microcode, which is not a thing to depend on.")


def test_the_live_medium_carries_every_vendors_microcode_not_the_build_hosts():
    """`autodetect` before `microcode` narrows the image to the builder's CPU.

    The hook reads /proc/cpuinfo when autodetect ran first and contributes that
    vendor alone; with no autodetect it adds every microcode it finds. Measured
    on an AMD build host, the autodetect ordering produced an image carrying
    AuthenticAMD.bin and no GenuineIntel.bin. A live medium boots machines nobody
    has seen, and the ISO is built on a runner whose CPU vendor is not a decision
    anyone made — so this profile ships no autodetect, and if one is ever added,
    microcode has to come first.
    """
    hooks = iso_initramfs_hooks()
    if "autodetect" in hooks:
        assert hooks.index("microcode") < hooks.index("autodetect"), (
            f"HOOKS is {hooks}\n\n`autodetect` runs before `microcode`, so the "
            "ISO would carry only the build host's CPU vendor. Move `microcode` "
            "ahead of it, or drop `autodetect` — a live image wants every vendor.")


def test_the_iso_preset_points_at_the_drop_in_that_holds_those_hooks():
    """Without this, everything above is a file nobody opens.

    `mkinitcpio -P` re-invokes itself with `-c <the preset's *_config>`, and the
    `-c` handler sets `_optconfd=0` — the flag that decides whether
    /etc/mkinitcpio.conf.d/*.conf is sourced at all. A preset naming
    /etc/mkinitcpio.conf therefore means "this file and nothing else", and
    archiso.conf — the microcode hook, and `archiso`/`archiso_loop_mnt`, without
    which the ISO boots to an emergency shell — is read by nothing. That is the
    state this profile was found in, hidden behind the boot failure above.
    """
    text = _uncommented(ISO_PRESET)
    assert re.search(r"^\s*\w+_config=.*mkinitcpio\.conf\.d/archiso\.conf", text, re.M), (
        f"{ISO_PRESET.relative_to(REPO)} does not point at "
        "/etc/mkinitcpio.conf.d/archiso.conf.\n"
        "A preset that names /etc/mkinitcpio.conf switches the drop-in directory "
        "off, and the image is then built with the stock Arch hook list — no "
        "archiso hooks, no ISO.")
    assert not re.search(r"^\s*ALL_config=", text, re.M), (
        f"{ISO_PRESET.relative_to(REPO)} sets ALL_config, which applies `-c` to "
        "every preset and disables the drop-in for all of them.")


def test_the_ucode_packages_stay_although_no_boot_configuration_names_them():
    """They are not boot files any more; they are the hook's raw material.

    /usr/lib/firmware/{intel,amd}-ucode/ is what the `microcode` hook reads. With
    nothing naming these two packages in any boot configuration, they read as
    dead weight to the next person shrinking the image — and removing them leaves
    the hook finding nothing, silently. The installed system is a copy of this
    live root and rebuilds its own initramfs, so it needs them too, with no
    mirror to fetch them from.
    """
    pkgs = iso_package_list()
    for pkg in ("intel-ucode", "amd-ucode"):
        assert pkg in pkgs, (
            f"install/iso/packages.x86_64 no longer ships {pkg}. The `microcode` "
            "hook builds the early cpio from that package's firmware directory — "
            "without it the ISO and every box installed from it boot with no "
            "microcode update, and nothing reports it.")


def target_boot_entries() -> dict[str, str]:
    """The systemd-boot entries gamecore-disk-install.sh writes on the target.

    Read out of the heredocs in the shipped script rather than described here:
    the point is what the installed machine gets, and a second copy of it in the
    test would keep passing after the real one changed.
    """
    text = DISK_INSTALL.read_text(encoding="utf-8")
    entries = {}
    for m in re.finditer(
            r"tee (/mnt/boot/loader/entries/\S+) >/dev/null <<ENTRY\n(.*?)\nENTRY\n",
            text, re.S):
        entries[m.group(1)] = "\n".join(
            ln for ln in m.group(2).splitlines() if not ln.lstrip().startswith("#"))
    assert entries, "no loader entry heredocs found — this harness needs updating"
    return entries


@pytest.mark.parametrize("entry", sorted(target_boot_entries()))
def test_the_installed_system_gets_the_same_arrangement_as_the_iso(entry):
    """Fixing the ISO alone would have moved the failure one step further on.

    The disk installer wrote the target's entry with the same three initrds. Those
    files usually do exist on the ESP — the ucode packages put them in /boot — so
    this was an assumption rather than a proven break. But it is an assumption
    about what mkarchiso leaves in the airootfs's /boot, and the symptom when it
    is wrong is an install that completes and a machine that never boots: strictly
    worse than an ISO that refuses at the menu, and discovered after the operator
    has already erased their disk.
    """
    text = target_boot_entries()[entry]
    named = [img for img in UCODE_IMAGES if img in text]
    assert named == [], (
        f"{entry} names {named} — the target's microcode goes inside its "
        "initramfs, the same way the ISO's does. Nothing on the ESP is "
        "guaranteed to carry those files.")
    assert text.count("\ninitrd") + text.startswith("initrd") == 1, (
        f"{entry} has more than one initrd line:\n{text}")


def test_the_disk_installer_guarantees_the_microcode_hook_on_the_target():
    """The other half of the same change, and the reason the entry above is safe.

    The archiso drop-in is deleted on the target a few lines earlier and the
    preset written for it deliberately names no config file, so the hook has to
    land in /etc/mkinitcpio.conf itself. Without it the single initrd this test
    asserts would contain no microcode at all — which is a quieter failure than
    the one being fixed, and a worse one to ship.
    """
    body = _uncommented(DISK_INSTALL)
    assert "add_microcode_hook /mnt/etc/mkinitcpio.conf" in body, (
        "gamecore-disk-install.sh no longer ensures the microcode hook on the "
        "target. Its boot entry names one initrd, so nothing else would put "
        "microcode on the installed machine.")
    # Ordering, which is the whole of the hook's behaviour: on the TARGET
    # autodetect is present and must stay ahead of microcode — an installed box
    # only ever boots on its own CPU and has no use for the other vendor. That is
    # the opposite of the ISO, and both are deliberate.
    assert re.search(r"for h in autodetect udev base", body), (
        "the hook is no longer anchored on autodetect. On the target that "
        "ordering is what keeps the image to this machine's own microcode.")
