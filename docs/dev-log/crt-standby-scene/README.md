# The standby room: re-rendering the plate

`crt-room.py` builds the room the CRT standby draws (a blue bedroom at night, a
maroon CRT on a white stand) and renders it with Cycles. The shipped files are
in `frontend/src/assets/standby/`:

| File | What | Made with |
|---|---|---|
| `room-off.webp` | the room, TV off: dark glossy glass, no TV light | `--screen off`, 1920 px, 128 samples |
| `room-tvlight.webp` | only the light the TV throws on the room, white | `--screen off --pass tvlight`, 1280 px, 64 samples |
| `room-screen.json` | the 4 corners of the TV glass in the picture | written next to every render as `<out>-screen.json` |

The interface lays the game video over the glass with a homography computed from
the corners, then tints `room-tvlight` with the video's colour and screens it
over `room-off` (`frontend/src/components/CrtStandby/`).

## Render

Blender 4.x as a Python module (`pip install bpy` in a venv), or
`blender -b -P crt-room.py -- ...`.

```bash
SCENE=docs/dev-log/crt-standby-scene
ARGS="--covers $GAMECORE_DATA/emu/covers --assets /path/to/assets"
python $SCENE/crt-room.py -- 1920 128 /tmp/room-off.png --screen off $ARGS
python $SCENE/crt-room.py -- 1280 64 /tmp/room-tvlight.png --screen off --pass tvlight $ARGS
python3 -c "from PIL import Image
for n in ('room-off', 'room-tvlight'):
    Image.open(f'/tmp/{n}.png').convert('RGB').save(f'frontend/src/assets/standby/{n}.webp', 'WEBP', quality=92, method=6)"
cp /tmp/room-off-screen.json frontend/src/assets/standby/room-screen.json
```

About 7 minutes for the plate and 80 s for the light pass on 4 CPU cores.
Blender may segfault on exit after `Saved:`; the files are already written.

`--screen on --frame <png>` renders the look the owner validated, with a
picture on the glass.

Dust is left out of the plate by default: a baked mote cannot move. The
interface draws falling dust instead. `--dust on` puts the 45 still motes back.

## What it needs

- **`--assets`**: a folder holding `gamepad/gamepad_1k.gltf` (+ its `.bin` and
  `textures/`), the [Gamepad](https://polyhaven.com/a/gamepad) model by Josh
  Dean from Poly Haven, 1k glTF download. Everything else is procedural.
- **`--covers`**: GameCore's cover cache (`<data>/emu/covers/<system>/`). The
  boxes on the floor and on the shelf use eleven named covers from it (see
  the paths in the script); a missing one fails the render.

## Licences

- Gamepad model: Poly Haven, **CC0** (public domain).
- Box art on the floor and the shelf: the owner's own library, as scraped into
  the cover cache. They are **baked into `room-off.webp`** and are not
  redistributable artwork in their own right; the shipped plate is the owner's
  picture of their room. A plate rendered for someone else should use their
  covers (or none).
- Everything else (room, furniture, CRT, lamp, blinds, dust) is procedural
  geometry in `crt-room.py`.

## Known limits

- The floor boxes are baked into the plate, so they do not follow the library.
  Fine for v1; a later version could render the floor without boxes and lay
  real covers over it like the video.
- The screen corners are exact for this camera only. Re-render the JSON with
  the plate whenever the camera, the TV or the stand moves.
- Vertex order in the JSON is the plane's: bottom-left, bottom-right, top-left,
  top-right (y from the top). The UI sorts the corners rather than trusting the
  order (`frontend/src/lib/homography.ts`).
