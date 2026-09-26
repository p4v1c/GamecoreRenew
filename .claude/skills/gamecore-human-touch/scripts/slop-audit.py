"""Count AI-look tells per UI area (see ../SKILL.md). -v prints samples."""
import collections
import re
import subprocess
import sys

files=[f for f in subprocess.run(['git','ls-files','config/themes','frontend/src','electron/boot','frontend/index.html'],capture_output=True,text=True).stdout.split()
       if re.search(r'\.(css|js|jsx|ts|tsx|html)$',f) and '.test.' not in f and '/test/' not in f]
def area(f):
    for t in ('orbit','shelf','summer','_skeleton'):
        if f'config/themes/{t}/' in f: return t
    return 'default-ui'
EMOJI=re.compile('[\U00002300-\U000023FF\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF\U0001F000-\U0001F2FF]')
PAD=set('✕○△□')
# Pad-hint strings are split on ' · ' by PadHints and drawn with spacing: not meta.
PADHINT=re.compile(r'[✕○△□↑↓←→]|\b(L[123]|R[123]|PS|Options)\b')
checks={
 'font-family':re.compile(r'font-family\s*:\s*([^;"}]+)',re.I),
 'uppercase':re.compile(r'text-transform\s*:\s*uppercase|textTransform:\s*[\'"]uppercase',re.I),
 'letter-spacing>=2px':re.compile(r'letter-spacing\s*:\s*(0\.[2-9]\d*em|[2-9]px|1\.\d+px)|letterSpacing:\s*[\'"]?(0\.[2-9]|[2-9])',re.I),
 'gradient':re.compile(r'(linear|radial|conic)-gradient',re.I),
 'glow/colored shadow':re.compile(r'(box|text)-shadow\s*:[^;]*(rgba?\((?!0,\s*0,\s*0)[^)]*\)|#[0-9a-f]{3,8})[^;]*|drop-shadow\(',re.I),
 'backdrop-blur':re.compile(r'backdrop-filter\s*:\s*blur|backdropFilter',re.I),
 'purple/violet':re.compile(r'#(8b5cf6|7c3aed|a78bfa|a855f7|9333ea|6366f1|818cf8|c084fc)|violet|purple',re.I),
 'arrow in text':re.compile(r'[A-Za-z]\s*(→|->)\s*[\'"<`]'),
 'middle-dot meta':re.compile(r'[\'"`>][^\'"`<\n]*\S · \S[^\'"`<\n]*[\'"`<]'),
 'em dash in UI text':re.compile(r'[\'">`][^\'"<`\n]{3,}\s—\s[^\'"<`\n]{3,}[\'"<`]'),
}
cnt=collections.defaultdict(collections.Counter); fonts=collections.defaultdict(collections.Counter); samples=collections.defaultdict(list)
for f in files:
    a=area(f); txt=open(f,encoding='utf-8',errors='replace').read()
    # strip comments for css/js roughly
    code=re.sub(r'/\*.*?\*/','',txt,flags=re.S); code=re.sub(r'(^|\s)//[^\n]*','',code)
    for k,rx in checks.items():
        for m in rx.finditer(code):
            if k=='font-family': fonts[a][m.group(1).strip()[:60]]+=1; continue
            if k=='middle-dot meta' and PADHINT.search(m.group(0)): continue
            cnt[a][k]+=1
            if len(samples[(a,k)])<3: samples[(a,k)].append(f"{f}: {m.group(0)[:90]}")
    for m in EMOJI.finditer(code):
        if m.group(0) in PAD: continue
        cnt[a]['emoji']+=1
        if len(samples[(a,'emoji')])<6: samples[(a,'emoji')].append(f"{f}: {code[max(0,m.start()-30):m.end()+30]!r}"[:120])
for a in sorted(cnt):
    print(f"\n### {a}"); 
    for k,v in cnt[a].most_common(): print(f"  {v:4} {k}")
    print("  fonts:", dict(fonts[a].most_common(6)))
if '-v' in sys.argv:
    for (a,k),s in samples.items():
        print(f"\n[{a}/{k}]"); [print("   ",x) for x in s]
