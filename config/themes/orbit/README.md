# Orbit

Installable GameCore theme. Requires GameCore SDK 5.

## Install

Run `gamecore-theme verify orbit.zip`, then `gamecore-theme install orbit.zip`.
Select Orbit in Settings → Themes. Alternatively extract the `orbit` directory into GameCore’s `config/themes/` directory.
No build, npm installation, backend patch, or changes to other themes are needed.

## Controls

- Home: Left/Right browse installed consoles and applications; Cross/A opens the selected entry.
- Library: Up/Down select a game; Cross/A launches; Circle/B returns home.
- Triangle/Y opens the host’s virtual search keyboard. L1/R1 changes the library sort. R2 opens the host’s per-game options.
- Square/X opens live controller inputs; press it twice to close. Hold Triangle/Y there for the host mapping wizard.
- Options/Menu opens all host settings, including catalog, controllers, network, storage and themes. Share/View opens power controls.
- L2 manages a suspended session, when there is one. D-pad selects an action; Cross/A confirms; Circle/B or L2 goes back. L1/R1 switch between suspended sessions.
- Home/Guide twice suspends the running game and returns here. That gesture belongs to the core, not to Orbit.

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

The thirteen console photos are 5.1 MB, down from 28.8 MB. Ten of them were
already 960 px on the long edge; three were 3760–6000 px, which is four to six
times more pixel than this theme can draw — the largest any of them appears is
`.orbit-feature-art`, capped at 450 px and 40vh, or 864 px on a 2160p panel. Those
were resampled to the same 960 px norm and everything was recompressed. The ten
that were not resampled are pixel for pixel what they were.
`assets/source-credits.json` is unchanged: resampling a photograph does not
change where it came from.

## Validation

Do not take the previous version’s “12 integration tests passed” on faith; that
was an assertion in a README, not a test anyone else could run. What can be run
is in the repository: `backend/tests/test_sdk_version_gate.py` computes the SDK
level Orbit actually uses from its sources and compares it with the manifest,
`backend/tests/test_shipped_theme_views.py` checks the controller screen still
reaches the mapping wizard, `frontend/src/lib/themeSplashContract.test.tsx`
holds the splash to the boot contract, and `scripts/check-theme.mjs` parses every
module and verifies the settings menu reaches all ten host pages.

Physical-controller and on-device verification remain to be performed.
