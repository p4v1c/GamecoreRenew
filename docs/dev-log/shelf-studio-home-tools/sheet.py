# Contact sheet of screencast frames (cropped to the stage), with times relative to the first press.
import json
import sys
import glob
from PIL import Image, ImageDraw
d = sys.argv[1]; start = int(sys.argv[2]) if len(sys.argv) > 2 else 0; n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
meta = json.load(open(d + '/frames.json'))
t0 = meta['pressAt'][0] if meta['pressAt'] else meta['frames'][0]
files = sorted(glob.glob(d + '/f*.jpg'))[start:start + n]
crop = (300, 200, 1400, 900)          # the stage, without the card
W, H = 330, 210; cols = 8
rows = (len(files) + cols - 1) // cols
sheet = Image.new('RGB', (cols * W, rows * (H + 18)), 'white')
for i, f in enumerate(files):
    k = start + i
    im = Image.open(f).convert('RGB')
    sx = im.width / 1920
    im = im.crop(tuple(int(c * sx) for c in crop)).resize((W, H))
    x, y = (i % cols) * W, (i // cols) * (H + 18)
    sheet.paste(im, (x, y + 18))
    ImageDraw.Draw(sheet).text((x + 4, y + 3), f"#{k} {int((meta['frames'][k] - t0) * 1000)}ms", fill='black')
sheet.save(d + f'/sheet-{start}.png')
print(d + f'/sheet-{start}.png', len(files))
