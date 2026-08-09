# Default (remake)

The stock GameCore UI, rebuilt as an ordinary third-party theme.

It exists to answer the only question that tells you whether a theme SDK is
finished:

> **Can the default frontend be expressed through it?**

Anything the default UI can do that a theme cannot is a hole, and the reliable
way to find those holes is to stand where a theme author stands and try to
rebuild the thing you already have. This theme is that attempt, and it stays in
the tree as a regression test: the day someone adds something to the default UI
and forgets to expose it, this theme is what stops looking like the default.

## What it found

Six gaps, all now closed. None of them stopped a theme from *loading* — every
one of them let a theme load and then be quietly worse than the default, which
is the failure mode this exercise is for.

| Gap | Symptom before |
|---|---|
| `sdk.format.systemColor` | The resolver was a private `getColor()` in `SystemCard`. `SystemEntry.color` is optional, so a themed dashboard painted every system the catalogue does not describe in the house purple — the same fallback chain existed in three places and none was reachable |
| `sdk.format.gameName` | A themed library could not turn `Super_Mario_64_(USA).z64` into a title. That function carries enough accumulated ROM-naming rules to have its own test file |
| `sdk.format.time` / `date` / `hexToRgb` | A theme said "3h 42m" differently from the rest of the UI |
| `sortKeys` / `sortLabels` on the library view | L1/R1 cycle a list held in `LibraryScreen`. A theme typing its own copy would draw one set of options while the buttons walked another |
| `toasts` as a shell part | The stack was rendered by the shell and not overridable, so a theme writing its own tree lost every notification — including the offer to map a controller emulators cannot bind |
| `sdk.system.splashHoldMs` | Electron asks for a cold-boot hold through the URL and the default splash honoured it silently, so every themed splash started mid-animation on the one boot that matters |

A seventh was found by the guard this work added rather than by the remake:
`storage` was missing from `DefaultSettingsPages` altogether, so safe-eject for
an external disk was unreachable from *any* theme that could ever be written.

## What it does not reproduce

Stated plainly, because a remake that quietly diverges is worth less than one
that says where it stopped:

- **The splash's audio is simplified.** The host's version runs a convolution
  reverb, a sub-oscillator with an LFO, a sparkle and an impact thump. This one
  keeps the pad and the Dmaj7 chime. Everything it drops is reachable through
  `sdk.system.getAudioContext()` — this is a length decision, not an SDK limit.
- **The top bar draws a wordmark, not the logo image.** The host imports a PNG
  through the bundler; a theme would ship its own via `sdk.system.asset()`.
- **It is a structural remake, not a pixel copy.** Spacing, easing and a number
  of colours are close rather than identical. What is faithful is the layout,
  the information shown, and every prop consumed.

## What it proves

- Eight of the ten shell parts are exercised: `topbar`, `homeView`,
  `libraryView`, `settings`, `powerView`, `gamepadView`, `screensaver`,
  `toasts`. The two left out are `background` and `decor`, and that is the
  faithful answer rather than a shortcut — the default UI has no full-screen
  layer behind or in front of itself, so supplying one would stop this being a
  remake. `config/themes/summer` exercises those two.
- A theme can animate at 60 fps without re-rendering — one rAF loop writing to
  the DOM through refs, no per-frame React.
- A theme can synthesize audio on the host's context and stay inside the
  player's sound setting.
- A theme can reuse the host's settings sub-pages, rendered **bare**, and
  restyle them through `--gc-overlay-*`.
- It declares **no** `sounds` and **no** `rumble`, exactly as the default UI has
  none — so it exercises the fallback end of both cascades every time it runs.

## Reading it

`index.js` is wiring and nothing else. One feature per file:

```
views/  splash.js  the boot animation   home.js         the dashboard
        topbar.js  clock, IP, battery   library.js      the game list
        settings.js  the menu           power.js        restart / shutdown
        gamepad.js the live pad         screensaver.js  standby
        toasts.js  the notifications
lib/    card.js    one system tile
```

Nothing here decides anything. Paging, focus, sorting, search, launching, the
modal stack and the button bindings are all the host's — which is why this theme
and the default behave identically and only the drawing differs.
