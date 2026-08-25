# AlternativeTo — entry to submit

**Where**: https://alternativeto.net/manage/new-app/ (account required, created
by the human).

AlternativeTo is a directory: the entry is only worth anything **through the
"alternative to" links it declares**, because traffic arrives from competitors'
pages, never from a search on the name. It is the one channel in this phase where
comparison is the mechanism rather than a weakness — but it stays in the linking
fields, never in the description.

---

## Name

```
GameCore
```

> There are already several "GameCore"s (a Java engine, a 3D IDE, a Mac engine on
> SourceForge). If the form refuses the name as a duplicate, use
> `GameCore (emulation frontend)` — and **not** `GamecoreRenew`, which is the
> name of nothing to a reader.

## URL

```
https://p4v1c.github.io/GamecoreRenew/
```

## Tagline (one line)

```
Living-room emulation frontend for Arch Linux, built around the recent consoles.
```

## Description

```
GameCore turns a PC into a console you drive from the couch with a gamepad. It
boots straight into a full-screen launcher: no desktop, no keyboard, no mouse.

Where most living-room emulation systems are built around decades of 8- and
16-bit machines, GameCore is built around the recent consoles first — PS3, PS4,
Switch, Wii U and Xbox 360 — with the classics alongside them, thirteen systems
in all. The emulators are Flatpaks from Flathub, so they update on their own
schedule rather than being frozen until the next release of the distribution.
That matters most exactly where it is hardest: RPCS3 and Ryujinx change every
few weeks.

Controllers configure themselves. GameCore writes each emulator's own
configuration for the pads actually connected, per player slot — the first pad
plugged in is Player 1 whatever brand it is, like a real console. For a
controller nothing recognises, a built-in wizard maps it in about a minute,
driven entirely by the pad being mapped, with no keyboard.

Underneath, it stays an ordinary Arch Linux machine with a KDE Plasma desktop.
One command closes the kiosk and gives you a normal PC back. Nothing is
read-only, nothing is locked down.

It installs onto an existing Arch or Manjaro system with a graphical installer,
updates itself over the air, and is free software under the GPL-3.0.
```

## Licensing model

```
Free / Open Source
```

## License

```
GPL-3.0-or-later
```

## Platforms

```
Linux
Self-Hosted
```

> Tick **Linux** only on the OS side. Do not tick Windows or macOS: the stack is
> X11-only and the installer is Arch-specific. An entry promising a platform it
> does not serve collects downvotes and "it doesn't install" comments, which stay
> visible for years.

## Alternative to

In this order — it is decreasing order of relevance, and it determines where the
traffic comes from:

```
Batocera.linux
RetroBat
EmulationStation
Playnite
```

For each, the comparison note if the form asks for one:

- **Batocera.linux** — same use (a living-room box driven by a gamepad), opposite
  approach: Batocera is a frozen, read-only system image covering a very large
  number of older machines; GameCore is a full, modifiable Arch oriented at recent
  consoles, whose emulators update independently.
- **RetroBat** — same idea on Windows; GameCore is Linux only.
- **EmulationStation** — EmulationStation is the interface alone, to be
  integrated. GameCore is the whole system: installation, services, kiosk,
  updates, controller configuration.
- **Playnite** — Playnite unifies PC game libraries on Windows. Real overlap on
  the couch launcher, none on Linux emulation.

> **Do not add RetroPie or Lakka.** Those are ARM / low-end targets, and an entry
> declaring itself an alternative to a project it does not replace gets corrected
> by community votes — which damages the entire entry, including the accurate
> links.

## Tags

```
emulator
emulation
game-launcher
retrogaming
htpc
kiosk
arch-linux
flatpak
gamepad
living-room
```

## Screenshots to attach

Four, in this order. They are frames from the video, so they cost nothing extra
once it is shot — **and they inherit the same constraint: no commercial box art,
no readable ROM name** (see [`../video-script.md`](../video-script.md)).

1. the home screen;
2. the library, list of systems visible, PS3/PS4/Switch at the top;
3. the mapping wizard mid-run, one button shown full screen;
4. the settings screen.
