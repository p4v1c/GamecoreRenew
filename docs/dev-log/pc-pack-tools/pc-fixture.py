"""Fake data root + Lutris home for devserve screenshots of the PC system.

    python3 pc-fixture.py <repo> <data root> <fake home>

Then run devserve with HOME=<fake home> GAMECORE_DATA=<data root>; the lutris
pack's sync writes the stubs and covers from the fake pga.db.
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

repo, data, home = map(Path, sys.argv[1:4])
shutil.rmtree(data, ignore_errors=True); shutil.rmtree(home, ignore_errors=True)
(data / "config").mkdir(parents=True)
dist = json.loads((repo / "install/generated/systems.json.dist").read_text())
keep = [s for s in dist if s["id"] in ("lutris", "snes9x", "duckstation", "gba")]
(data / "config/systems.json").write_text(json.dumps(keep, indent=2))
(data / "config/apps.json").write_text("[]")
shutil.copytree(repo / "config/themes", data / "config/themes")
for sid, names in {"snes9x": ["Super Mario World.sfc", "Chrono Trigger.sfc"],
                   "gba": ["Metroid Fusion.gba"], "duckstation": ["Vagrant Story.cue"]}.items():
    d = data / "emu" / sid; d.mkdir(parents=True)
    for n in names: (d / n).write_bytes(b"")
(data / "emu/lutris").mkdir(parents=True)

games = [(1, "Celeste", "celeste", "gog", (66, 32, 92), (234, 87, 133)),
         (2, "Hades", "hades", "epic", (40, 10, 10), (214, 74, 38)),
         (3, "Hollow Knight", "hollow-knight", "gog", (12, 18, 34), (180, 196, 220)),
         (4, "Disco Elysium", "disco-elysium", "gog", (24, 52, 60), (232, 190, 92)),
         (5, "Stardew Valley", "stardew-valley", "gog", (40, 96, 52), (246, 210, 120)),
         (6, "Half-Life 2", "half-life-2", "", (36, 36, 40), (238, 130, 30))]
lutris = home / ".var/app/net.lutris.Lutris/data/lutris"
(lutris / "coverart").mkdir(parents=True)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
except OSError:
    font = ImageFont.load_default()
for gid, name, slug, svc, bg, fg in games:
    im = Image.new("RGB", (528, 704), bg)
    dr = ImageDraw.Draw(im)
    for y in range(704):
        k = y / 704
        dr.line([(0, y), (528, y)], fill=tuple(int(b * (1 - k) + f * k * 0.5) for b, f in zip(bg, fg)))
    dr.ellipse([114, 180, 414, 480], outline=fg, width=10)
    words, lines = name.split(), []
    for w in words:
        if lines and len(lines[-1] + " " + w) < 13: lines[-1] += " " + w
        else: lines.append(w)
    for i, line in enumerate(lines):
        dr.text((264, 560 + i * 56), line.upper(), fill=fg, font=font, anchor="mm")
    im.save(lutris / "coverart" / f"{slug}.jpg", quality=88)
con = sqlite3.connect(lutris / "pga.db")
con.executescript("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, runner TEXT,"
                  " service TEXT, installed INTEGER);"
                  "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT);"
                  "CREATE TABLE games_categories (game_id INTEGER, category_id INTEGER);")
con.executemany("INSERT INTO games VALUES (?, ?, ?, 'wine', ?, 1)",
                [(g[0], g[1], g[2], g[3]) for g in games])
con.commit(); con.close()
print("fixture ready")
