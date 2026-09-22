# Orbit 3.6.14

A cinematic GameCore theme with Games, Consoles and Applications.
Choose a console to open its game library within Consoles. Back returns to the
console showcase; L1/R1 cycle the three main tabs.
Requires GameCore theme SDK 6. Based on GameCore v1.2.44 (03c0df8).

## Install

Run `gamecore-theme verify orbit-3.6.14-clean-fixed.zip`, then
`gamecore-theme install orbit-3.6.14-clean-fixed.zip`. Select Orbit in Settings → Themes.
Alternatively, extract the `orbit` folder into GameCore's `config/themes/`.
No build, npm installation or backend patch is required. Other themes are unchanged.

## Code refactor in 3.6.14

- No visual, navigation, API or session behavior is intentionally changed.
- `views/home.js` is now a small composition root; Games, Consoles, Applications
  and the home hooks live in focused modules under `views/home/`.
- Console metadata tuple access is centralized behind named fields instead of
  scattering numeric indexes through the theme. `consoles` and `meta` stay compatible.
- The duplicate guarded `scrollIntoView` helper is shared from `lib/dom.js`.
- Home artwork fallback behavior is isolated in `lib/art.js`.
- `theme.css` and all artwork/assets are unchanged from 3.6.13.

Static refactor checks cover JavaScript syntax, relative import resolution, module
loading and catalogue output parity against 3.6.13. Runtime testing on GameCore
with a physical controller is still recommended before replacing an installed copy.

## Cover improvements in 3.6.12

- Games shows up to six games, prioritising recently played titles, alongside
  installed applications and the Collection shortcut. The console library keeps
  its responsive grid and includes the full collection.
- Larger home tiles, with the artwork area filling 95% of each tile.
- Original image proportions are preserved: horizontal N64 boxes, square DS/GBA
  boxes and vertical Switch/PlayStation cases remain complete and unstretched.
- Library cards use a consistent portrait frame. Wide or square covers have space
  around them instead of being cropped to fit. Titles can occupy two lines.
- Game details show the complete cover beside the title and metadata.
- Low-resolution covers scale up to the available space; their source quality
  still determines sharpness. Missing artwork keeps a readable fallback.
- The Play button stays above the footer at 720p; tiles also scale for 4K.

Artwork comes from GameCore's cover and media APIs. The existing cover resolver
can fall back to box-front media when the direct cover is missing or unsuitable.
There are no bundled demonstration games or new scraping services.

## Navigation and data

Use the directional controls to move focus, Cross/A to select and Circle/B to
return. L1/R1 switch the main tabs. The Library includes All and console filters,
search, favourites and sorting controls. Search uses the host's virtual keyboard;
Square opens the host's controller inputs screen and R2 opens game options.

Applications use installed pack logos. Console presentation assets belong to
Orbit and do not replace other themes' assets. Unknown consoles fall back to the
pack logo or initials. Photo credits are in `assets/source-credits.json`.

Only connected controllers are shown. The IP address is in the footer and storage
information is in settings. Favourites are stored locally in this browser.

## Sessions

This release preserves the SDK 6 host session integration already present in
GameCore v1.2.44. Suspend/resume and close actions depend on the host; the theme
does not implement process management or change its timings. The existing session
dock provides access to suspended games and applications.

## Validation

The preceding cover release passed 64 frontend tests and 3 cover-layout Python tests.
The 3.6.12 navigation change has a focused tab/return smoke check. The theme checker validates
17 JavaScript modules and access to all ten host settings pages. Browser checks
cover 720p, 1080p and 4K, using synthetic DS, N64, Switch, PlayStation and low-resolution
artwork. N64 and Switch covers were also checked in the game-details panel.

These checks do not replace testing with a physical controller and running
emulators on the target GameCore installation.

## Boot animation

Orbit now has a native navy-blue boot animation with luminous orbital rings,
the GameCore mark and a soft reveal into the interface. The introduction lasts
4.8 seconds followed by a 700 ms fade, and waits for host readiness before leaving.
Reduced-motion preferences are respected. The host splash-contract tests pass.

## Navigation polish in 3.6.12

Stronger controller focus, 240 ms page entrances and remembered console selection
when returning from its library. Selection is remembered for the current theme
session. Reduced-motion preferences disable the new transitions.

## Console polish in 3.6.13

- Backdrops keep their existing 175 ms stabilization and preload; transitions
  back to the neutral scene now fade too.
- The library shows the selected title, console, year and a short description.
  Metadata requests wait until selection settles and stale replies are ignored.
- Jackets keep their space while loading, then fade in. Missing art keeps initials.
- The session dock is compact and expands on hover/focus. L2 still opens the
  host menu for resume and close; process lifecycle is unchanged.
- Footer hints remain contextual and use Xbox labels when the first controller
  reported by the host is identified as Xbox/XInput, otherwise PlayStation labels.
- Reduced-motion preferences are respected.

Targeted validation: 11 session tests and 26 physical-media/navigation tests pass.
