# Les overlays par console — rapport

Branche **`feat/bezels-par-console`**, poussée, **non fusionnée**, pas de PR.
Base : `main` à `7bf7a76`.

---

# Décisions prises seul

Tu n'étais pas là ; j'ai tranché en préférant à chaque fois l'option la plus
réversible. Voici les six, avec leur raison et **comment les défaire**.

### 1. Les consoles sont déclarées dans `roms.consoles`, pas dans `libretroSystems`

**Raison — et elle est mesurée, pas supposée.** `melonds` déclare **deux**
entrées libretro (`Nintendo - Nintendo DS` et `Nintendo - Nintendo DS (Download
Play)`) pour **une seule machine**. `libretroSystems` n'est donc pas une liste de
consoles, c'est une liste de noms dans la base libretro. S'en servir comme clé
aurait donné une console fantôme à melonDS. Et `shadps4` en déclare zéro tout en
ayant un `mediaAlias` : la liste libretro est incomplète en plus d'être fausse.

J'ai aussi regardé `scraper.mediaAlias`, qui lui est bien une entrée par console.
Écarté quand même : c'est le vocabulaire de ScreenScraper (`"nintendo 64"`,
`"xbox 360"`, espaces compris), donc un nom que quelqu'un d'autre peut renommer,
et il n'est pas utilisable dans un nom de fichier.

**Pour défaire :** supprimer le bloc `consoles` du schéma et des deux packs. Le
code retombe seul au niveau système — `consoles.declared()` renvoie `[]`.

### 2. `.iso`, `.rvz` et `.zip` ne sont rattachés à aucune console

**Raison.** Ils sont réellement ambigus. `.rvz` est le conteneur propre à
Dolphin et tient GameCube comme Wii ; le scraper a déjà payé cette leçon —
`gamemedia/registry.py` raconte que tous les jeux Dolphin étaient cherchés comme
des jeux GameCube et que Mario Kart Wii tombait discrètement sur Double Dash.
Le brief disait de ne pas inventer : je n'ai pas inventé.

Une extension ambiguë renvoie donc `None`, et le niveau console est simplement
sauté. **L'échec est visible** de deux façons : `check-catalog.py` refuse à la
construction qu'une extension soit revendiquée par deux consoles, et à
l'exécution `consoles.for_rom()` écrit une ligne de log avant de retomber.

**Conséquence à savoir :** la plupart de tes dumps Dolphin sont probablement des
`.iso` ou des `.rvz`, donc **la plupart de tes jeux Dolphin resteront au niveau
système**. C'est honnête, pas satisfaisant.

**Pour défaire :** ajouter `*.iso` sous une console dans `catalog/dolphin/pack.json`
— mais alors `check-catalog` refusera de le mettre sous les deux. La vraie
sortie serait de lire l'en-tête du disque (`gameid.identify()` sait déjà le
faire) ; je ne l'ai pas fait, c'est de l'I/O devant un jeu qui démarre.

### 3. La clé de correction porte la console — explicitement, pas par accident

Le brief notait l'élégance du cas : un PNG par console ⇒ des trous différents ⇒
des ratios différents ⇒ des clés différentes, naturellement. **C'est vrai et ça
ne suffit pas**, parce que ça ne vaut qu'une fois les PNG fournis. Tant qu'il n'y
en a qu'un, les trois consoles partagent un ratio — et c'est exactement l'état où
j'ai trouvé ta boîte.

Donc : `<system>/<console>@<ratio>` pour un pack qui déclare des consoles,
`<system>@<ratio>` pour les onze autres, **inchangé à l'octet près**.

**Pour défaire :** rendre `key_for()` à sa forme d'origine. Les anciennes entrées
sont toujours sur le disque, elles redeviennent lisibles immédiatement.

### 4. Les corrections déjà en cache sont **gardées mais rendues inatteignables**

Le brief demandait de trancher entre garder et jeter. J'ai fait ni l'un ni
l'autre exactement : `mgba@1:1` reste sur le disque, mais plus aucune clé
calculée ne peut la retrouver — un pack à consoles porte toujours un segment
console, `-` compris quand l'extension n'a rien dit.

**Raison.** Les garder revenait à appliquer à trois consoles une mesure faite sur
une seule, ce qui est le bug. Les effacer rendait le retour arrière impossible.
Les laisser mortes coûte un réapprentissage — deux lancements — et **ne détruit
rien**, ce qui est la propriété que je voulais.

**Pour défaire :** rien à faire, justement. `git revert` de la branche et
l'ancienne clé redevient lisible telle quelle.

### 5. Le nommage : `<système>.<console>.png`

`mgba.gba.png` à côté de `mgba.png`. Devinable sans documentation : le bezel
système est `mgba.png`, celui d'une console ajoute son nom. À côté du fichier
système plutôt que dans `assets/overlays/mgba/`, parce que ce répertoire est le
pack par jeu et qu'une archive Bezel Project décompressée dedans se retrouverait
à côté de fichiers qui ne sont pas des jeux.

Les ids de console interdisent le point (`^[a-z0-9][a-z0-9-]{0,31}$`), sinon
`mgba.gb.c.png` ne se relit plus.

**Pour défaire :** changer `bezels.console_png()`, une ligne. Et renommer les PNG
déjà déposés, s'il y en a.

### 6. Le dépôt passe par une route du cœur, et refuse une image opaque

`POST /api/overlays/<system>/consoles/<console>`. **Pas une extension du contrat
addon** : `api: 1` dit qu'un addon écrit dans son propre répertoire de données.
Ouvrir `assets/overlays/` aux addons pour une fonctionnalité l'ouvrirait à tous.
ROM Manager appelle, le cœur valide la console contre `roms.consoles` et décide
où poser. `docs/SECURITY.md` : `/api/*` répond 403 depuis le LAN, donc la route
est joignable depuis la boîte, pas depuis un téléphone.

**Décision annexe, celle dont je suis le moins sûr :** le refus d'une image sans
zone transparente s'applique **aussi à la route système existante**, pas
seulement à la nouvelle. Une image opaque est un rectangle peint sur tout le jeu,
quel que soit le niveau — mais c'est un changement de comportement sur un
point d'entrée qui existait. **En pratique ça rend le JPEG inutilisable** (un
JPEG ne peut pas porter d'alpha), ce qui est correct mais plus strict qu'avant.

**Pour défaire :** déplacer le bloc `hole is None` de `_receive_bezel()` dans la
seule route console.

---

# Phase 1 — l'état, en trois lignes

Le détail est dans [`bezels-par-console-phase1.md`](bezels-par-console-phase1.md),
écrit avant la phase 2 et non retouché depuis, sauf une correction signalée.

**1.1 — le défaut est démontré.** `for_launch("mgba", …)` renvoyait la même
réponse **octet pour octet** pour `.gb`, `.gbc` et `.gba`.

**Et c'était pire que ça.** Le trou de `mgba.png` mesure `1080x1080` — un carré
**1:1**, qui n'est ni la Game Boy (10:9) ni la GBA (3:2). Le libellé de
`config/overlays.json` l'avouait à demi-mot : `"Game Boy Advance (Cadre Total)"`.

**Le cache de ta boîte portait la preuve du mécanisme**, une seule ligne :

```json
{ "mgba@1:1": { "h": 1080, "w": 1234, "x": 343, "y": 0 } }
```

1234/1080 = **1.14** : c'est une Game Boy. Un jeu GBA dessiné sur 1080 de haut
fait **1620** de large. **Le cadre lui mangeait 193 px de chaque côté** — et
`"measure": fixed is None` valant `false`, la boîte n'allait plus jamais
regarder. La première console jouée avait verrouillé les trois, définitivement.

Trois choses qui ne collaient pas avec le brief, écrites plutôt que tues :

1. Le PNG n'est pas « taillé pour la Game Boy », il est faux pour les trois.
2. **`duckstation` porte un défaut latent** : trou en `180:121` (1.488) pour une
   console qui rend en 4:3. Sans rapport avec le multi-console, signalé, pas
   corrigé.
3. **Quatre PNG ont disparu de ta boîte** — `assets/overlays/` ne contient plus
   que `azahar.png` et `melonds.png`. La correction date du 17 août, le ménage
   du 18. Le symptôme que tu décris est donc antérieur, et **il reviendra tel
   quel le jour où tu remettras les PNG** : la correction, elle, est restée.

**1.4** — relevé refait : `mgba` (3 consoles), `dolphin` (2), dix packs à une, et
`shadps4` à **zéro** — avec `"extensions": []` en prime. Le trou de catalogue est
double, et il est signalé sans être bouché.

---

# Phase 2 — ce qui a été construit

| fichier | ce qu'il fait |
|---|---|
| `backend/services/consoles.py` | **nouveau** — quelle console d'un pack pour ce ROM |
| `backend/services/bezels.py` | le niveau `console` dans `resolve()`, `console_png()`, `hole_of()` |
| `backend/services/bezel_capture.py` | `key_for/correction_for/record` prennent la console |
| `backend/routers/overlays.py` | route de dépôt par console, refus d'une image opaque |
| `catalog/_schema/pack.schema.json` | `roms.consoles` |
| `catalog/{mgba,dolphin}/pack.json` | les cinq consoles déclarées |
| `backend/services/catalog/{tiles,merge}.py` | porté dans `systems.json`, **et jusqu'à ta boîte** |
| `scripts/check-catalog.py` | refuse une déclaration incohérente |
| `electron/main.js` | renvoie la console avec la mesure |
| `frontend/src/…` | l'écran des options nomme la console |

**Aucune liste de consoles n'est écrite dans le code.** Le QUOI est déclaratif,
le COMMENT est dans le générateur : un pack ajouté demain marche sans que le
cœur le connaisse.

## Les quatre vérifications de 2.5

**① La démonstration de 1.1, rejouée.** Trois réponses **différentes** :

```
Tetris (World).gb          console='gb'
Zelda Oracle (USA).gbc     console='gbc'
Pokemon Emerald (USA).gba  console='gba'
```

Et les clés de correction se séparent : `mgba/gb@1:1`, `mgba/gba@1:1`,
`mgba/-@1:1` — l'ancienne `mgba@1:1` n'est plus atteignable, `pcsx2@4:3` est
inchangée.

**② Un test rouge avant le correctif.** `test_bezels_consoles.py` a été écrit
d'abord et lancé sur le code d'avant :

```
>       assert (gb_level, gba_level) == ("console", "console")
E       AssertionError: assert ('system', 'system') == ('console', 'console')
```

Pas une `ImportError` — un échec de comportement, sur le défaut exact.
5 tests rouges, dont celui-ci.

**③ La non-régression, mesurée contre le code réellement déployé.** J'ai fait
tourner `/opt/GameCore` (l'ancien code) et le clone (le nouveau) **sur les mêmes
données**, et comparé les sorties de `for_launch` pour six systèmes
mono-console :

```
✅ IDENTIQUE — les packs mono-console ne bougent pas d'un octet (hors le champ console)
```

Plus un test qui compare `describe()` en bloc, et un qui épingle
`key_for("pcsx2", …) == "pcsx2@180:121"`.

**④ `check-catalog.py` valide la nouvelle forme et échoue sur une incohérente.**
Vérifié dans les deux sens :

```
check-catalog: mgba: *.gba is claimed by both 'gba' and 'gbc' — an extension names one console or none
check-catalog: mgba: console 'gbc' claims *.sgb but roms.extensions does not list it
check-catalog: 2 problem(s)
```

## Les six commandes

| | avant | après |
|---|---|---|
| `ruff check .` | ✅ | ✅ |
| `shellcheck` | ✅ | ✅ |
| `check-catalog.py` | 17 packs OK | 17 packs OK |
| `gen-catalog.py --check` | à jour | à jour |
| `pytest` | **1634** passés, 5 ignorés | **1659** passés, 5 ignorés |
| `npm run build` | ✅ | ✅ |

+25 tests, aucune fixture touchée, `config/overlays.json` inchangé.

---

# Phase 3 — le protocole

Dans [`bezels-par-console-phase3.md`](bezels-par-console-phase3.md) : la
non-régression d'abord, mgba, dolphin, chaque niveau de la cascade, le dépôt, et
la migration avec sauvegarde et chemin de retour.

**Le point le plus utile du document :** `update/linux.sh` lance déjà
`merge_file()` sur `config/systems.json` après le rsync — le mécanisme mis en
place pour réparer le lanceur N64. J'y ai accroché `consoles`, avec la même règle
prudente que `libretroSystems` (rempli si la boîte n'en a aucun, jamais écrasé).
Vérifié à blanc sur une copie de ta vraie `systems.json` :

```
dolphin: consoles filled in (gamecube, wii)
mgba: consoles filled in (gba, gbc, gb)
```

**Donc il n'y a rien à renommer, rien à déplacer, rien à vider.** C'était
l'hypothèse du brief ; elle est fausse à la mesure, et c'est une bonne nouvelle.
Il reste une seule chose manuelle, et c'est celle que je ne peux pas faire à ta
place : **déposer les images**.

---

# Ce que cette phase ne fait pas

**Elle rend possible un bezel par console. Elle n'en fournit aucun.**

Aucun PNG n'est ajouté par ce travail. Le dépôt reste à toi, et c'est un travail
d'image, pas de code.

Ce qui s'améliore quand même **sans que tu déposes quoi que ce soit** : la
correction de dérive est désormais apprise **par console**. Sur ta boîte, un jeu
GB apprendra `mgba/gb@1:1` ≈ 1200x1080 et un jeu GBA `mgba/gba@1:1` ≈ 1620x1080.
**Le trou devient donc juste pour chaque console** et le jeu est entièrement
visible. Le décor, lui, reste le cadre 1:1 qui ne colle à aucune des deux : il ne
mordra plus, mais il laissera du noir. Le cadre qui **épouse** l'image demande
une image taillée pour.

Et ce n'est **pas un correctif pour dolphin** : GameCube et Wii partagent le 4:3,
rien ne débordait. C'est une capacité, deux bezels pour deux machines.

---

# Ce dont je ne suis pas sûr

1. **Le refus d'une image opaque sur la route système existante** (décision 6).
   C'est le seul changement de comportement sur un point d'entrée qui existait,
   et il rend le JPEG inutilisable en pratique. Correct, mais plus strict
   qu'avant, et je l'ai décidé seul.

2. **`.iso` et `.rvz` non rattachés rendent le niveau console peu utile pour
   dolphin.** Défendable — c'est le refus de deviner — mais le résultat est une
   fonctionnalité qui ne servira presque jamais sur ce pack.

3. **Le seuil de plausibilité pour la GBA.** `is_plausible` demande une
   couverture entre 0.25 et 0.995 et un centrage à 8 px près. J'ai calculé que
   1620x1080 dans 1920x1080 donne 0.84, centré à 150/150 : ça passe. **Je ne l'ai
   pas vu passer sur un vrai écran** — il n'y a pas de capture X11 possible ici,
   et ce module n'est couvert par aucun test pour cette raison.

4. **Le défaut latent de `duckstation`** (`180:121` pour du 4:3). Signalé,
   non corrigé, et je n'ai pas cherché si le PNG ou la fiche a raison.

5. **`shadps4` sans `libretroSystems` ni `extensions`.** Signalé, non touché : le
   brief disait de laisser décider pour les cas douteux.

6. **Je n'ai pas relancé de service `gamecore-*`**, rien écrit dans
   `~/.var/app/`, ni dans les ROMs, ni dans les sauvegardes, et `/opt/GameCore`
   n'a été ouvert qu'en lecture. Les seules écritures sont dans le clone et dans
   un répertoire temporaire.
