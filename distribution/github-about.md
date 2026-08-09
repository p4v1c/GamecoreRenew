# The repo's About block — to apply by hand

GitHub serves no description today. So Google only has the default string:

```
Contribute to p4v1c/GamecoreRenew development by creating an account on GitHub.
```

That is the only text the repo emits to the outside world. Replacing it is the
cheapest and highest-return change in this whole phase.

## Where

`https://github.com/p4v1c/GamecoreRenew` → the **⚙ (Settings)** button to the
right of **About**, at the top of the repo home page's right-hand column. Not the
repo Settings: it is the little cog on the About block itself.

---

## 1. Description (one line)

The field allows 350 characters, but Google cuts the displayed text around
155–160. **Everything that matters must fit in the first 155.**

```
Living-room emulation frontend for Arch Linux — PS3, PS4, Switch, Wii U, Xbox 360 and 8 more. Always-current Flatpak emulators, auto-configured pads.
```

149 characters — so Google shows it whole, untruncated. The ordering is
deliberate:

- **`Living-room emulation frontend for Arch Linux`** first — that is the query,
  not the name. Nobody searches for "GameCore"; people do search those words.
- **The named consoles** next, because `ps3`, `switch`, `wii u` are what actually
  gets typed, and because that is the angle: recent consoles first.
- **`Always-current Flatpak emulators, auto-configured pads`** last: the two
  differentiators. `pads` rather than `controllers`, and the sentence split in
  two rather than one more comma, purely to stay under 155.

If "gamepad-only" absolutely has to be in there, this variant is 170 characters
and Google will cut it just before `auto-configured` — meaning it loses, in
display, the very differentiator it adds:

```
Living-room emulation frontend for Arch Linux — PS3, PS4, Switch, Wii U, Xbox 360 and 8 more, always-current Flatpak emulators, gamepad-only, auto-configured controllers.
```

The word is in the `gamepad` topic and in the site's `<title>` anyway.

---

## 2. Website

```
https://p4v1c.github.io/GamecoreRenew/
```

To be set **after** enabling Pages (see [`site.md`](site.md)) — a Website field
that 404s is worse than an empty one, because crawlers follow it.

---

## 3. Topics

The eight wanted, in this order (GitHub displays them in entry order):

```
emulation-frontend
retrogaming
flatpak
arch-linux
electron
fastapi
gamepad
kiosk
```

To paste one at a time into the Topics field. GitHub accepts up to 20.

### Five more, to add if wanted

They are here because GitHub's `/topics/<name>` pages are indexed and act as
landing pages — a topic is a discovery channel, not a label:

```
emulator
playstation-3
nintendo-switch
htpc
couch-gaming
```

`playstation-3` and `nintendo-switch` are the two that carry the "recent
consoles" angle. `htpc` and `couch-gaming` catch search-by-use rather than
search-by-technology, which is what people building a living-room box do before
they know what they will put in it.

---

## 4. The checkboxes, under the topics

- **Releases** — tick. That is where the installer is, and it is the first thing
  a visitor should see.
- **Packages** — untick, there are none.
- **Deployments** — untick.

---

## Checking it took

Once applied, the tag reads back without waiting for Google to come round:

```bash
curl -s https://github.com/p4v1c/GamecoreRenew | grep -o '<meta name="description"[^>]*>'
```

It must return the new description, plus the `Contribute to…` sentence.

For indexing itself, count a few days, and do not worry about it before two
weeks. The Pages site will be indexed faster than the repo page anyway, because
GitHub forbids crawlers on `/tree/` and `/blob/` but not on `github.io`.
