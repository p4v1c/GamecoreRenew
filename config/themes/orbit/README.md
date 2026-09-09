# Orbit

Installable GameCore theme, built from the interactive mockup (`gamecore-orbit`).
Requires GameCore SDK 5.

## Install

Run `gamecore-theme verify orbit.zip`, then `gamecore-theme install orbit.zip`.
Select Orbit in Settings → Themes. Alternatively extract the `orbit` directory into GameCore’s `config/themes/` directory.
No build, npm installation, backend patch, or changes to other themes are needed.

## The four tabs

The mockup’s whole shape is its navigation, and so is this theme’s.

| Tab | What it is |
|---|---|
| **Games** | a rail of what you have actually been playing, with the applications on the same rail and the whole library one tile away at the end. A hero panel underneath: console, title, description, genre and year from the metadata, time played, Play and the favourite heart. |
| **Consoles** | the showcase — maker, year, the console’s own photograph on a plinth, a line about the generation — over a grid of every console you have installed. |
| **Library** | one console’s games as cover cards, with the other consoles as filter chips, a search field, and a favourites filter. |
| **Applications** | the app rail and its feature panel: category, edition, description, and Open. |

`L1` / `R1` walk the tabs on Games, Consoles and Applications. In the Library
they sort, because that is the host’s binding and the host’s screen — `○` leaves.

### Where this departs from the mockup, and why

- **The rail is what you played, not every game you own.** The mockup listed
  twelve invented titles. A real box has however many ROMs its owner put on it,
  and “every game” is not a rail, it is a wall nobody reaches the end of. The
  playtime table already knows the useful subset.
- **There are no bundled games or consoles.** Everything on screen is a pack you
  installed. The mockup’s `games` and `systems` arrays are gone; what survived
  is the *presentation* — maker, year, accent, the sentence under the console
  name — keyed by the real pack id, in `lib/catalog.js`.
- **The Library is per console, and the filter chips switch console.** GameCore
  keeps ROMs per console and the host’s library screen is scoped to one. “All of
  them” is the Consoles tab, which is a better answer than a chip.
- **Favourites are this theme’s, in this browser’s storage.** GameCore has no
  favourites: no endpoint, no column. Nothing else on the box can see them.
- **The control centre, the power menu, the search keyboard and the controller
  diagram are the host’s.** The mockup drew its own with simulated data; a theme
  that shipped those would be showing fixtures where the box has facts.

## Suspend and resume

Orbit draws GameCore’s session lifecycle. It does not implement one.

Pressing Home twice freezes the running game or application — the whole process
group, so a Flatpak emulator stops down to the last process in its sandbox — and
puts you back in the interface with the controller working. The session dock
along the bottom of the screen shows what is frozen; Cross/A resumes it, and
closing it is a separate, deliberate action that asks first.

Everything behind that comes from the host through `sdk.session` (SDK 5): the
state, the actions, and every rule about them. How many sessions may exist at
once, what happens when one is resumed while something else holds the screen,
and whether a launch is refused are the core’s decisions, and Orbit does not
have an opinion about any of them. Playtime does not count the time a session
spends frozen — also the core’s doing, not Orbit’s.

The dock itself is mounted by the host, above the shell. A theme supplies the
picture and cannot remove the bar: it is the only way back to a frozen game, and
a theme that simply forgot to draw one would leave an emulator holding several
gigabytes of memory with nothing on screen able to reach it.

### What this replaced

Version 1.0.0 shipped a *local session preview*: an in-memory model in
`lib/local-session.js` with `foreground`, `background` and `askClose`, and a
session object no process ever answered to. It called no endpoint and suspended
nothing, and the README said so in as many words. It is gone. `lib/session.js`
is the adapter over the real API, and nothing in the interface says “preview”
any more, because there is nothing left to hedge about.

## Data and artwork

Home shows the actual installed console/application entries exposed by the SDK. A console opens its real game library. Covers, metadata and available backdrops come from GameCore. There are no bundled demonstration games, fake controllers, profiles or recommendation sections. The native SDK’s library uses Up/Down, so Orbit presents a vertical game list with a large artwork detail area.

Only connected controllers supplied by the host are displayed. IP is in the footer; storage is in settings. Pack application logos fill branded tiles. Console artwork is owned by Orbit and resolved through `sdk.system.asset`; mappings and app presentation are in `lib/artwork.js`. Unknown systems fall back to their pack logo, then initials. Editing this mapping never alters the other themes.

Console photo source/attribution pages are recorded in `assets/source-credits.json`. The hardware and application names/logos belong to their respective owners. Orbit is an independent community theme.

### Weight

The thirteen console photos are 5.1 MB, down from 28.8 MB. **Eight** were
already 960 px on their long edge and are pixel for pixel what they were; the
other **five** were resampled to that norm — `ps4` at 6000 px, `n64` and
`gamecube` near 3800, plus `ps3` and `xbox360`, which were 960 px *wide* but
1067 and 1322 px *tall*. That is four to six times more pixel than this theme
can draw: the largest any of them appears is `.orbit-feature-art`, capped at
450 px and 40vh, or 864 px on a 2160p panel.

(An earlier version of this file said ten and three. It was counting width
rather than the long edge, so the two tall ones were described as untouched
while the resizing script had correctly shrunk them. The numbers above are
`Image.tobytes()` hashes taken against the original archive.)

`assets/source-credits.json` is unchanged: resampling a photograph does not
change where it came from. Its thirteen entries still name the thirteen files.

## Validation

`frontend/src/lib/orbitTabs.test.tsx` mounts the four tabs against the real host
and the real SDK — the same assembly `index.js` builds, `homeOmit` included —
and asserts which tab is drawn, that the rail comes from the playtime table
rather than a bundled list, that consoles and applications are not mixed into
each other, that the pad moves Orbit's cursor and not a hidden one underneath,
and that Library goes to the host's screen. `backend/tests/test_sdk_version_gate.py`
computes the SDK level Orbit actually uses from its sources,
`test_shipped_theme_views.py` checks the controller screen still reaches the
mapping wizard, `themeSplashContract.test.tsx` holds the splash to the boot
contract, and `scripts/check-theme.mjs` parses every module and verifies the
settings menu reaches all ten host pages.

How it *looks* on a television is not claimed by any of that.
