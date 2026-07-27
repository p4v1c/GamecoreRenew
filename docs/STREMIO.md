# Stremio on GameCore — and why playback used to hang

> **TL;DR** — The Stremio Flatpak's ffmpeg cannot decode HEVC. Since the web UI
> routes almost everything through that ffmpeg, x265 movies never started
> playing. The streaming server therefore runs on the **host's** node + ffmpeg.
> The host needs the `ffmpeg` package (installed by `install/arch.sh`).

## The setup

The Stremio tile does *not* open the Flatpak client. Its UI has no on-screen
keyboard, so search is unusable with a gamepad. Instead GameCore runs a fork of
[stremio-web](https://github.com/p4v1c/stremio-web) (branch
`feature/tv-virtual-keyboard`) in a Firefox kiosk, driven by
[gamepad-tv-bridge](https://github.com/p4v1c/gamepad-tv-bridge), which also owns
the three user services:

| Service | Role |
|---|---|
| `stremio-server.service` | Streaming server (EngineFS, `127.0.0.1:11470`) — the Flatpak's `server.js`, run by `install/stremio-server.sh` |
| `stremio-web.service` | Serves the fork's `build/` on `127.0.0.1:8096` |
| `stremio-tv.service` | Firefox `--kiosk` (launched on demand by the tile) |

The Flatpak stays installed: it supplies `server.js`, and remains usable as a
standalone client.

## The symptom

Starting a movie through a debrid service (AllDebrid, Real-Debrid…) either hung
forever on the loading spinner, or took minutes — on links that are fast by
definition. The **Flatpak client played the same file instantly**, which is what
makes the bug confusing: it looks like the fork is at fault. It isn't — the
fork's diff against upstream touches only UI and gamepad code.

## Cause 1 — Firefox almost never plays a stream directly

In the browser a stream is either played **directly** by the `<video>` element,
or **transcoded** by the local server (`/hlsv2/…/master.m3u8`).

`stremio-video`'s `mediaCapabilities.js` decides:

```js
var formats = ['mp4'];
if (window.chrome || window.cast) formats.push('matroska,webm');
```

Under Firefox `window.chrome` is undefined, so **only MP4 can play directly** —
every MKV, meaning nearly every debrid release, goes to the transcoder. And
`canPlayStream()` (in `withStreamingServer.js`) additionally rejects any file
that carries **embedded subtitles**, or two or more playable audio tracks.

A typical release — MKV, x265, E-AC-3 5.1, embedded subs — fails on all counts.
The transcoder is not an edge case here; it is the normal path.

## Cause 2 — the transcoder could not decode

The server used to run inside the Flatpak, so it used the runtime's ffmpeg,
which is built with:

```
--disable-decoder='h264,hevc,vc1,vvc'
```

| Source | Inside the Flatpak | With the host's ffmpeg |
|---|---|---|
| x265 / HEVC | `no decoder found for: hevc` → the server answers `{"error":{"code":10,"message":"Failed to read hls playlist: Premature close"}}` → the player waits on a stream that never comes | plays |
| x264 | `libopenh264` only: software, and VAAPI is out of reach because hwaccel needs the native decoder | native decoders, hardware-capable |

That is the whole bug: **x265 never started, x264 crawled.**

Why the Flatpak client is immune: it never transcodes. It plays through its own
bundled `libmpv` (`/app/lib/libmpv.so`, with its own libavcodec), and
`supportsTranscoding()` returns `false` as soon as `window.qt` exists.

## The fix

Keep the Flatpak's `server.js`, run it with the **host's node** so it picks up
the system ffmpeg — which has the full decoder set, plus VAAPI when the GPU
allows. `gamepad-tv-bridge`'s `install/stremio-server.sh` handles this: it
resolves `server.js` through `flatpak info --show-location` (system *or* user
Flatpak install) and falls back to the Flatpak's node if the host has no node or
no HEVC-capable ffmpeg — degraded, but the server still comes up.

Measured on a 1080p x265 + E-AC-3 5.1 + embedded-subtitles sample, replaying the
exact HLS request Firefox issues:

| | playlist | first segment |
|---|---|---|
| Flatpak server | `Premature close` error | never delivered |
| host node | valid | **281 KB in 0.52 s** |

## Troubleshooting

```bash
# Is the server up, and on which node?
systemctl --user status stremio-server.service     # ExecStart → …/install/stremio-server.sh
journalctl --user -u stremio-server.service -f     # a fallback prints an explicit warning

# Does the host's ffmpeg decode HEVC? (this is the check the wrapper makes)
ffmpeg -hide_banner -decoders | awk '$2 == "hevc"'

# Ask the server what it thinks of a file
curl -s 'http://127.0.0.1:11470/hlsv2/probe?mediaURL=<url-encoded>' | head -c 400
```

Known trap: `flatpak run` can leave an orphaned `server.js` behind when the unit
restarts. It keeps port 11470, the real service silently falls back to 11471,
and the UI then talks to a stale server. If playback misbehaves right after a
restart, check `ss -tlnp | grep 1147` and kill any leftover.

Two things worth remembering if this ever has to be re-diagnosed: the fork's own
code is not involved, and a Chromium-based kiosk would bypass the transcoder
entirely (`window.chrome` → MKV plays directly) — at the cost of the
Firefox-specific window-title detection the gamepad bridge relies on.
