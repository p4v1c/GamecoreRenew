# Stremio on GameCore

> **TL;DR** — The tile opens the **official Stremio desktop client**, unmodified.
> The only thing it lacked for couch use was an on-screen keyboard, so a small
> local proxy serves Stremio's own web interface with a keyboard script injected
> into it. No fork to build, no browser kiosk, no transcoding, no system service.

## The setup

| | |
|---|---|
| Client | Flatpak `com.stremio.Stremio` — the official desktop client, untouched |
| Keyboard | [`stremio-gamepad-keyboard`](https://github.com/p4v1c/stremio-gamepad-keyboard), cloned to `/opt/Stremio` |
| Tile | `bash /opt/Stremio/stremio-tv.sh` |

`stremio-tv.sh` starts a local proxy, then opens the client on it. That is the
whole mechanism.

The client (`stremio-linux-shell`, Rust + GTK4 + WebKitGTK) has no interface of
its own: it displays the official web interface, `https://web.stremio.com`, and
plays through mpv. It takes a `--url`, which is the seam the keyboard uses — the
proxy relays that same interface and adds one `<script>` to it. Rendering, mpv
and the shell↔interface dialogue are untouched.

Gamepad **navigation** needs nothing from us: the v5 interface handles it
natively. Only the keyboard was missing.

## Why not a browser kiosk any more

GameCore used to run a fork of `stremio-web` (with a TV keyboard) in a Firefox
kiosk, plus three user services. It worked, but it fought the browser the whole
way:

- In a browser, a stream is either played directly by `<video>` or **transcoded**
  by the local server. `stremio-video` only allows direct play of `matroska,webm`
  when `window.chrome` exists — under Firefox it does not, so **every MKV**,
  meaning nearly every debrid release, went through the transcoder.
- That transcoder ran on the host's node and ffmpeg only because the Flatpak
  runtime's ffmpeg is built with `--disable-decoder='h264,hevc,vc1,vvc'`: inside
  the sandbox, x265 answered `no decoder found for: hevc` and the player waited
  forever on a stream that never came.

The desktop client sidesteps all of it: it plays through mpv, natively, and
`supportsTranscoding()` is false for it. So the fork, its build (minutes of
`pnpm`), the three services and the host-ffmpeg workaround are all gone.

The `ffmpeg` package is no longer needed *by Stremio*. It is still installed as
general media tooling; nothing else in the tree calls it.

## Sanitising the gamepad

The injected script also filters what the interface reads from the gamepad,
because it reads it too bluntly. Both problems are worth knowing about — they
look like application bugs.

**A DS4 publishes two gamepads.** The controller, and its motion sensors —
announced as `mapping: "standard"` as well, with the same button count. Only the
name tells them apart:

```
#0 standard  Wireless Controller                axes=[0, 0, -0.04, 0]
#1 standard  Wireless Controller Motion Sensors axes=[0, 0.24, 0, 0]
```

The second one's vertical axis sits at **0.24** with the pad flat on a table, and
the interface treats a stick as active from **0.05**. It therefore sees a
permanent press downwards: lists scroll on their own and no stream can be picked.
The phantom is hidden.

**Sticks do not centre exactly.** Measured on that same pad: right stick stuck at
-0.051, noise up to 0.109 — above the interface's threshold, which is enough to
rewind a film and drift the volume. Resting is widened to 0.15 before the
interface reads it; past that the value goes through untouched.

## Troubleshooting

```bash
# Is the injection proxy up?
curl -sI http://127.0.0.1:8098/__gc/osk.js | head -1

# Which URL did the client get? It must point at the proxy, not web.stremio.com
pgrep -af 'libexec/stremio/stremio'

# The client's own streaming server
ss -tlnp | grep 1147
```

Known traps:

- The client is a **GApplication**: a running instance absorbs the next launch
  and silently drops its arguments, so `--url` goes unnoticed. `stremio-tv.sh`
  kills any instance first.
- Never pass two `-u`: argument parsing fails with a message pointing elsewhere
  (`required argument was not provided: dev`).
- Never set `RUST_LOG`: the shell passes it down to mpv, which rejects it —
  `Failed to create mpv: Raw(-11)`, a panic at startup and no window at all.
- Browser local storage is partitioned **per origin**. Serving the interface
  through the proxy changes the origin, so the account and library appear to have
  vanished on first launch; `stremio-session-migrate.py`, which `stremio-tv.sh`
  calls, carries the storage over once.
