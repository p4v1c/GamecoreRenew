# Logo credits

The `logo.png` of these packs is the "Systematic" system icon by baxysquare,
from [libretro/retroarch-assets](https://github.com/libretro/retroarch-assets)
(`xmb/systematic`), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Rendered at 512×512 from the vector sources in
[baxysquare/baxy-retroarch-themes](https://github.com/baxysquare/baxy-retroarch-themes)
(`Systematic/src/pdf`); no other change.

atomiswave, dreamcast, fds, gamegear, mame, mastersystem, megacd, megadrive,
gb, gba, gbc, naomi, naomigd, nes, pcengine, pcenginecd, saturn, sega32x,
sg1000, snes9x, supergrafx.

Rendered with `pdftocairo -png -singlefile -scale-to 512 -transp "<name>.pdf"`
from `Systematic/src/pdf/<name>.pdf`; `megadrive` re-renders pixel-identical.

`wii` is drawn for GameCore in that style: Systematic has no Wii with its
Wii Remote, and its console alone reads as a blank white card on a tile. Same
palette, same 16 px half-white outline; source in `catalog/wii/logo-source.svg`,
outline added when rendering to `logo.png`. Released under CC BY 4.0 like the rest.

`gamecube` is the purple cube the `dolphin` tile has always shown, copied
unchanged from `catalog/dolphin/logo.png`.

`dolphin` and `mgba` keep the logos they had before the split into one pack
per system; they are shown only on a box that has not run
`scripts/split-systems.py` yet.

Console names and logos are trademarks of their owners.
