# Phase 1 — Ce qui a été mesuré, avant toute modification

Mesuré le 2026-08-18 sur le clone `~/Downloads/GamecoreRenew` à `main` (7bf7a76),
et en lecture seule sur `/opt/GameCore`.

## 1.1 — La démonstration : **le défaut est confirmé**

`for_launch("mgba", …)` sur trois ROMs de trois consoles différentes :

```
Tetris (World).gb          -> hole {"x":420,"y":0,"w":1080,"h":1080}  source system  measure true
Pokemon Emerald (USA).gba  -> hole {"x":420,"y":0,"w":1080,"h":1080}  source system  measure true
Zelda Oracle (USA).gbc     -> hole {"x":420,"y":0,"w":1080,"h":1080}  source system  measure true
```

**Réponses identiques octet pour octet.** Le système ne distingue pas les
consoles d'un même pack. La prémisse du brief tient.

## 1.2 — Ce que l'alpha mesure réellement

Les six PNG livrés, trou dérivé de leur canal alpha :

| pack | trou mesuré | ratio | déclaré | accord |
|---|---|---|---|---|
| azahar | `900x1080+510+0` | **5:6** (0.833) | idem | ✅ |
| duckstation | `1440x968+240+52` | **180:121** (1.488) | idem | ✅ |
| gopher64 | `1440x1080+240+0` | **4:3** (1.333) | idem | ✅ |
| melonds | `720x1080+600+0` | **2:3** (0.667) | idem | ✅ |
| mgba | `1080x1080+420+0` | **1:1** (1.000) | idem | ✅ |
| pcsx2 | `1440x1080+240+0` | **4:3** (1.333) | idem | ✅ |

Les six s'accordent avec `config/overlays.json` : `test_bezels.py` fait son
travail, la dérive `gopher64` de l'historique est réparée dans le dépôt.

### Le trou de mgba n'est cut pour aucune des trois consoles

Le brief supposait un cadre taillé pour la Game Boy. La mesure dit autre chose,
et c'est pire :

| console | ratio | largeur d'une image de 1080 de haut | trou mgba |
|---|---|---|---|
| Game Boy / Color | 10:9 (1.111) | 1200 px | 1080 px |
| Game Boy Advance | 3:2 (1.500) | 1620 px | 1080 px |

**1:1 n'est ni l'un ni l'autre.** Le libellé de `config/overlays.json` l'avoue
d'ailleurs à demi-mot : `"label": "Game Boy Advance (Cadre Total)"` — un cadre
de compromis, pas un cadre de console.

### Les autres packs : un défaut latent

- **duckstation `180:121` (1.488)** ne correspond à aucune console qu'il émule.
  La PlayStation rend en 4:3 (1.333) ; à 968 de haut une image 4:3 fait 1291 px,
  pas 1440. Le trou est **149 px trop large**. Personne ne s'en plaint parce que
  le trou est *plus grand* que l'image — on voit des bandes noires dans le cadre
  plutôt qu'un cadre qui mord. À signaler, hors périmètre de ce travail.
- **azahar 5:6** et **melonds 2:3** sont cohérents : ce sont des écrans
  empilés (3DS 400x480, DS 256x384), pas des ratios de console simple. ✅
- **gopher64 4:3** et **pcsx2 4:3** sont justes. ✅

## 1.3 — Ce que les caches contiennent

`/opt/GameCore/config/bezel-holes.json` — six entrées, une par PNG, clé = chemin
absolu. Rien à redire : la clé est le chemin, la signature est `mtime:size`.

`/opt/GameCore/config/bezel-corrections.json` — **une seule entrée** :

```json
{ "mgba@1:1": { "h": 1080, "w": 1234, "x": 343, "y": 0 } }
```

**La clé est `mgba@1:1`.** Le ratio est celui du trou annoncé — 1:1 — donc
**une clé pour les trois consoles**, exactement comme le brief l'anticipait.

### L'hypothèse de 1.3 est vérifiée, et le résultat est chiffrable

La correction retenue fait **1234x1080**, soit un ratio de **1.143**. C'est la
signature d'une Game Boy ou d'une Game Boy Color (1200 px attendus à 1080 de
haut), pas d'une Game Boy Advance (1620 px).

| console jouée | largeur réelle | trou corrigé | écart |
|---|---|---|---|
| Game Boy / Color | 1200 px | 1234 px | −34 px (−17 px par côté) |
| **Game Boy Advance** | **1620 px** | **1234 px** | **+386 px (+193 px par côté)** |

**Le cadre mord 193 px de chaque côté d'un jeu GBA.** C'est le symptôme rapporté,
et il est maintenant mesuré et non déduit.

Et `for_launch()` porte `"measure": fixed is None` : la correction existant,
`measure` vaut **false** pour les trois consoles. **La boîte ne remesurera plus
jamais mgba.** La première console mesurée a verrouillé la correction pour les
trois, définitivement. Hypothèse confirmée.

### L'état réel de la boîte, qui n'était pas dans le brief

`/opt/GameCore/assets/overlays/` ne contient plus que **`azahar.png` et
`melonds.png`**. Les quatre autres PNG — dont `mgba.png` — ont disparu du disque,
alors que `bezel-holes.json` les a encore en cache et que `config/overlays.json`
les déclare toujours.

Conséquence, simulée avec les chemins de la boîte :

```
Tetris (World).gb          -> source "declared"  asset null  hole {"x":343,"y":0,"w":1234,"h":1080}
Pokemon Emerald (USA).gba  -> source "declared"  asset null  hole {"x":343,"y":0,"w":1234,"h":1080}
```

C'est le cas que `describe()` documente en toutes lettres : `declared` sans
asset, **des bandes noires que personne n'a demandées**. La boîte est aujourd'hui
dans cet état pour mgba, gopher64, duckstation et pcsx2.

Et pour dolphin : `source "none"`, rien de dessiné — correct.

## 1.4 — Les packs multi-consoles (relevé refait, `config/systems.json`)

13 systèmes. Le relevé du brief tient :

- **`mgba` : 3 consoles** — GBA, GBC, GB
- **`dolphin` : 2 consoles** — GameCube, Wii
- 10 packs en déclarent **une seule**
- **`shadps4` en déclare zéro** : `"libretroSystems": []`, et `"extensions": []`
  avec. `rpcs3` a aussi `"extensions": []` mais déclare bien sa console.
  Le trou de catalogue est donc **`shadps4`**, et il est double.

### La correspondance console → extension est bien implicite, et bien fragile

```
mgba     libretroSystems [GBA, GBC, GB]      extensions [*.gba, *.gbc, *.gb, *.zip]
dolphin  libretroSystems [GameCube, Wii]     extensions [*.iso,*.gcm,*.rvz,*.wbfs,*.wad,*.zip]
```

L'ordre coïncide **pour mgba seulement**, et par accident. Pour dolphin il ne
veut rien dire : 6 extensions pour 2 consoles, `.iso` et `.zip` servent les deux,
`.gcm`/`.rvz` sont GameCube, `.wbfs`/`.wad` sont Wii. **Aucune règle d'ordre ne
peut produire ça.** La correspondance doit être écrite, pas déduite.

## Ma lecture : chaîne de causalité **confirmée**

Un PNG par pack → un trou par pack → un ratio par pack → **une clé de cache par
pack**, alors que le pack sert trois consoles de ratios différents. La première
console jouée fixe la correction et `measure: false` la gèle. Mesuré à chaque
maillon, pas déduit.

Trois choses ne collent pas avec le brief, et je les enchaîne quand même :

1. **Le trou de mgba n'est pas « taillé pour la Game Boy »** — il est en 1:1,
   faux pour les trois. Un niveau console rend le correctif *possible* ; il ne
   suffit pas, il faut aussi des PNG. Voir « ce que cette phase ne fait pas ».
2. **duckstation porte un défaut latent** (180:121 pour une console 4:3) qui n'a
   rien à voir avec le multi-console. Signalé, pas corrigé.
3. **Quatre PNG ont disparu de la boîte**, qui tombe donc en `declared` — des
   bandes noires. Ça change la procédure de migration : il y a un ménage à faire
   en plus du renommage.
