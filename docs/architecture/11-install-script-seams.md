# Splitting the install scripts — the seams, and why they are not cut yet

`install/arch.sh` is 1 632 lines and `install/uninstall.sh` is 902. Both are far
outside the size the rest of this tree keeps to, and both were looked at as part
of the quality pass that split `gamescrape.py` and `gamemedia.py`.

They were **deliberately left whole**. This file records what the split would
be, so the next person does not re-derive it, and — more importantly — what has
to be true before anyone runs it.

## Why not yet

Three facts, and any one of them is enough:

- **No test covers either file.** The Python splits in the same pass were
  provable: `test_covers.py` and `test_gamemedia.py` counted 73 tests before and
  73 after, to the unit, which is what made "this changed nothing" a statement
  rather than a hope. There is no equivalent here. `shellcheck -S warning` is
  the only automated reader, and it checks for shell mistakes, not for whether
  the install still installs.
- **They run as root.** A sourcing order that is subtly wrong does not raise —
  it writes a unit file, a sudoers rule or an SDDM config to the wrong place,
  as root, on a machine that then reboots into it.
- **A half-refactored install script is worse than a long one.** `arch.sh` warns
  and carries on for a dozen recoverable failures and reports them in its
  closing summary, on purpose: a missing emulator is a degraded box, an aborted
  installer at 66 % is a machine that is neither installed nor clean. That
  property is spread across the whole file and is exactly the kind of thing a
  partial extraction breaks.

**The prerequisite is a disposable VM**, and a fresh one per attempt: the only
honest test of an installer is a machine that has never been installed. Doing it
on a working box proves nothing, because the box already has everything the
script would create. Cutting these files on the machine that *is* the
installation target is the one way to turn a refactor into an outage.

## The seams, if a VM is available

`arch.sh` already announces its own structure — every phase opens with
`msg "<name>"`, and those calls are the cut lines. The three worth taking first
are the three that are self-contained, come late, and can each be re-run on an
already-installed box without doing damage:

| Phase | Lines (approx.) | Why it is a good first cut |
|---|---|---|
| `SDDM auto-login` | 964–1051 | Touches one subsystem and one config tree. Nothing later in the file depends on what it computes. |
| `Caddy reverse-proxy (HTTPS :8443)` | 1052–1103 | Same shape: writes a Caddyfile and enables one unit. `uninstall.sh` already has its own matching Caddy section, so the pair moves together. |
| `Node frontend build` + `Electron shell` | 1176–end | The tail of the script. Long, mechanical, and the only phases that shell out to npm. |

Everything before `msg "System packages"` is preamble — colours, `warn`/`info`,
`progress`, `git_sync`, the manifest recorders, `want_emu`/`want_app` — and it
is what the extracted phases would need. So the split is:

```
install/lib/common.sh      the helpers and the manifest recorders above
install/phases/sddm.sh     one phase per file, sourced in order by arch.sh
install/phases/caddy.sh
install/phases/frontend.sh
install/arch.sh            argument parsing, the phase order, the summary
```

`arch.sh` keeps the phase ORDER and the closing summary, because the order is
the one thing that is genuinely a property of the whole install, and the summary
is what turns a degraded box into a diagnosable one.

## What to check before believing it worked

Not "the script exits 0". On a fresh VM, after a full run:

- the box reaches the grid unaided after a reboot — that is the only end-to-end
  assertion that matters, and it exercises SDDM, the units and Electron at once;
- `install/uninstall.sh` still removes what `arch.sh` created. The two files
  carry a shared, undocumented contract about what was written where, and it is
  the first thing a split of only one of them breaks;
- the closing summary still lists the recoverable failures. Extracting a phase
  into a sourced file makes it easy to lose the `warn`-and-continue behaviour by
  making the phase exit instead — and that failure looks exactly like success.

## Also noted, and also left alone

`install/steps/apply-multi-ds4.sh` names two emulators in plain text. It stays
that way. It is a hardware workaround for multiple DualShock 4 pads, those two
are the only ones whose `.ini` files share the SDL-0/Pad1 convention, and a
schema field two packs out of seventeen would use — to serve a patch — costs
more than it earns.

The criterion is not "is it hardcoded", it is **"does it disappear without
saying so"**. That script prints `SKIP — ini not found`. It fails in the open,
which is all that is asked of it.

---

## The ISO, and why it is a *third* installer rather than a wrapper

`install/iso/` builds a live ISO with `mkarchiso` — an archiso profile
(`profiledef.sh`, `packages.x86_64`, `pacman.conf`, `airootfs/`, `syslinux/`,
`efiboot/`) plus `build.sh` (229 l.) which stages the payload and runs the build.

Three properties are not obvious and each one is a seam in its own right.

**The profile is copied before building.** `mkarchiso` wants the payload inside
the profile's `airootfs/`, and the payload is ~2 GB of `node_modules`, Python
wheels and a copy of the GameCore tree. Staging that in place would put two
gigabytes of build output inside the git working tree, where the next
`git status` is unusable and the next `git clean -fdx` is a nasty surprise. So
the profile is copied to a scratch directory and the repository is never written
to.

**`gamecore-disk-install.sh` deliberately does not run `arch.sh`.** This is the
seam that matters most, because the obvious design is wrong. `arch.sh` assumes a
running systemd — `systemctl enable --now sshd`, `cpupower.service` and half a
dozen more, none of them guarded — and inside `arch-chroot` there is no systemd
to talk to. The first call fails, `set -e` fires, and the install dies two thirds
of the way through **with a partitioned disk and no bootloader**.

So the disk install stops at "a bootable Arch carrying the GameCore payload", and
the rest is finished on first boot, where systemd exists. That is why there are
three installers and not one:

| | runs where | finishes what |
|---|---|---|
| `gamecore-installer` (PyInstaller) | an existing Arch/Manjaro | everything |
| `gamecore-disk-install.sh` | the live ISO, `arch-chroot` | partitioning and payload only |
| first-boot unit | the installed box | the systemd half |

**Where it can be built, and where it cannot.** `mkarchiso` needs root, loop
mounts and ~25 GB of scratch, so the ISO cannot be built or verified on the box
that plays the games, and it is not built on a development laptop by accident —
`build.sh` guards against both. In practice the only place it is exercised is the
`iso` job in `release.yml`, which means **CI is the test environment**: a change
here is proven by pushing, and there is no cheaper way. See
[13](13-release-and-ota.md) for what that push costs, and
[9](09-gotchas.md#build-and-release) for the two stacked defects that kept this
job red from the day it was added — both of which exited 0.

`build.sh` now refuses a Node outside 18–22 **before** the forty minutes of
`pacstrap`, rather than letting the symptom surface at the Electron guard where
it is indistinguishable from the npm policy problem. The upper bound is the last
version measured working, not the first known broken.
