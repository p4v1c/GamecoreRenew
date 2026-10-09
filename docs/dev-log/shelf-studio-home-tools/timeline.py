# Compact per-frame timeline of the jacket holders from samples.json.
import json, sys
s = json.load(open(sys.argv[1] + '/samples.json'))
prev = None
for x in s:
    line = ' | '.join(f"{h.get('phase','j')}{'T' if h.get('tucked')=='1' else ''}{'h' if h['vis']=='hidden' else ''} turn={h['turn']} mv={h['move']} op={h['op']} {(h['key'] or '')[:14]} img={h['imgs']}" for h in x['holds'])
    line = f"gaps={x['gaps']} " + line
    if line != prev:
        print(f"{x['t']:5d} {line}")
    prev = line
