# Video — 3 minutes

In this niche, video ranks better than any page, and it is what creates searches
for the name. Someone searching "ps3 emulator living room" today gets no result
that shows them the finished thing in motion.

**The rule governing the whole script: don't tell, show.** Every second of
voice-over describing what the picture already shows is a second wasted. The edit
holds 3 minutes without a single text slide.

---

## ⚠️ To settle before shooting

> **The entry condition.** The closing shot (2:40) sends the viewer to the
> graphical installer, which means the video only speaks to people who already
> run Arch or Manjaro. There is no image to offer instead — the ISO was removed
> from the project — so that condition is real and the script should own it
> rather than gloss over it.

> **Nothing copyrighted on screen.** This is the easiest constraint to forget in
> the edit and the most expensive: an emulation video showing commercial box art,
> game titles and gameplay gets demonetised or taken down, and the link dies with
> it. Concretely:
> - **never any filmed gameplay** — cut the second the game renders a frame;
> - **no box art** in the library: populate the demo with homebrew and freely
>   distributable demos, whose art is their own;
> - **no ROM filename** visible anywhere, including in a terminal or a
>   notification going past;
> - **no BIOS, no keys** on screen, even blurred.
>
> What the video has to prove is that **the box launches**, not what it launches.
> The launch stops at the emulator's logo: that is enough, and it is safe.

---

## Shooting

**One single take for the screen, no hidden cuts.** The project's argument is "it
works on its own"; an edit that jumps from shot to shot at the precise moment
something configures itself destroys exactly what it is trying to prove. Film the
whole sequence continuously and cut for length, not for logic.

- **Screen**: HDMI capture from the box, 1080p60. No software capture on the box
  itself — it costs frames and it shows on the animations.
- **Hands**: a second camera on the controller, at table height, for the plugging
  and wizard shots. That is the shot that makes the point physical.
- **Sound**: the box's own sound (interface sounds are a theme, they exist), plus
  a voice-over recorded separately. No music under the voice — it saturates the
  3 minutes and tires the listener.

---

## The script

Timecodes are targets; the slack is in shots 2 and 6.

### 0:00 — 0:12 · The boot, without a word

**Picture** — Wide shot: a TV, a box, a controller set down. The box is off. A
finger presses the power button.
Cut to the HDMI capture: boot logo, splash, **home screen**.
A running timer stays visible bottom-left throughout the sequence.

**Voice-over** — *nothing.* Not a word for twelve seconds.

> This shot is the project's entire argument and it needs no commentary. The
> timer is there because "it boots fast" is a claim, and a timer is proof. **Do
> not fake it and do not speed the picture up**: if boot takes forty seconds,
> show forty seconds, or cut the shot with an honest fade and state the real
> duration out loud.

### 0:12 — 0:35 · What it is

**Picture** — Pad navigation on the home screen, then the library. Scroll down
the list of systems: PS3, PS4, Switch, Wii U, Xbox 360 go past at the top. Hold a
second on the full list.

**Voice-over** —
> "This is a machine running Arch Linux, in a living room, driven entirely with a
> controller. Thirteen systems — and unlike most boxes of this kind, it is the
> recent consoles that are at the top of the list: PS3, PS4, Switch, Wii U, Xbox
> 360."

### 0:35 — 1:05 · The controller, with nothing to configure

**Picture** — Hands shot: a **second** controller, a different brand from the
first, out of its box. Plug it in.
Cut to screen: the controller indicator goes to two. Player 2 appears. The second
pad navigates the menu immediately.

**Voice-over** —
> "A controller you plug in is usable straight away. No configuration screen, no
> file to edit — and that is true inside the emulators too, not just in the menu.
> The first pad plugged in is player one, the next is player two. Like a console."

> Using two different brands is the point of the shot. Two identical pads prove
> nothing: that is the easy case.
>
> **There is only one controller on the development machine** (a DualShock 4).
> This shot therefore needs hardware that is not present as this script is
> written. If it cannot be shot with two real pads, **cut it entirely** and keep
> the demonstration to one controller: the characterisation harness proves
> multi-pad support in the tests, but a video can only show what was plugged in.

### 1:05 — 1:45 · Launching. Switch, then PS3.

**Picture** — Library → Switch system → a game (homebrew) → **A**. The emulator
opens, the window appears, the logo shows. **Cut.**
Back to home via the Guide button, without putting the pad down.
Then: PS3 system → a game → **A**. RPCS3 opens. **Cut.**

**Voice-over** —
> "You launch from the couch, and you come back to the menu with the Guide button
> without ever touching a keyboard. The emulators themselves are Flatpaks: they
> update from Flathub, at their own pace. RPCS3 changes every week — on a frozen
> image, you wait for the distribution's next version. Not here."

> The return via the Guide button matters: it is the "and how do I get out?"
> question that every box of this kind has to answer.

### 1:45 — 2:30 · The mapping wizard

**Picture** — Hands shot on a generic, unbranded controller, the kind nothing
recognises. Plug it in: it does not navigate properly.
Cut to screen: Settings → Controllers → **Map this controller**.
The wizard starts. One button at a time, full screen. You see:
- a **press** that records and advances,
- a **hold** that skips a button the pad does not have,
- a **double press** that goes back.

End of the wizard, review screen, save. The pad navigates.

**Voice-over** —
> "And for a controller nobody recognises, there is this wizard. One button at a
> time, and it is driven entirely by the controller you are configuring — because
> at that moment, it is the only device you can be sure of. A press records. A
> long press skips a button the pad does not have. Two presses go back. A minute,
> without a keyboard."

> This is the most convincing shot in the video for an emulation audience:
> everyone in that community has spent an evening on a mapping file. Do not speed
> it up, and **let the hold last** — that is precisely the gesture you need to
> have seen once to reproduce it.

### 2:30 — 2:40 · The real machine

**Picture** — Settings → Exit to desktop. The kiosk closes, **a full Plasma
desktop** appears. A browser opens. Then, in one terminal command, back to the
kiosk.

**Voice-over** —
> "And underneath, it is a full Arch. Not a read-only image: a real PC, with a
> desktop, that you install whatever you like on."

> This shot answers the only serious objection a technical audience makes to
> living-room boxes: "I lose my machine". Ten seconds is enough.

### 2:40 — 3:00 · Where to get it

**Picture** — Back to the GameCore home screen. The site URL is overlaid,
readable, still, until the end.

**Voice-over** —
> "It's free software, GPL. If the machine already runs Arch or Manjaro, there is
> a graphical installer to download — the link is in the description."

---

## The publication text (YouTube)

### Title

The title carries the query, not the name: nobody searches for "GameCore".

```
A living-room emulation box for PS3, PS4, Switch and Wii U — on Arch Linux
```

Variant if the channel is French-speaking:

```
Une box salon pour émuler PS3, PS4, Switch et Wii U — sous Arch Linux
```

### Description

The first two lines are the only ones visible before "more": they carry the
angle, and the link is high up.

```
GameCore is a gamepad-only frontend for a living-room Arch Linux box, built
around the recent consoles — PS3, PS4, Switch, Wii U, Xbox 360 — with emulators
that stay current because they come from Flathub.

→ https://p4v1c.github.io/GamecoreRenew/
→ Source (GPL-3.0): https://github.com/p4v1c/GamecoreRenew

00:00  Boot, from cold to the home screen
00:12  Thirteen systems, recent consoles first
00:35  Plug a pad in — it just works, in the emulators too
01:05  Launching a Switch game, then a PS3 one
01:45  The mapping wizard: any controller, about a minute, no keyboard
02:30  Exit to the desktop — it is still a real Arch machine
02:40  Where to get it

Controllers are configured automatically in each emulator: GameCore writes the
emulator's own config for the pads actually connected, per player slot. The
first pad plugged in is Player 1, whatever brand it is.

No games, ROMs or BIOS files are shown or provided in this video. Everything on
screen is homebrew or a freely distributable demo.
```

> That last line is not decorative caution: it is what a moderator reads first on
> a report, and it is what makes the difference between a video reviewed and a
> video removed.

### Tags

```
emulation, linux gaming, arch linux, ps3 emulator, rpcs3, switch emulator,
wii u emulator, cemu, retrogaming, htpc, couch gaming, emulation frontend,
batocera alternative, flatpak, gamepad
```

`batocera alternative` belongs here — in the tags, where it catches an existing
search — and **nowhere in the title, description or voice-over**. The comparison
on breadth is lost in advance; the query itself is worth taking.
