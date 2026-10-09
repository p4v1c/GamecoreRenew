# Per-jacket continuity check from samples.json.
# A cut = a jacket that appears or disappears while NOT at its row pose
#         (edge-on: |turn| ~ 90, travelled to depth z ~ dive).
# A jump = a change of turn > 40 deg or of depth > 160 px between two samples.
import json
import sys
s = json.load(open(sys.argv[1] + '/samples.json'))
DIVE = -425
# Sampled every ~40 ms headless, so a jacket created at p = 1 may already have
# moved a step when first seen: 'near the row' = edge-on and at least 60 % deep.
def rowpose(h): return h and abs(abs(h['turn']) - 90) <= 8 and h['move'][2] <= DIVE * 0.6
prevt = None; prev = {}; cuts = []; jumps = []; seen = set(); maxturn = {}
for x in s:
    now = {h['key']: h for h in x['holds'] if h['key']}
    for k, h in now.items():
        seen.add(k)
        if k not in prev and x is not s[0] and not rowpose(h): cuts.append((x['t'], 'appear', k, h['turn'], h['move']))
        if k in prev:
            p = prev[k]
            f = max(1.0, (x['t'] - prevt) / 16.7)       # how many 60 fps frames this sample spans
            if abs(h['turn'] - p['turn']) / f > 35 or abs(h['move'][2] - p['move'][2]) / f > 120:
                jumps.append((x['t'], k, p['turn'], h['turn'], p['move'][2], h['move'][2]))
        maxturn[k] = min(maxturn.get(k, 99), abs(h['turn']))
    for k, p in prev.items():
        if k not in now and not rowpose(p): cuts.append((x['t'], 'vanish', k, p['turn'], p['move']))
    prev = now; prevt = x['t']
print('jackets seen:', len(seen))
print('came out at least part way (turn < 80):', sum(1 for k in maxturn if maxturn[k] < 80), 'of', len(maxturn))
print('cuts:', len(cuts)); [print('  ', c) for c in cuts[:10]]
print('jumps:', len(jumps)); [print('  ', j) for j in jumps[:10]]
