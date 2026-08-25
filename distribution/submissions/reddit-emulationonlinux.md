# r/EmulationOnLinux — post to publish

**The audience closest to the project, and the most demanding on detail.** This
is not where you sell a living-room experience: here you talk controller
configuration, Flatpak, and RPCS3. It is the only community in this phase that
will check the technical claims — so the only one where you have to be precise,
and where being precise is enough.

**Before posting**: read the subreddit rules in the sidebar. Many emulation subs
forbid any link to ROMs or BIOSes — the post below contains none and alludes to
none, and that must stay true.

**Flair**: `Project` or `Discussion`, whichever exists. Without a flair the post
is auto-removed on most of these subs.

---

## Title

```
I built a couch emulation frontend for Arch that auto-configures controllers inside each emulator (RPCS3, Ryujinx, Dolphin, Cemu…)
```

> The title carries the **technical detail**, not the ambition. "I made an
> emulation frontend" is indistinguishable from anything; "it configures pads
> inside RPCS3 and Ryujinx" is a problem this audience has had personally.

## Body

```markdown
I've been building a living-room emulation frontend for Arch for a while and it
has reached the point where it's genuinely usable, so here it is.

The short version: it boots straight into a full-screen, gamepad-only launcher
on a normal Arch install, and it's weighted towards the recent consoles — PS3,
PS4, Switch, Wii U, Xbox 360 — with the classics alongside. Thirteen systems.

Two things in it are worth this sub's time specifically.

**Emulators are Flatpaks from Flathub, not bundled builds.**

They update on their own, independently of the frontend. This is the part I care
most about: RPCS3 and Ryujinx change every few weeks, and on a frozen system
image you wait for the image. Here `flatpak update` is the whole story. The
trade-off is that first install needs a network, and Flatpak sandboxing needed
real work — each emulator gets `--filesystem` for the ROM directory and
`--device=all` for controllers, granted automatically at install.

**Controllers are configured inside each emulator, per player slot.**

Not just in the launcher's menus — the actual emulator config files. This turned
out to be much less uniform than I expected, and the details might save someone
else the reverse-engineering:

- PCSX2 and DuckStation speak SDL's role vocabulary (`SDL-0/FaceEast`), so
  exporting the community SDL_GameControllerDB through
  `SDL_GAMECONTROLLERCONFIG_FILE` covers any pad in the database with zero
  config. Worth noting that's *the* variable SDL actually reads —
  `SDL_GAMECONTROLLERDB` is not one, and I shipped that for a while before
  noticing the database was being silently ignored.
- Dolphin and RPCS3 also use semantic roles, but pick the *device* by literal
  name (`Device = SDL/0/PS4 Controller`). Both bundle SDL3, whose device names
  differ from the SDL2-era community database — a DualSense is "DualSense
  Wireless Controller", not "PS5 Controller". So the name gets resolved by
  asking the system's libSDL3 with the pads actually connected. And the number
  in that string is *not* the player slot: RPCS3 appends a 1-based counter per
  name, Dolphin a 0-based one, so a lone DualSense is "…Controller 1" even as
  Player 2.
- Ryujinx binds by device GUID and resolves it by string equality. No match is
  −1, and −1 disposes the slot silently — no log line, nothing in Input
  Settings. The GUID carries bus type and driver signature, so the same DS4 has
  different GUIDs over USB and Bluetooth; it can't be derived from vendor:product.
  Ryujinx renders SDL2's 16 raw GUID bytes through .NET's `System.Guid`, which
  reverses the first three fields, so the conversion has to be done exactly.

The first pad plugged in is Player 1 whatever brand it is, the next is Player 2,
like a real console. No slot is ever tied to a brand.

For a pad nothing recognises there's a mapping wizard: one button at a time,
full screen, about a minute. It's driven entirely by the pad being mapped —
press to record, hold to skip a button the pad doesn't have, double-press to go
back — because a controller the box can't understand is exactly the one you
can't use normal navigation with.

**Everything else stays a normal machine.** It's plain Arch with KDE Plasma
underneath, nothing read-only. `sudo gamecore-session-select desktop` closes the
kiosk and gives you a PC back.

**Getting it.** If the machine already runs Arch or Manjaro there's a graphical
installer on the releases page. Updates are over the air from the settings
screen.

GPL-3.0. Source: https://github.com/p4v1c/GamecoreRenew

Happy to answer anything about the controller side in particular — that's where
almost all the time went, and where I'd most like to be told I got something
wrong.
```

---

## Notes for answering comments

Three questions will land, and it is better to have the answer ready than to
improvise.

- **"Why not Batocera / EmuDeck?"** — Answer with the use case, never with the
  comparison: recent consoles first, emulators that update themselves, a machine
  that stays a machine. **Do not say Batocera is worse.** It is a respected
  project here, and attacking it costs the whole thread.
- **"Does it work on anything other than Arch?"** — No, and say so plainly. The
  installer is Arch/Manjaro-specific and the stack is X11 only. An evasive answer
  is paid for in installation tickets.
- **"What about ROMs / BIOSes?"** — The project distributes none, downloads none,
  and has no scraper that looks for any. Short answer, no debate.

And a fourth, which will certainly come because the post insists on multi-pad
support:

- **"How many controllers did you test it with?"** — The honest answer, and it
  must be given as-is: **one physical controller** on the development machine, a
  DualShock 4. Two, three and four pads are covered by a characterisation harness
  that replays synthetic rosters against the real generators and compares to
  recorded output — that is real proof for config generation, and it is **not**
  proof that four pads play together on real hardware.
>
> Saying that costs less than being caught: this sub has people with four
> controllers who will try. Being contradicted by a comment after claiming
> otherwise kills the thread; having said it up front turns the same comment into
> a test report.

The general principle: this sub punishes overselling. What has not been plugged
in gets said. Here that reads as seriousness, not weakness.
