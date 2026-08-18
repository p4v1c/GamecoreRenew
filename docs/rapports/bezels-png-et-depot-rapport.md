# Les PNG de mGBA, et le dépôt depuis ROM Manager — rapport

Deux dépôts, deux états différents :

| dépôt | branche | état |
|---|---|---|
| `GamecoreRenew` | `feat/bezels-mgba-png-et-emplacements` | **poussée, non fusionnée** |
| `gamecore-addons` | `main` | **fusionnée et poussée — en production** |

---

# ⚠️ Deux choses à lire avant le reste

## 1. J'ai arrêté ROM Manager sur ta boîte, par accident

En nettoyant mes serveurs de test j'ai tapé `pkill -f "server.py"`, qui a
attrapé le service de ta boîte (pid 786) en plus du mien. Il est arrêté depuis
18:06, pas désactivé.

**Je ne l'ai pas redémarré** — tu as dit garder la main. La commande :

```bash
systemctl --user start gamecore-addon-rom-manager
```

Le cœur (8765) n'a pas été touché, `rpcs3-manager` et `save-manager` étaient
déjà inactifs avant que j'arrive. Aucune écriture sur la boîte : j'ai vérifié
après coup que `assets/overlays/` et `bezel-corrections.json` ont leurs mtimes
d'origine.

## 2. Un fichier parasite est parti dans ce que tu as fusionné

`config/bezel-holes.json` a été committé par erreur dans mon premier commit
(`b2eddb0`) — un `git add -A` a ramassé un cache généré par mes propres
exécutions. C'est un cache pur, **indexé par chemin absolu**, qui embarque les
`/home/pavic/Downloads/GamecoreRenew/...` de ma machine dans chaque clone.

Rien de sensible et rien de cassé — le backend le reconstruit en 0,4 s par PNG
et invalide chaque entrée par mtime et taille. Mais il n'a rien à faire là.

**Le correctif est dans la branche de cette phase** (`5553850`), qui l'enlève du
suivi et ajoute les trois caches de bezels au `.gitignore`. Il arrivera avec le
reste ; il n'y a rien à taper.

---

# Décisions prises seul

### 1. Les trois PNG vont dans `assets/overlays/` du dépôt — et n'écraseront jamais personne

C'était la question à trancher, et la réponse était déjà dans `install/arch.sh`.

`assets/overlays/` est exclu **du rsync de l'OTA et du tar d'`arch.sh`**. La
boucle qui suit ne recopie le répertoire que s'il est **absent** à destination :

```sh
for _keep in emu config assets/overlays assets/logos; do
  if [ -d "$PROJECT_ROOT/$_keep" ] && [ ! -e "$GAMECORE_PATH/$_keep" ]; then
```

**Le conflit est donc résolu à la granularité du répertoire entier, pas du
fichier** — et c'est ce qui rend la réponse simple :

| situation | ce qui arrive au bezel du joueur |
|---|---|
| installation neuve | il n'en a pas ; il reçoit les trois |
| boîte existante, OTA | **rien du tout** — le répertoire existe, il est sauté |
| boîte existante, `arch.sh` relancé | **rien du tout** — même boucle, même saut |

Un joueur qui avait déjà son bezel ne peut pas être écrasé par une release. Le
revers, c'est que **ta boîte ne les recevra pas non plus** : c'est la partie B.

Je n'ai pas inventé d'emplacement dans `catalog/` : les six bezels existants
sont déjà dans `assets/overlays/`, et un second endroit aurait été une seconde
réponse à « où vit un bezel ».

**Pour défaire :** supprimer les trois fichiers. Rien d'autre n'en dépend.

### 2. Générés par un script committé, pas déposés en binaire

`scripts/make-console-bezel.py`. Un blob dans git ne se relit pas ; le ratio,
lui, est la seule chose qu'un bezel ne peut pas se permettre d'avoir faux à un
pixel près. Là, le ratio est un argument et l'arithmétique fait huit lignes.

**Stdlib pur, pas Pillow** — pour la raison qui a déjà fait écrire
`_alpha_bbox` à la main plutôt qu'appeler ImageMagick : aucun script
d'installation ne met de bibliothèque d'images sur une boîte. (Pillow est
présent dans le venv ici, je ne m'en suis pas servi.)

**Pour défaire :** remplacer les PNG par les tiens, le script devient inutile.

### 3. Un dégradé et un biseau — rien d'emprunté

Deux panneaux latéraux sombres, un filet de couleur au bord du trou. Vert pour
la Game Boy, violet pour la Color, indigo pour l'Advance, pour que tu les
distingues d'un coup d'œil. Aucune jaquette, aucun logo.

**Pour défaire :** `--top`, `--bottom`, `--accent` sont des options.

### 4. Une route d'état côté cœur, plutôt qu'un décodeur dans l'addon

`GET /api/overlays/{system}/slots` répond ce que `choices` ne peut pas : **tous
les emplacements, remplis ou non**, avec le trou mesuré et son ratio réduit.
`choices` parle d'un jeu et ne liste que ce qui existe — une console sans bezel
y est simplement absente, et depuis un navigateur c'est indiscernable d'un
envoi qui a échoué en silence.

L'addon aurait pu lire `assets/overlays/` lui-même. Il aurait alors fallu un
second décodeur alpha pour connaître le trou, donc deux réponses à une question
qui en a déjà une.

J'ai ajouté `DELETE /api/overlays/{system}/consoles/{console}` avec : sans lui,
un bezel déposé sur la mauvaise console pouvait être remplacé mais jamais
retiré, et la cascade aurait continué à le résoudre devant le bezel système.

**Pour défaire :** les deux routes sont additives, rien d'existant n'en dépend.

### 5. L'addon dégrade au lieu de casser face à un cœur plus ancien

**C'est la décision qui a évité de te casser quelque chose.** Un addon se met à
jour par son propre `git pull`, le cœur par OTA : les deux versions sont
indépendantes. J'ai publié l'addon **avant** que la release du cœur existe, donc
sur ta boîte il va parler à un cœur qui ne connaît ni `/slots` ni
`/consoles/…`.

Sans repli, `/slots` répondait 404 et l'écran des overlays devenait inutilisable
— y compris pour le bezel **système**, qui marchait avant. La mise à jour aurait
été une régression nette.

Le repli est l'emplacement système seul, avec une phrase qui l'explique dans
l'interface. La présence est lue sur le disque — **lire** les données du joueur
est permis, c'est **écrire** hors du répertoire de l'addon qu'`api: 1` interdit
— mais le trou reste nul plutôt que deviné.

**Pour défaire :** supprimer `legacy_slots()`. À ne faire qu'une fois la release
du cœur passée partout.

### 6. J'ai fusionné dans `main` des addons — donc publié

Tu l'avais autorisé explicitement. `gamecore-addon update` fait un
`git pull --ff-only` sur le checkout qui suit `main`, **sans tag ni CI** : c'est
en production dès que tu tapes la commande de mise à jour.

C'est sans risque grâce au point 5 : sur ta boîte, l'écran des overlays se
comportera exactement comme avant jusqu'à ce que le cœur soit à jour.

**Pour défaire :** `git revert` du merge `8c44d39` puis `gamecore-addon update`.

---

# Partie A — les trois PNG

| fichier | console | trou mesuré | ratio |
|---|---|---|---|
| `mgba.gb.png` | Game Boy | `1200x1080+360+0` | **10:9** |
| `mgba.gbc.png` | Game Boy Color | `1200x1080+360+0` | **10:9** |
| `mgba.gba.png` | Game Boy Advance | `1620x1080+150+0` | **3:2** |

Trous mesurés par `bezels.hole_of()` — le vrai décodeur alpha, pas le
générateur. Cadre 1920×1080, celui que `window_rect` force. ~22 Ko chacun.

## Prouvé par un test, pas par inspection

`test_bezels_consoles.py` ajoute quatre tests sur les fichiers livrés :

- le ratio est **exact**, en arithmétique entière (`w * rh == h * rw`), pas à
  une tolérance près ;
- le trou est centré à un pixel près — sinon `is_plausible` refuserait toute
  mesure d'écran et la correction de dérive ne s'appliquerait plus jamais ;
- le nom désigne une console que `roms.consoles` déclare vraiment ;
- si un pack livre un bezel de console, il les livre **tous** — deux consoles
  habillées et la troisième en cadre 1:1 se lit comme un bug de la cascade.

**Et le test n'est pas vide.** Vérifié en régénérant `mgba.gba.png` en 10:9 :

```
E  AssertionError: mgba.gba.png: hole is 1200x1080 = 1.1111, gba renders at 3:2 = 1.5000
E  assert (1200 * 2) == (1080 * 3)
```

## « Un jeu GBA n'est plus rogné »

Mesuré de bout en bout, cœur + addon lancés sur une racine de test :

```
Pokemon Emerald (USA).gba   console=gba  source=console   trou=1620x1080+150  asset=mgba.gba.png
Zelda Oracle (USA).gbc      console=gbc  source=console   trou=1200x1080+360  asset=mgba.gbc.png
Tetris (World).gb           console=gb   source=console   trou=1200x1080+360  asset=mgba.gb.png
Compil (Europe).zip         console=None source=declared  trou=1080x1080+420  asset=-
```

1620/1080 = **1,5000**. Le trou fait 3:2, plus 1,14.

Le `.zip` retombe au niveau système : une extension ambiguë ne nomme aucune
console, c'est la décision de la phase précédente et elle se voit ici.

---

# Partie B — le dépôt depuis ROM Manager

Le modal des overlays devient **une carte par emplacement**, les vides compris :
aperçu, état (`in place` / `no bezel`), nom du fichier attendu, trou mesuré et
ratio, zone de dépôt, bouton de retrait.

## Le contrat d'addon est intact, et c'est testé négativement

`assets/overlays/` appartient au cœur. Tout passe par un relais en loopback :
le cœur décide du nom du fichier, de la destination et de la validation.

Le test qui compte le plus dans `test_overlays.py` est une **négation** — après
un envoi, l'addon ne doit avoir créé **aucun fichier nulle part** :

```
  ok   upload without a core answers 503, not 500
  ok   nothing was written under DATA
  ok   nothing was written under PATH
  ok   no assets/overlays was created at all
```

Écrire le PNG depuis l'addon aurait fait une ligne de moins, aurait marché sur
une boîte, et aurait transformé la règle en « un addon écrit partout où il peut
atteindre ». J'ai ajouté la règle 6 à `docs/SECURITY.md` du dépôt des addons
pour que ce soit écrit et pas seulement respecté.

## Le refus d'une image opaque arrive avec ses mots

Le relais rend le **statut et le corps** de la réponse du cœur. Mesuré :

```
HTTP 422
{"detail":"A bezel needs a transparent area for the game to show through,
 and this image has none the decoder can read. Save it as a PNG with an alpha
 channel — JPEG cannot carry one at all."}
```

Et aucun fichier créé. L'avaler dans un « échec » générique aurait perdu la
seule explication que le joueur reçoit.

## Deux racines réellement distinctes

Tu avais raison d'insister, et **ça a attrapé un vrai faux positif.**

`GAMECORE_BACKEND_PORT` vaut 8765 par défaut — qui sur cette machine est le
**vrai backend GameCore de ta boîte**. Mon premier jet de `test_overlays.py` lui
parlait pour de bon et mesurait ses réponses au lieu de celles de l'addon :
trois checks « échouaient » en rapportant 405 et 404, qui étaient les réponses
du cœur déployé. Le fichier épingle maintenant un port mort choisi par l'OS, et
le premier check du fichier vérifie que ce n'est pas le vrai.

(Rien n'a été écrit sur la boîte pendant ce faux départ : le cœur déployé n'a
pas ces routes, il a répondu 405. Vérifié après coup sur les mtimes.)

`test_paths.py` couvre en plus `OVERLAYS_DIR` sous les deux racines, y compris
le repli d'une boîte qui n'a pas pris l'OTA P3.

---

# Les commandes exactes à taper

## 1. Remettre ROM Manager en marche (à cause de moi)

```bash
systemctl --user start gamecore-addon-rom-manager
```

## 2. Récupérer la nouvelle version de l'addon

```bash
gamecore-addon update
```

Ça fait un `git pull --ff-only` sur `/opt/gamecore-addons` et relance les addons
installés. À faire quand tu veux : grâce au repli, l'écran des overlays se
comportera exactement comme avant tant que le cœur n'est pas à jour.

Pour vérifier :

```bash
grep '"version"' /opt/gamecore-addons/addons/rom-manager/addon.json   # 1.3.0
```

## 3. Après la release du cœur — déposer les trois PNG sur ta boîte

Ils n'arrivent **pas** par l'OTA. Deux voies, au choix.

**Par ROM Manager** (le but de tout ça) : ouvre l'écran ROMs, choisis Game Boy
Advance, bouton *Overlay*, et dépose un PNG sur chacune des trois cartes.

**En ligne de commande**, si tu préfères — les fichiers sont dans le dépôt :

```bash
cd ~/Downloads/GamecoreRenew
cp assets/overlays/mgba.gb.png  /opt/GameCore/assets/overlays/
cp assets/overlays/mgba.gbc.png /opt/GameCore/assets/overlays/
cp assets/overlays/mgba.gba.png /opt/GameCore/assets/overlays/
```

Puis vérifie, sans lancer de jeu :

```bash
cd /opt/GameCore && .venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, '.')
from backend.services import bezels
for rom in ("Tetris (World).gb", "Zelda Oracle (USA).gbc", "Pokemon Emerald (USA).gba"):
    o = bezels.for_launch("mgba", rom)
    print(f"  {rom:28s} console={o['console']!r:7s} source={o['source']:9s} "
          f"trou={o['hole']['w']}x{o['hole']['h']}")
EOF
```

Attendu : `source='console'` pour les trois, trou **1620** pour la GBA et
**1200** pour les deux autres.

⚠️ **Un PNG copié à la main n'est pas validé** — la vérification (image sans
zone transparente refusée) est sur la route, pas sur le système de fichiers.
C'est un argument pour passer par ROM Manager.

## 4. Le retour en arrière

```bash
rm -f /opt/GameCore/assets/overlays/mgba.g{b,bc,ba}.png   # les trois cadres
```

La procédure complète de la phase précédente (sauvegarde, migration, retour)
reste valable : `docs/rapports/bezels-par-console-phase3.md`.

---

# Les six commandes

| | avant cette phase | après |
|---|---|---|
| `ruff check .` | ✅ | ✅ |
| `shellcheck` | ✅ | ✅ |
| `check-catalog.py` | 17 packs OK | 17 packs OK |
| `gen-catalog.py --check` | à jour | à jour |
| `pytest` | **1659** passés | **1674** passés, 5 ignorés |
| `npm run build` | ✅ | ✅ |

Côté addons, les sept tests des quatre addons passent, `check-docs.py` aussi.

---

# Ce dont je ne suis pas sûr

1. **Les cadres sont laids et c'est voulu.** Je ne peux pas prouver qu'un bezel
   est beau. Deux panneaux et un filet : ça se juge à trois mètres, et la
   partie B existe pour que tu les remplaces sans moi.

2. **Je n'ai pas déclaré le ratio attendu d'une console dans le pack.**
   L'interface montre le ratio *mesuré* (« 3:2 ») mais ne peut pas dire « et
   cette console en attend 3:2 » — donc elle ne t'avertira pas si tu déposes un
   cadre 16:9 sur la Game Boy. Ajouter un champ `ratio` à `roms.consoles`
   règlerait ça ; je ne l'ai pas fait parce que c'était élargir la déclaration
   au-delà de ce qui était demandé.

3. **Le biseau de 28 px est un chiffre choisi à l'œil**, sur une image que je ne
   vois qu'en aperçu. Il peut être trop discret sur ta télé.

4. **Je n'ai pas vu l'interface dans un navigateur.** Le JS est vérifié
   syntaxiquement (`node --check`), les routes sont testées de bout en bout avec
   un vrai cœur, mais la mise en page des cartes n'a jamais été rendue.

5. **Le repli « cœur ancien » se déclenche sur un 404 de `/slots`.** Si un jour
   un cœur répond 404 pour une autre raison, l'écran dira « ta boîte est
   ancienne » à tort. J'ai préféré ça à un test de version, qui aurait demandé
   au cœur d'annoncer la sienne.

6. **`.iso` et `.rvz` restent non rattachés pour dolphin**, décision de la phase
   précédente : la carte console apparaîtra pour GameCube et Wii, mais la
   plupart de tes jeux Dolphin continueront de résoudre au niveau système.
