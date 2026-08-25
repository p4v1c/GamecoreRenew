# Awesome-lists — the line, and the PR body

Awesome-lists are the slowest and most durable channel: an accepted line stays
for years and earns a backlink from a very well-ranked repo. They are also the
easiest to get refused from, for one constant reason: **a PR that does not match
the list's format is closed without discussion.**

So, in order, every time:

1. read the target list's `CONTRIBUTING.md`;
2. **copy the exact format of a neighbouring line** — dash, bold or not, full stop
   or not, alphabetical order or not;
3. one PR per list, never a grouped PR.

---

## The target lists, in order of relevance

| List | Likely section | Note |
|---|---|---|
| [`awesome-emulators`](https://github.com/tomconte/awesome-emulators) | Frontends | The most direct. |
| [`awesome-linux-gaming`](https://github.com/dgvai/awesome-linux-gaming) | Emulation | Overlaps r/linux_gaming's audience. |
| [`awesome-selfhosted`](https://github.com/awesome-selfhosted/awesome-selfhosted) | — | **Do not submit.** GameCore is not a self-hosted service; the PR will be refused and rightly so. |
| [`awesome-arch`](https://github.com/PandaFoss/Awesome-Arch) | Applications | Arch angle, smaller but very targeted. |

---

## The line

Most common format (`- [Name](url) - Description.`):

```markdown
- [GameCore](https://github.com/p4v1c/GamecoreRenew) - Gamepad-driven living-room emulation frontend for Arch Linux, built around the recent consoles (PS3, PS4, Switch, Wii U, Xbox 360) with Flatpak emulators that stay current and controllers that configure themselves.
```

If the list requires short descriptions (many cap around 100 characters):

```markdown
- [GameCore](https://github.com/p4v1c/GamecoreRenew) - Living-room emulation frontend for Arch Linux, recent consoles first.
```

> The link points at the **repo**, not the site: awesome-lists expect a project,
> and an entry pointing at a marketing page rather than a repo regularly gets
> asked to change. The site is linked from the repo's About anyway.

---

## PR body

Short. An awesome-list maintainer reads dozens of these and looks for three
things: is it alive, is it free, does it belong here.

```markdown
### What it is

GameCore is a gamepad-only emulation frontend for a living-room Arch Linux box.
It boots into a full-screen launcher — no desktop, no keyboard — and covers
thirteen systems, weighted towards the recent consoles: PS3, PS4, Switch, Wii U
and Xbox 360.

### Why it fits this list

- Free software, GPL-3.0-or-later.
- Actively developed, with tagged releases and CI on every merge.
- It is a frontend, not an emulator: it installs and drives existing ones
  (RPCS3, Ryujinx, Cemu, Dolphin, PCSX2, DuckStation and others) rather than
  reimplementing anything.

### What makes it different from the frontends already listed

- Emulators are Flatpaks from Flathub, so they update independently of the
  frontend. RPCS3 and Ryujinx move every few weeks; a frozen system image holds
  them back until its own next release.
- Controllers are configured automatically **inside each emulator**, per player
  slot, from the pads actually connected — not just in the launcher's own menus.
  A built-in wizard handles pads nothing recognises, driven entirely by the pad
  being mapped.
- It stays a normal Arch install with a KDE Plasma desktop underneath; one
  command closes the kiosk and hands the machine back.

Installs onto an existing Arch/Manjaro system with a graphical installer, and
updates over the air.

Docs: https://github.com/p4v1c/GamecoreRenew#readme
```

---

## What must not go in the PR

- **No named comparison with Batocera** or with an entry already in the list. A
  maintainer reads that as "my submission deserves more than yours", and it is
  the fastest way to get an otherwise correct PR closed. The differences above
  are phrased positively, naming nobody — that is deliberate, do not "fix" it.
- **No screenshots**: these are text lists, images weigh the review down without
  adding anything.
- **No mention of star count**, nor of "new project". Several lists require a
  minimum age or popularity; announcing it yourself gets the criterion applied
  immediately.
