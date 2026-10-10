"""Dev only: stand-in game clips and screenshots in a dev media cache.

The dev box has no ScreenScraper account, so the CRT standby is tested on
clips made here with ffmpeg, filed exactly the way gamemedia files a real
download: `<data>/<media>/<system>/<game key>/<slug>.<ext>` plus `game.json`.
WebM/VP9, because Playwright's Chromium has no H.264. Every picture carries
the words "stand-in clip" so a screenshot cannot pass for a real video.

    GAMECORE_DATA=$SCRATCH/gcdata PYTHONPATH=$PWD python3 make-standins.py [frame.png]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.services.gamemedia import gamemedia as gm

FRAME = sys.argv[1] if len(sys.argv) > 1 else None
LABEL = "drawtext=text='stand-in clip':x=16:y=h-40:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.5"
CLIPS = [  # (system, rom, seconds, ffmpeg input)
    ("snes9x", "Chrono Trigger (USA).sfc", 12, ["-f", "lavfi", "-i", "mandelbrot=s=640x480:r=30"]),
    ("azahar", "Mario Kart 7 (Europe).3ds", 14, ["-f", "lavfi", "-i", "testsrc2=s=640x480:r=30"]),
    ("duckstation", "Crash Bandicoot (Europe).chd", 10,
     ["-f", "lavfi", "-i", "life=s=640x480:r=30:mold=10:ratio=0.1:death_color=#C83232:life_color=#F0A020"]),
    ("gba", "Advance Wars (Europe).gba", 16,
     ["-f", "lavfi", "-i", "gradients=s=640x480:r=30:c0=#0a6040:c1=#30e0b0:speed=0.03"]),
]
STILLS = [  # (system, rom, ffmpeg input)
    ("snes9x", "Super Mario World (Europe).sfc", ["-f", "lavfi", "-i", "smptehdbars=s=640x480"]),
    ("nes", "The Legend of Zelda (Europe).nes", ["-f", "lavfi", "-i", "gradients=s=640x480:c0=#1d7a3a:c1=#e0c070"]),
    ("megadrive", "Sonic the Hedgehog (Europe).md", ["-f", "lavfi", "-i", "gradients=s=640x480:c0=#1050d0:c1=#60c0ff"]),
    ("gba", "Metroid Fusion (Europe).gba", ["-f", "lavfi", "-i", "gradients=s=640x480:c0=#401060:c1=#f04040"]),
]
if FRAME:  # the validated scene's TV picture, panned, as one more clip
    CLIPS[0] = ("snes9x", "Chrono Trigger (USA).sfc", 12,
                ["-loop", "1", "-i", FRAME, "-vf", "scale=1280:960,crop=640:480:x='t*40':y=240"])


def ffmpeg(args: list[str], out: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, str(out)], check=True)


def file_media(system: str, rom: str, slug: str, path: Path) -> None:
    d = gm.entry_dir(system, rom)
    d.mkdir(parents=True, exist_ok=True)
    manifest = gm.load_cached(system, rom) or {"system": system, "filename": rom, "found": True,
                                                "lang": gm.LANG_PREF[0], "media": {}, "meta": {}}
    target = d / f"{slug}{path.suffix}"
    path.replace(target)
    kind = "video" if slug.startswith("video") else "image"
    manifest["media"][slug] = {"file": target.name, "bytes": target.stat().st_size,
                               "url": f"https://example.invalid/{slug}", "category": kind, "kind": kind}
    gm.write_json(d / gm.MANIFEST, manifest)
    print(f"{system}/{rom}: {slug} {target.stat().st_size // 1024} KB")


with tempfile.TemporaryDirectory() as tmp:
    for system, rom, secs, src in CLIPS:
        out = Path(tmp) / "clip.webm"
        vf = src[src.index("-vf") + 1] + "," + LABEL if "-vf" in src else LABEL
        args = [a for i, a in enumerate(src) if a != "-vf" and (i == 0 or src[i - 1] != "-vf")]
        ffmpeg([*args, "-t", str(secs), "-vf", vf, "-c:v", "libvpx-vp9", "-b:v", "900k",
                "-deadline", "realtime", "-cpu-used", "8", "-an"], out)
        file_media(system, rom, "video-normalized", out)
    for system, rom, src in STILLS:
        out = Path(tmp) / "still.png"
        ffmpeg([*src, "-frames:v", "1", "-vf", LABEL.replace("clip", "screenshot")], out)
        file_media(system, rom, "screenshot-gameplay", out)
