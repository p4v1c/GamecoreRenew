# r/linux_gaming — post to publish

**A much wider audience than r/EmulationOnLinux, and much more suspicious of
self-promotion.** The sub has over a million subscribers; a post that smells of a
press release gets buried in downvotes within the hour.

What works here is a personal project told by the person who made it, with its
limits stated. The post below is therefore shorter than the r/EmulationOnLinux
one, less technical, and it **says what doesn't work** — that is not modesty, it
is the difference between a thread that lives and a thread that dies.

**Before posting:**

- read the sub's rules, particularly on self-promotion — some require a
  participation ratio or a minimum account age;
- set the flair. Here it is probably **`Software`** or **`Emulation`**;
- post on a weekday, European morning. On a Sunday evening the thread is buried
  before anyone sees it;
- **do not post the same day as r/EmulationOnLinux.** The two audiences overlap,
  and a simultaneous crosspost reads as spam;
- **reread the first-person claims.** This text is written to be signed by the
  owner, but it was drafted by someone else: "it's what runs under my TV", "it
  took me a while", "I have exactly one controller" are biographical claims. They
  match what the repo lets you see, but **only the owner knows whether they are
  true** — and on a sub that punishes overselling, a single false one costs more
  than everything the post earns. Correct without hesitation; tone matters less
  than accuracy.

---

## Title

```
I spent a while turning an old PC into a console for the living room — PS3, PS4, Switch and Wii U, driven entirely with a gamepad
```

> The title tells a project, not a product. "I spent a while" is what separates a
> welcomed post from a reported one — and it is true, so it is not a pose.

## Body

```markdown
I wanted the machine under my TV to behave like a console: turn it on, it's
there, drive everything with the pad, never see a desktop or a keyboard. What
existed either targeted mostly older systems, or handed me a frozen system image
where I couldn't just update an emulator when it needed it. So I built my own,
and it's what runs under my TV.

It's called GameCore. It's a full-screen launcher on top of a normal Arch
install — thirteen systems, weighted towards the recent consoles (PS3, PS4,
Switch, Wii U, Xbox 360) rather than the usual long tail of 8-bit machines.

**The parts I'm actually happy with:**

- **The emulators are Flatpaks from Flathub.** They update independently of my
  frontend, which matters enormously for the recent stuff — RPCS3 and Ryujinx
  change every few weeks, and I didn't want a release of mine to be what gates a
  compatibility fix reaching my TV.
- **Controllers configure themselves, inside the emulators.** Plug a pad in and
  it works in RPCS3, Dolphin, Cemu, Ryujinx and the rest, per player slot, with
  no config screen. The first pad plugged in is Player 1 whatever brand it is.
  This was by far the hardest part — every emulator identifies devices
  differently, and two of them fail *silently* when you get it wrong, which is
  a wonderful way to lose an evening.
- **It's still a real computer.** Plain Arch with KDE Plasma underneath, nothing
  read-only. One command closes the kiosk and I have my desktop back. I didn't
  want to give up a machine to gain a console.
- **There's a mapping wizard** for pads nothing recognises — one button at a
  time, about a minute, driven entirely by the pad you're mapping, no keyboard.

**The parts that are honestly limitations:**

- **It only installs on Arch or Manjaro.** There's a graphical installer, but if
  you run something else, this isn't for you today.
- **X11 only.** The overlay system, the fullscreen enforcer and the
  gamepad-to-keyboard bridge all depend on it. Wayland is not a small change.
- **I have exactly one controller.** Two-, three- and four-pad setups are
  covered by a test harness that replays synthetic controller sets against the
  real config generators and compares against recorded output — so I'm
  reasonably confident in the generated configs, but I have not sat four people
  down in front of it. If you try it with a pile of pads I'd genuinely like to
  know what happens.
- **First install needs a network**, because the emulators come from Flathub.
- It's one person's project. The bus factor is one.

GPL-3.0, source is here: https://github.com/p4v1c/GamecoreRenew

Happy to answer questions, and happy to be told what I got wrong.
```

---

## Notes for answering comments

- **"Why not Bazzite / ChimeraOS / Batocera?"** — It will come first and probably
  several times. Answer with what you wanted, not with what they lack: recent
  consoles first, emulators updating independently, a machine that stays normally
  usable. **Do not disparage any of the three** — many readers use them, and
  criticising them turns the thread into a defence.
- **"Why Arch and not Debian/Fedora?"** — Because recent emulators need recent
  system packages, and because that is what runs on the box. That is a sufficient
  answer; do not try to make it a universal technical argument.
- **"Wayland?"** — No, and say precisely why (overlays, forced fullscreen,
  pad→keyboard bridge). Do not promise a date. A roadmap promise in a Reddit
  comment gets quoted back six months later.
- **A bug report in the comments** — ask for a GitHub issue, but **answer the
  substance in the thread anyway**. "Open an issue" on its own reads as a dodge.

And the reflex not to have: **do not reply to downvotes or hostile comments.** On
this sub, an author who defends himself always does worse than the comment he is
fighting.
