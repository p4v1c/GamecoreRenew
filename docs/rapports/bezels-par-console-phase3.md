# Phase 3 — Ce que tu vérifies sur la boîte, et comment tu la migres

Je ne peux pas voir un bezel. Je peux prouver qu'il est résolu pour la bonne
console, que son trou vient du bon alpha et que les clés de cache se
distinguent — les tests le font. **Le reste se juge à l'œil, à trois mètres**, et
c'est ce document.

## À quoi ressemble un bezel juste

C'est la seule chose à regarder, et elle n'est pas évidente si personne ne la
dit :

> Le cadre décoratif **épouse les bandes noires**. Il ne mord pas sur l'image —
> aucun bout de décor par-dessus le jeu — et il ne laisse **aucune bande noire
> entre l'image et le cadre**.

Les deux défauts se voient au même endroit, la frontière image/décor, et ils
sont opposés : trop de cadre mange le jeu, trop peu laisse du noir apparaître.

---

# 1. La non-régression — à faire en premier

**C'est le test le plus important, et le seul qui puisse invalider toute la
livraison.** Ta boîte n'a que des bezels système. Aucun d'eux ne doit bouger.

Sans lancer un seul jeu :

```bash
cd /opt/GameCore && .venv/bin/python - <<'EOF'
import sys, json; sys.path.insert(0, '.')
from backend.services import bezels
for sid in ("azahar", "melonds", "duckstation", "pcsx2", "gopher64", "mgba"):
    o = bezels.for_launch(sid, "Un Jeu Quelconque (USA).iso")
    print(f"{sid:12s} source={o['source']:9s} console={o['console']} hole={o['hole']}")
EOF
```

Note ces six lignes **avant** la mise à jour, et recompare-les après. Pour les
cinq packs mono-console, `console` doit valoir `None` et tout le reste doit être
**identique au caractère près**. Si une seule de ces lignes bouge, arrête-toi et
dis-le moi : c'est une régression, pas un effet de bord.

Puis, à l'œil : lance un jeu **PS1**, un jeu **PS2**, un jeu **3DS**, un jeu
**DS**. Chacun doit être exactement comme avant.

Cas particulier à ne pas confondre avec une régression : `duckstation`,
`gopher64`, `pcsx2` et `mgba` n'ont **plus de PNG sur la boîte aujourd'hui**
(`/opt/GameCore/assets/overlays/` ne contient que `azahar.png` et
`melonds.png`). Ils n'affichent donc rien, ni avant ni après. C'est l'état
actuel, pas une conséquence de ce travail.

---

# 2. Le cas qui a motivé le travail — mgba

## 2.1 Sans rien déposer

Après la mise à jour, **avant** de fournir le moindre PNG :

```bash
cd /opt/GameCore && .venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, '.')
from backend.services import bezels
for rom in ("Tetris (World).gb", "Pokemon Emerald (USA).gba"):
    o = bezels.for_launch("mgba", rom)
    print(f"{rom:28s} console={o['console']!r:7s} hole={o['hole']} measure={o['measure']}")
EOF
```

Attendu : `console='gb'` et `console='gba'` — **deux réponses différentes**,
alors qu'avant elles étaient identiques octet pour octet. Et `measure=True` pour
les deux : l'ancienne correction `mgba@1:1` n'est plus atteignable, donc la boîte
va réapprendre, **une fois par console**.

## 2.2 En jouant

Lance un jeu **Game Boy**, quitte, puis un jeu **Game Boy Advance**, quitte.
Puis relis le cache :

```bash
cat /opt/GameCore/config/bezel-corrections.json
```

Attendu, **deux entrées distinctes** :

```json
{
  "mgba/gb@1:1":  { "x": 360, "y": 0, "w": 1200, "h": 1080 },
  "mgba/gba@1:1": { "x": 150, "y": 0, "w": 1620, "h": 1080 }
}
```

Les chiffres exacts varieront de quelques pixels — c'est une mesure d'écran.
Ce qui compte, ce sont **deux clés** et deux largeurs nettement différentes :
autour de 1200 pour la Game Boy (10:9), autour de 1620 pour la GBA (3:2).

L'ancienne ligne `mgba@1:1` est toujours là et **c'est voulu** : elle est morte,
plus rien ne peut la lire, et la laisser est ce qui permet de revenir en arrière
proprement. Tu peux la supprimer plus tard, pas maintenant.

> ⚠️ **Ce que ça corrige et ce que ça ne corrige pas.** Le **trou** devient juste
> pour chaque console — le jeu est entièrement visible dans les deux cas. Le
> **décor**, lui, reste celui du PNG unique `mgba.png`, taillé en 1:1, qui ne
> correspond ni à la Game Boy ni à la GBA. Pour que le cadre épouse vraiment
> l'image il faut un PNG par console : c'est l'étape 2.3, et c'est à toi de
> fournir les images.

## 2.3 En déposant un bezel par console

La convention de nommage, dans `/opt/GameCore/assets/overlays/` :

| fichier | pour |
|---|---|
| `mgba.png` | tout mGBA — le repli, comme aujourd'hui |
| `mgba.gb.png` | Game Boy (10:9) |
| `mgba.gbc.png` | Game Boy Color (10:9) |
| `mgba.gba.png` | Game Boy Advance (3:2) |
| `dolphin.gamecube.png` | GameCube |
| `dolphin.wii.png` | Wii |

`<système>.<console>.png`, à côté du bezel système. Les ids de console sont ceux
que le pack déclare, et tu peux les lire :

```bash
/opt/GameCore/.venv/bin/python -c "
import json
for s in json.load(open('/opt/GameCore/config/systems.json')):
    if s.get('consoles'): print(s['id'], [c['id'] for c in s['consoles']])"
```

Dépose un fichier, puis vérifie qu'il est pris **sans lancer de jeu** :

```bash
cd /opt/GameCore && .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.services import bezels
print(bezels.for_launch('mgba','Pokemon Emerald (USA).gba'))"
```

Attendu : `source='console'` et `asset='/assets/overlays/mgba.gba.png'`.

⚠️ **Un PNG déposé à la main n'est pas validé.** La validation (image sans zone
transparente refusée) est sur la route d'envoi, pas sur le système de fichiers.
Si tu copies un fichier avec `cp`, personne ne te dira qu'il est opaque. Le test
ci-dessus te le dira indirectement : `source` restera `system` ou `none` si le
trou est illisible.

## 2.4 Refuser une image sans trou

Par la route, cette fois :

```bash
curl -k -X POST https://localhost:8443/api/overlays/mgba/consoles/gba \
     -F "file=@une-image-sans-transparence.png"
```

Attendu : **422**, avec un message qui dit qu'un bezel a besoin d'une zone
transparente. Et le fichier déjà en place, s'il y en avait un, **n'a pas été
touché**.

---

# 3. Le second pack multi-consoles — dolphin

Rien ne devrait déborder : GameCube et Wii partagent le 4:3. **Ce n'est pas un
correctif, c'est une capacité** — deux bezels pour deux machines différentes.

```bash
cd /opt/GameCore && .venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, '.')
from backend.services import bezels
for rom in ("Zelda Wind Waker (USA).gcm", "Wii Sports (USA).wbfs",
            "Mario Kart (USA).iso"):
    print(f"{rom:30s} console={bezels.for_launch('dolphin', rom)['console']!r}")
EOF
```

Attendu : `'gamecube'`, `'wii'`, puis **`None`** pour le `.iso`.

**Ce `None` est voulu, pas un oubli.** `.iso`, `.rvz` et `.zip` peuvent contenir
l'une ou l'autre machine — `.rvz` est le conteneur propre à Dolphin, et le
scraper a déjà payé cette leçon : tous les jeux Dolphin étaient cherchés comme
des jeux GameCube et Mario Kart Wii tombait sur Double Dash. Une extension
ambiguë reste au niveau système plutôt que de deviner. En pratique, la plupart
de tes dumps Dolphin sont probablement des `.iso` ou des `.rvz`, donc **la
plupart de tes jeux Dolphin resteront au niveau système** — c'est normal.

---

# 4. Chaque niveau de la cascade

Six états, dans cet ordre : **off → jeu → console → système → déclaré → rien**.

| ce que tu fais | ce que tu dois voir |
|---|---|
| un jeu GBA, avec `mgba.gba.png` et `mgba.png` | le bezel **console** |
| le même, avec en plus `mgba/Pokemon Emerald (USA).png` | le bezel **du jeu** |
| un jeu GB, avec seulement `mgba.png` | le bezel **système** |
| overlay éteint sur ce jeu (écran des options) | **rien**, même s'il a un bezel console |
| un système sans aucun PNG | **rien** — et surtout pas de bandes noires |

La dernière ligne est celle à surveiller. Des bandes noires sur un jeu qui
remplissait l'écran correctement, c'est le défaut que la cascade existe pour
éviter.

Pour vérifier « éteint » sans manette :

```bash
cd /opt/GameCore && .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.services import bezels
bezels.set_preference('mgba','Pokemon Emerald (USA).gba','off')
print(bezels.for_launch('mgba','Pokemon Emerald (USA).gba'))
bezels.set_preference('mgba','Pokemon Emerald (USA).gba', None)   # on remet"
```

Attendu : `source='off'`, `asset=None`, `hole=None`. **La seconde ligne remet le
réglage à l'automatique** — ne l'oublie pas.

---

# 5. La migration de la boîte

`assets/overlays/` et `config/` sont exclus du rsync de l'OTA. **La release ne
touchera donc ni tes images ni tes fiches.** Voici ce qui se passe quand même,
et ce qui ne se passe pas.

## Ce qui arrive tout seul

`update/linux.sh` lance déjà `merge_file()` sur `config/systems.json` après le
rsync — c'est le mécanisme qui avait été mis en place pour réparer le lanceur
N64. J'ai accroché `consoles` au même endroit, avec la même règle prudente :
**rempli seulement si la boîte n'en a aucun**, jamais écrasé.

Donc `config/systems.json` gagnera `consoles` pour `mgba` et `dolphin` **sans
que tu tapes quoi que ce soit**. Vérifié à blanc sur une copie de ta vraie
`systems.json` :

```
dolphin: consoles filled in (gamecube, wii)
mgba: consoles filled in (gba, gbc, gb)
```

## Ce qui n'arrive pas tout seul

Les **images**. Le nouveau code rend possible un bezel par console ; il n'en
fournit aucun. Si tu veux que le cadre de la GBA épouse une image 3:2, il faut
que tu déposes `mgba.gba.png`.

## 5.1 La sauvegarde — d'abord, toujours

Quelques dizaines de kilo-octets. Sans elle il n'y a pas de retour.

```bash
B=~/sauvegarde-bezels-$(date +%F-%H%M)
mkdir -p "$B"
cp -a /opt/GameCore/assets/overlays "$B"/overlays
cp -a /opt/GameCore/config/systems.json "$B"/
cp -a /opt/GameCore/config/overlays.json "$B"/
cp -a /opt/GameCore/config/bezel-holes.json "$B"/ 2>/dev/null
cp -a /opt/GameCore/config/bezel-corrections.json "$B"/ 2>/dev/null
cp -a /opt/GameCore/config/bezel-choices.json "$B"/ 2>/dev/null
echo "$B" > ~/.derniere-sauvegarde-bezels
ls -la "$B"
```

(`bezel-choices.json` n'existe pas aujourd'hui sur ta boîte — le `2>/dev/null`
est là pour ça, ce n'est pas une erreur.)

## 5.2 Ce qu'il faut faire — une commande par ligne

**Rien n'est obligatoire.** La boîte fonctionne sans migrer ; voir 5.5.

```bash
# a) Voir ce que la boîte a compris des consoles (rien à taper si c'est bon).
/opt/GameCore/.venv/bin/python -c "
import json
for s in json.load(open('/opt/GameCore/config/systems.json')):
    if s.get('consoles'): print(s['id'], [c['id'] for c in s['consoles']])"

# b) Si (a) n'affiche rien, la fusion de l'OTA n'a pas tourné. La relancer :
cd /opt/GameCore && .venv/bin/python - <<'EOF'
import sys; from pathlib import Path
root = Path("/opt/GameCore"); sys.path.insert(0, str(root))
from backend.services.catalog import load_catalog
from backend.services.catalog.merge import merge_file
for n in merge_file(root/"config"/"systems.json",
                    load_catalog(root/"catalog", root/"config"/"catalog.d"),
                    root):
    print(" ", n)
EOF

# c) Déposer un bezel par console — TES images, que je ne peux pas fabriquer.
#    Le nom est <système>.<console>.png, à côté du bezel système.
cp /chemin/vers/ton-cadre-gba.png /opt/GameCore/assets/overlays/mgba.gba.png
cp /chemin/vers/ton-cadre-gb.png  /opt/GameCore/assets/overlays/mgba.gb.png

# d) OPTIONNEL, et seulement après avoir vérifié le point 2.2 : effacer
#    l'ancienne correction devenue morte. Elle ne gêne pas, elle est juste
#    illisible désormais. Ne fais ça que si tout le reste marche.
/opt/GameCore/.venv/bin/python - <<'EOF'
import json
from pathlib import Path
p = Path("/opt/GameCore/config/bezel-corrections.json")
d = json.loads(p.read_text())
mortes = [k for k in d if "/" not in k and k.split("@")[0] in ("mgba", "dolphin")]
for k in mortes:
    print("supprimée :", k, d.pop(k))
p.write_text(json.dumps(d, indent=2, sort_keys=True))
EOF
```

**Il n'y a rien à renommer et rien à vider.** C'était l'hypothèse de départ ;
elle s'est révélée fausse à la mesure, et c'est une bonne nouvelle : le cache de
trous est indexé par chemin de fichier, donc un PNG ajouté est mesuré tout seul,
et les corrections changent de clé toutes seules.

## 5.3 Vérifier que ça a pris — avant de lancer un jeu

```bash
cd /opt/GameCore && .venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, '.')
from backend.services import bezels, consoles
print("consoles déclarées mgba :", [c["id"] for c in consoles.declared("mgba")])
for rom in ("Tetris (World).gb", "Pokemon Emerald (USA).gba"):
    o = bezels.for_launch("mgba", rom)
    print(f"  {rom:28s} console={o['console']!r:7s} source={o['source']:8s} asset={o['asset']}")
print("pcsx2 (mono-console) :", bezels.for_launch("pcsx2", "God of War.iso")["console"])
EOF
```

Trois choses à lire :

1. `consoles déclarées mgba : ['gba', 'gbc', 'gb']` — la fusion a marché ;
2. les deux ROMs donnent **deux `console` différents** — le niveau existe ;
3. `pcsx2 (mono-console) : None` — rien n'a bougé pour les onze autres packs.

## 5.4 Le chemin de retour — écrit avant d'en avoir besoin

```bash
B=$(cat ~/.derniere-sauvegarde-bezels)
rm -rf /opt/GameCore/assets/overlays
cp -a "$B"/overlays /opt/GameCore/assets/overlays
cp -a "$B"/systems.json           /opt/GameCore/config/systems.json
cp -a "$B"/overlays.json          /opt/GameCore/config/overlays.json
cp -a "$B"/bezel-holes.json       /opt/GameCore/config/ 2>/dev/null
cp -a "$B"/bezel-corrections.json /opt/GameCore/config/ 2>/dev/null
cp -a "$B"/bezel-choices.json     /opt/GameCore/config/ 2>/dev/null
```

Puis relis le bloc de non-régression du point 1 : les six lignes doivent être
celles d'avant.

Si tu veux revenir aussi sur le **code**, c'est un `git revert` de la branche :
l'ancienne clé `mgba@1:1` redevient lisible, et comme elle n'a jamais été
supprimée (sauf si tu as fait le 5.2.d), la boîte retrouve exactement son
comportement d'origine.

## 5.5 Ce que tu perds si tu ne fais rien

**Rien ne casse.** Le nouveau code fonctionne sur une boîte non migrée. Une
migration obligatoire pour que la boîte reste utilisable serait un défaut, pas
une étape.

Précisément :

| tu ne fais rien | ce que ça donne |
|---|---|
| tu n'appliques pas l'OTA | tout comme aujourd'hui |
| tu appliques l'OTA, tu ne déposes aucun PNG | mgba **réapprend sa correction par console** : le trou devient juste pour la GB et pour la GBA séparément. Le décor reste le cadre 1:1, donc il ne colle toujours pas — mais le jeu est entièrement visible |
| tu ne déposes pas de bezel dolphin | dolphin reste au niveau système, comme aujourd'hui |
| tu n'effaces pas `mgba@1:1` | rien : la ligne est morte, plus rien ne la lit |

La seule chose que tu perds durablement en ne faisant rien, c'est **le cadre qui
épouse l'image** — et ça, ça demande des images que je n'ai pas.
