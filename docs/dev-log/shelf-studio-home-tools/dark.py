# Dark-pixel fraction per frame in the jacket's area (screen 640..1010 x 300..760,
# in front of the row), so a black face or slab shows up as a spike.
import json
import sys
import glob
from PIL import Image
d = sys.argv[1]
meta = json.load(open(d + '/frames.json')); t0 = meta['pressAt'][0]
box = (640, 300, 1010, 760)
rows = []
for k, f in enumerate(sorted(glob.glob(d + '/f*.jpg'))):
    im = Image.open(f).convert('L'); sx = im.width / 1920
    c = im.crop(tuple(int(v * sx) for v in box)).resize((185, 230))
    px = list(c.getdata()); dark = sum(1 for v in px if v < 45) / len(px)
    rows.append((k, int((meta['frames'][k] - t0) * 1000), round(dark, 3)))
for r in rows: print(*r)
