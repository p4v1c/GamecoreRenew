# Summer

A WebGL ocean that tracks the real sun, under glass panels.

Ported from the "GameCore Summer" design mockup (`DESIGN-BRIEF.md`). The mockup
was a single ~700-line component that owned everything — its own gamepad
polling, its own clock, fake systems and games. Here:

- **`ocean.js` is the mockup's renderer, kept close to verbatim.** Sky, swell,
  breaking crests, foam, wet sand and grass are one fullscreen fragment shader,
  so there is no texture to ship and the camera never moves.
- **The screens were rebuilt on the theme SDK**, so they run on the box's real
  systems, playtime and controllers, and share the host's single input bus
  instead of polling pads themselves.

## Surfaces

`background` · `topbar` · `home` · `settings`

Everything else — library, screensaver, the power and controller modals — stays
on the default theme. That is what partial override is for.

## Deviations from the brief

| Brief | Here | Why |
|---|---|---|
| Location resolved by geo-IP at boot | a constant in `ocean.js` (`LOCATION`) | a theme making an outbound network call at boot is the box owner's decision, not a stylesheet's |
| Full NOAA solar formulas | the mockup's compact ones | within a few minutes at usable latitudes, and neither needs the network |
| `settings` not designed | built here in the same glass language | the surface did not exist when the mockup was made |

Set `LOCATION` in `ocean.js` if the light should track your actual sky. The
default is Paris.

## Performance

- The ocean is capped at **30 fps** and **pauses entirely** while a game is
  running or the box is in standby — the emulator owns the machine then.
- Render scale drops automatically (1.0 → 0.75 → 0.55) after sustained slow
  frames, so the launcher is never the reason a box feels slow.
- If WebGL is unavailable the canvas stays empty and every other surface renders
  normally.

## Testing notes

The shader compiles and links, and all four surfaces render with real data.
A full-resolution screenshot of the ocean could not be produced under headless
software rendering (SwiftShader is far too slow for this shader) — it needs a
real GPU.
