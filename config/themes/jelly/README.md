# Jelly 1.2.1

A bright, rounded GameCore theme: a cyan playground, purple and pink jelly
tiles, keys that press down, one burst of confetti at boot. Textures and
interface only — no characters, no avatar, no profile circle (GameCore has no
accounts). Built from the approved "GameCore · Jelly" mockup; its eight demo
games, fake networks and fake BIOS states are gone, replaced by the box's own
data. Interface text is French.

Requires SDK 9 (`GamepadView`, `launchGame`, sessions). Other themes are not
touched.

## Screens

| Screen | What it shows | Whose behaviour |
|---|---|---|
| **Jouer** | the suspended game, else the last one played; *Mes favoris*, *Surprends-moi*; the last five adventures | Jelly draws, `sdk.defaults.launchGame` / `sdk.session.resume` act |
| **Collection** | every game on every console, filtered by console or favourites | Jelly |
| **Consoles** | one photo card per installed console, then the applications | ✕ opens the host library or launches the app |
| A console's library | the host's library screen in Jelly cards | host: loading, sort, △ search keyboard, Options per-game options, launch |
| Search (△ from the dashboard) | *La bonne pioche*: keyboard, filters, results | Jelly |
| Game fiche | jacket, metadata, playtime, Play / Resume, favourite | Jelly, launch by the host |
| Settings (Options) | the host's nine categories, dressed | host (`createSettings`, `pager`, `detail: 'dialog'`) |
| Power (Share), controller (□), session menu (PS ×2) | dressed host markup | host |

**Pictures.** Game cards stand on the game's 3D box (`box-3d` in its media
index) when it has one, drawn at its own shape on the jelly, and on the flat
jacket otherwise (cover API, then scraped `box-front`, then the title drawn on
the colour). A chip in Collection and in each library switches every card to
flat jackets; the choice is kept as `jelly-jacket`. Console photos are the
packs' (`system.art.console`, from `catalog/<id>/art/`): Jelly ships none, so
changing one is changing that file. A pack without one shows its mark.

Favourites live in this browser's storage (`jelly-favourites`, keyed
`system:filename`): GameCore has no favourites of its own. Nothing else is
stored by the theme, and never a password.

## Pad

The dashboard binds its own d-pad, L1/R1 and ✕ (`homeOmit`), the library its
own d-pad and ✕ (`libraryOmit`); PS, Options and Share stay the host's.

| | Dashboard | Search | Settings |
|---|---|---|---|
| d-pad | move inside the tab, never diagonally when a straight step exists | move inside the lit zone | ↑↓ categories, → enter |
| ✕ | choose | type / choose | enter / change |
| ○ | back to Jouer | keyboard, then close | back to the categories, then close |
| △ | search | keyboard ↔ results, both remembered | — |
| □ | controller screen | erase a letter | — |
| L1 / R1 | tabs | zones: Keyboard, Filters, Games | categories |
| L2 / R2 | — | L2 clears query and filters | scroll the page |

The search opens with the cursor on A, never on a text field; typing never
moves it; a fiche closes back onto the result it came from. Every layer Jelly
opens raises the modal depth, so the screen behind it stands down, and each
press is judged by the state it started in (`navAtPress` in `lib/spatial.js`):
when the host's ○ takes the library home, Jelly's dashboard does not act on the
same press.

**Compromise.** △ inside a console's library is the host's: it opens the host
search keyboard for that console (dressed in Jelly through `--gc-overlay-*`),
not Jelly's three-zone search. The host binds it there and no `libraryOmit` id
releases it. From the top bar or the dashboard, Jelly's search covers every
console.

## Files

```
index.js            createParts (every screen over one context) and the theme's surfaces
DESIGN.md           idea, type, palette, shape, depth, motion, voice
lib/                catalog (names, marks, colours), collection (all games + playtime),
                    spatial (pad moves) + presses (who owns a press), search, launch,
                    art (3D box / jacket fallbacks) + jacket-style, icons, favourites,
                    format (French), tabs, drawings
views/              home + home/{play,hero,shortcuts,collection,consoles},
                    library/{index,toolbar,rows}, search/{index,header,zones,results,keyboard},
                    details, cards, chips, topbar, footer, background, splash, ceremony,
                    session, settings, controller
css/                base, shell, cards, home, dialogs, moments, settings, motion
fonts/red-hat/      Red Hat Display (SIL OFL)
```

Sizes are multiples of `--px`, one pixel of a 1920×1080 design, so 720p and 4K
keep the same layout. Reduced motion stops the wobble, the texture and the
confetti; focus keeps its ring.

## Checks

- `node scripts/check-theme.mjs config/themes/jelly` — 39 modules, all ten settings pages reachable
- `npx vitest run src/themes/jelly src/themes/themeSplashContract.test.tsx` (frontend)
- `pytest backend/tests -k theme` — the shared theme rules (ceremony length, settings grid, versions, controller wizard)

## Credits

Console photos: in the packs, with their Wikimedia Commons source beside each
(`catalog/<id>/art/SOURCE.md`). Red Hat Display: Red Hat, SIL Open Font License
(`fonts/red-hat/OFL.txt`). Game jackets come from the box's own cover service;
none ship with the theme.
