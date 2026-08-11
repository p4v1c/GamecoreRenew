# Shelf

Your library as objects on a papered wall. A system's games stand as spines;
the selected one is turned towards you as a real solid and can be turned over;
a card beside it carries the cartridge and its printing details; ✕ slots it in
and the iris closes on the label.

Ported from a screen capture of a reference UI. The capture showed a shelf
browser for one console with a fixed dataset; this runs on the box's real
systems, playtime, metadata and controllers, on the host's single input bus.

## The box is assembled, not drawn

The backend already does the work. `WARM_MEDIA` in
`backend/services/gamemedia/__init__.py` pulls `box-front`, `box-spine` and
`box-back` down for the whole library once the covers have landed — its own
comment calls them *"the three faces the 3D box is built from"*. This theme is
the other half of that sentence: six CSS faces, a depth, and a rotation.

```
front  = box-front          W × H       width and height come from the
spine  = box-spine          D × H       front image's own ratio, measured
back   = box-back           W × H       on load — a SNES box is landscape,
top · bottom · opening edge             a PS1 box is portrait
       = cardboard, because no artwork is printed on those faces
```

Turning the box over is a rotation of that one object, continuing the way it
was already going, past the opening edge. That is the reason it is assembled
rather than composited: a flat image cannot be turned over.

**Unfocused games are their spine and nothing else** — one `<img>`, the face a
real shelf shows you. Twenty solids would be sixty images and sixty
compositing layers for nineteen boxes showing one face each.

## Three stackings, one shelf

R2 cycles them. All three are the same markup and the same solid; only the
axis and the card move.

| | |
|---|---|
| `shelf` | spines upright, the turned box among them, card at the right |
| `stack` | the boxes in a pile, index down the left edge |
| `gallery` | flat on, card as a strip along the bottom — the reading position |

## What the theme adds, and what it never touches

Scrolling, sorting, searching, launching and ○ arrive as props and are used
exactly as given, so a shelf and the default list behave identically.

Two additions, both pure view state — they move no selection and survive no
reload:

| Button | | Why that button |
|---|---|---|
| **L2** | turn the box over | the only face-adjacent buttons the library leaves free |
| **R2** | restack the shelf | ↑↓ scroll, ✕ launches, ○ home, △ search, □ controller, L1/R1 sort |
| **←→** | scroll | wired to the host's own `onSelect`, same clamped step as ↑↓ — on a shelf that runs left to right, pressing right and having nothing happen reads as a broken screen |

## Two accents, two jobs

- **The live one** is read out of the jacket on screen — a 24px offscreen
  canvas, bucketed by hue, scored by saturation, clamped to something a UI can
  actually wear. The wall, the stamps and the focus ring take it and cross-fade
  when the selection settles. It is the signature of the reference capture and
  the reason the wallpaper is a *mask* over a solid colour rather than a
  picture: `background-color` transitions, an image does not.
- **The fixed one** is seal gold, in `:root`. The host's settings widgets are
  drawn with inline styles and can only read `:root`, so chrome does not follow
  the artwork. The shelf does.

## The settings rail, and why it is not the two-column screen

The v2 capture draws Settings as a rail of numbered categories on the left and
the selected category's contents on the right, both on screen at once. This is
a rail that hands over to a full-screen page instead, and the reason is
structural rather than a shortfall of effort.

Every page in `sdk.defaults.DefaultSettingsPages` renders its own `<Overlay>`,
which is `position: fixed; inset: 0`. The handles a theme is given on it are
`--gc-overlay-{scrim,blur,panel,border,radius}` — colour, blur, corners. None
of them insets the layer, so a page drawn "on the right" covers the rail
whatever the theme does; and boxing it into a column nests `position: fixed`
inside a flex panel, which is the exact thing that shattered the Wi-Fi page and
painted it black.

What carried the capture's meaning survives: the numbered rows, and the live
value at the end of each one — the SSID you are on, how many pads answered,
how many BIOS sets are complete. **Every one of those is read from the box or
left blank.** The capture's own figures (−42 dBm, 82 % battery, `2.4.0 →
2.4.2`) have no source on this machine, and a rail that invents them is a rail
nobody can trust for the values that are real. A row whose endpoint did not
answer shows nothing — not a dash, which reads as a measurement of "none".

Eight rows for ten host pages, which is not a page left behind: `Update`,
`Standby`, `Storage` and `Desktop` sit one level down under `System`, and
`theme.json` declares all ten. Returning from one of them lands back on
`System` rather than at the top of the rail.

`Controllers` is this theme's own page — the host has none. It does not carry
the capture's dead-zone slider or exit-combination picker, because neither
exists on this box: dead zones are written per emulator by configgen and the
exit hotkey is generated rather than chosen. It states what is connected, read
from the Gamepad API rather than from `sysinfo.controllers` (that field is
`read_batteries()`, which cannot see a wired pad), and says where the three
real controller settings actually are.

## What this screen deliberately does not do

The capture proposes more than the box can honestly answer. These are refusals,
written down so the next person does not spend a day rediscovering them.

**Display — no resolution, refresh rate or VSync.** A mode switch needs a
revert-unless-confirmed timer, and here that timer would have to run inside the
frontend — the very surface a bad mode makes invisible and unpilotable. There
is no second channel to confirm from with a pad in your hand. On top of that,
`xrandr` is in none of the sudoers rules, `fullscreen_enforcer.py` reads the
current display state, and the X11 session is configured at install time.
VSync alone would have been safe, but it is written per emulator by configgen,
so one global switch would misstate what it governs. Desktop Mode already puts
the desktop's own display tools within reach.

**System — no `pacman -Syu`.** The sudoers rules (`install/arch.sh`,
`install/steps/setup-update-permissions.sh`) each name a binary and usually its
exact arguments: `systemctl poweroff|reboot`, `udevadm trigger`,
`gamecore-session-select gamecore|desktop`, two `systemctl start` units,
`cpupower frequency-set`, and `gamecore-emu`. A NOPASSWD rule for pacman is not
another line of that kind — pacman runs package hooks as root, so it is a root
shell obtainable by installing any package. And the failure mode decides it
anyway: interrupted halfway, `pacman -Syu` leaves mesa or the libc inconsistent
— no frontend, no pad, no way back from a sofa, repair needs a TTY and a
keyboard. Updating GameCore itself already covers the real need and is what
Settings → System → Update does.

**Emulator versions and "Update all".** `gamecore-emu` has `install`, `remove`,
`reconfigure` and `verify` — no `update` verb — and nothing on the box asks a
remote what version it offers. `pergame.emulator_version()` can read an
installed Flatpak's version, but it is Flatpak-only and no endpoint exposes it.
So the capture's `2.4.0 → 2.4.2`, its per-row Update buttons and its "Update
all" describe an action that does not exist. This is the most tempting row on
the screen and the most dishonest: it promises work nobody can perform.

Also dropped for want of a source: Wi-Fi gateway/DNS/MAC/band/channel/link
rate and WPA2-vs-WPA3 (the backend knows `secured`, a boolean, and a 0–100
signal that is not dBm); the Wi-Fi and Bluetooth radio switches (no route);
per-Bluetooth-device battery and RSSI (`BtDevice` is `{mac, name, connected,
paired}`, and the battery levels that exist carry no MAC to join on); stick
dead zone and exit combination; background music; the kernel version; and an
ejectable internal disk — `storage.report()` excludes it on purpose, since an
Eject button on your own root filesystem is not a feature.

## Deliberate deviations

**The overlays are dark, on a light theme.** Wi-Fi, audio, Bluetooth, standby
and the updater are the host's pages, reused whole, and every one writes its
text in hardcoded white. A paper panel would hand you a menu in paper and a
Wi-Fi page in white-on-white. So the theme's own menus join them in warm
near-black — the drawer under the shelf — and `--gc-overlay-*` brings the
reused pages the rest of the way.

**The turned box does not use the host's `Cover`.** `Cover` draws at
`object-fit: cover` in a frame the caller sizes; a shelf needs the opposite,
because a box that crops its own cover is not a box. The front is a plain
`<img>` at its natural ratio with the same fallback chain reimplemented rather
than skipped. Everything else still goes through the host's components.

**The card is not the host's `Meta`.** The capture's card is a spec table —
Released / Developer / Publisher / Genre / Players — not a row of chips. One
`sdk.api.media.list()` answers with the metadata *and* the artwork catalogue,
so the card costs one request, on the settled selection only.

**The dashboard is a horizontal rail, and the host's pager is untouched.**
`HomeScreen` traverses a COLS × ROWS grid across pages and a theme may not
change that. But read its `navigate()` closely and the grid already *is* a set
of horizontal lanes: pressing right at the last column turns the page and lands
on `row * COLS` — the same row. From system 3 you go to system 8, never to 4.

```
grid, as the host pages it        the same thing, drawn as lanes
page 0      page 1                lane 0 ▸ 0 1 2 3 8 9 10 11 …
0 1 2 3     8  9 10 11            lane 1 ▸ 4 5 6 7 12 13 14 15 …
4 5 6 7    12 13 14 15
```

So each grid row is laid out as one continuous rail, and ←→ walks it linearly
straight through the page boundary, ↑↓ changes lane, L1/R1 still pages.
Nothing is rebound and nothing is reimplemented — what you feel under your
thumb is the pager the host wrote.

The view reads `cols` and `rows` from props rather than assuming 4 and 2, so
**setting `ROWS = 1` (and `COLS` to taste) in
`frontend/src/components/HomeScreen/index.tsx` turns this into a single
unbroken rail** with no change to the theme. `DefaultHomeView` builds its grid
from the same two props, so it follows too. That is the one-line change if you
want the pure single-row feel; the theme is correct either way.

Every console on the rail is the same solid the library builds, on the same
plank, under the same card. Four faces instead of six: a console box is never
flipped and never seen from below, so a back and a bottom would be hidden
layers for nothing. The artwork is the system's own logo — there is no
`box-front` for a console — on cardboard under a band of its accent colour,
which the spine repeats.

**The screensaver is the default.** The standby slideshow is dark cover art,
which is right for a room that has gone quiet, and nothing in the capture
suggested otherwise.

## Searching

Not in the reference capture, and worth adding: with several hundred games on
a shelf, the alphabet rail alone is not enough.

The bar sits at the top left of the library. **Searching itself stays the
host's** — △ opens its on-screen keyboard, which owns the modal stack and the
d-pad bindings, and reimplementing that would be reimplementing the one thing
the bar exists to reach. So the bar shows the live query, the hit count as
`12/486`, and names the button that opens the keyboard. The text field beside
it is for a mouse and a real keyboard, and calls the same `onSearch` the
keyboard calls.

While a query is live the bar takes the artwork's accent, and the empty state
offers to clear it rather than sending you back to the systems list.

## Moving between the two screens

The host toggles the screens with `display`, so there is no outgoing frame to
animate — a hidden element cannot be tweened. But an element going from
`display: none` to visible restarts its animations, which is the hook: the
arriving screen plays itself in, and choosing a console reads as walking up to
its shelf. The plank draws outwards, the rail rises, the card slides in from
the right, the header settles. Coming back with ○ does the same for the
consoles.

It is applied to the screen's *contents*, never to `.cz-lib` itself: an
animated `transform` there would become the containing block for the boot
overlay's `position: fixed`, and the iris would close on the wrong thing.

## Fallbacks, all of them drawn

Nothing in this theme shows a hole or an error where artwork is missing.

| Missing | What you get |
|---|---|
| `box-spine` | a printed spine — black field, coloured wordmark, which is what real cardboard is |
| `box-front` | the title set on cardboard, and "No cover scanned" |
| `box-back` | a **printed reverse**: the blurb, whatever screenshots the game carries, the publisher, the region and a barcode. Turning a box over and finding the front again reads as a broken control |
| `cart-front` | a cartridge shell in CSS with the jacket set into its label window. Disc dumps (`.iso .chd .cue .pbp .rvz .nsp …`) get a disc instead |
| metadata | every row falls back to `—`; the card never renders empty |

## Motion budget

Six animated elements at rest, and every one stops.

| Element | Property | Duration | Idle |
|---|---|---|---|
| two wallpaper layers | `transform` | 140s / 190s loop | paused on standby and while a game runs |
| the rail | `transform` | 340ms | static |
| the solid (turn / flip) | `transform` | 620ms | static |
| a console box turning to focus | `transform` | 420ms | static |
| screen entrance (5 elements, staggered) | `transform` `opacity` | 420–560ms | plays once on arrival |
| the wall tint | `background-color` | 900ms | static |
| boot: rise then iris | `transform` | 900ms + 620ms | only while launching |

`prefers-reduced-motion` collapses all of it to 1ms.

## Installing and testing

1. Copy this folder to `config/themes/shelf/` on the box — drag & drop through
   the rom-manager addon from any browser on the LAN, or over SSH.
2. Settings → Themes → Shelf.
3. Theme files are served `no-store`, so editing is save-and-reload. If a
   reload seems to change nothing the theme failed to load rather than loading
   unchanged: Settings → Themes lists an unusable theme with the reason.

What to look at, per surface:

- **splash** — a cartridge drops into a slot, overshoots, settles; wordmark fades up.
- **home** — consoles on two horizontal planks. Hold ← or →: the rail slides
  sideways and keeps sliding *through* the page boundary without jumping to
  the other plank. ↑↓ swaps plank. The focused box should *turn* towards you
  and lift, and the wall retints to its colour.
- **the transition** — ✕ on a console, then ○ back, a few times. The arriving
  screen should build itself in each way, not appear whole.
- **search** — △ opens the host's keyboard; the bar shows what you typed and
  the hit count. Type in the field with a mouse and the shelf filters live.
- **library** — spines slide, the centre box holds still and its artwork settles
  150ms behind the cursor. **L2** turns it over: watch it go *past the opening
  edge*, not cross-fade. **R2** three times returns you to `shelf`.
- **alphabet rail** — jump with the mouse; sort by playtime with L1/R1 and the
  rail hands over to a sort note, because letters mean nothing under that sort.
- **boot** — ✕. The card empties, the cartridge rises and fills the screen, the
  iris closes on its label, black.
- **overlays** — ≡ for settings, then Wi-Fi: the reused page should sit in the
  same warm dark as the menu that opened it, in seal gold, not default purple.

## Still to produce by hand

`preview.png` — the thumbnail in Settings → Themes. A model cannot draw one.
The shot to take: `shelf` mode, a colourful jacket selected so the wall is
strongly tinted, the box turned about 25°, the card visible at the right.

## Files

```
index.js       the wiring, and nothing else
theme.json  theme.css  README.md
views/   splash.js     the cartridge going in    home.js       the consoles
         background.js the wall                  library.js    the shelf
         box.js        the solid and its spines  cartridge.js  the media
         topbar.js     the shelf label           settings.js   the drawer
         themes.js     the picker                power.js      restart / off
         gamepad.js    the live pad
lib/     paper.js      the wallpaper, as a mask  accent.js     the colour
         names.js      titles, letters, regions  dossier.js    one lookup
         browse.js     flip and restack          idle.js       is anyone here
```
