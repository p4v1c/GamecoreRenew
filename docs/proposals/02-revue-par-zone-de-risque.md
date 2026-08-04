# Revue du diff par zone de risque

261 fichiers, +46 372 / −3 408. Le nombre est trompeur : **178 fichiers sur 261
sont des ajouts inertes** (packs, fixtures, tests, docs). Ce document classe le
diff non pas par répertoire, mais par la seule question qui compte pour un
boîtier en production :

> **Qu'est-ce qui atteint la machine, et quand ?**

Rien n'est committé, rien n'est poussé, `/opt` n'a jamais été touché. Ce
document sert à décider quoi relire avant de franchir cette ligne.

---

## Le tableau de bord

| Zone | Fichiers | Quand ça s'exécute | Risque |
|---|---|---|---|
| **1. OTA automatique** | 4 | à **chaque** mise à jour, sur **tous** les boîtiers | 🔴 **élevé** |
| **2. Backend au démarrage** | 8 | au redémarrage du service, après OTA | 🟠 **moyen-élevé** |
| **3. Graines déployées** | 6 | seulement si on relance `install-emu-configs.sh` | 🟠 **moyen** |
| **4. Installation** | 5 | seulement si on (ré)installe | 🟡 **moyen-faible** |
| **5. Désinstallation** | 1 | seulement si on désinstalle | 🟡 **moyen-faible** |
| **6. Nouveaux outils** | 6 | seulement si on les appelle | 🟢 **faible** |
| **7. Données inertes** | 178 | jamais exécuté | 🟢 **nul** |
| **8. Frontend** | 4 | au chargement de l'UI | 🟢 **faible** |

---

## 🔴 Zone 1 — ce qui s'exécute à chaque OTA, tout seul

**C'est la seule zone qui peut casser un boîtier sans que personne ne le
demande.** Un `git push` sur `main` déclenche une release, et la flotte
l'installe automatiquement.

### `update/linux.sh` (+58 / −32)

Deux changements, et le second est le plus important de tout le travail.

**(a) `catalog/` et `scripts/` entrent dans le rsync.** Purement additif.

**(b) L'OTA ÉCRIT désormais dans `config/systems.json`.**

C'est un changement de nature, pas de degré. Jusqu'ici l'OTA ne touchait de
`config/` que `config/themes/`. Le bloc qui *imprimait* les instructions de
migration N64 les *applique* maintenant.

| À vérifier en priorité | |
|---|---|
| Le `.bak-merge` est-il bien créé ? | `merge_file` sauvegarde avant d'écrire |
| Un `systems.json` bricolé à la main survit-il ? | 13 tests le couvrent, dont « une tuile ajoutée à la main est intacte » |
| L'écriture est-elle atomique ? | `tmp.replace()` — une grille à moitié écrite, c'est un boîtier sans interface |
| L'échec est-il non fatal ? | `|| echo WARNING` : une fusion ratée ne doit pas casser la mise à jour |

**Test de relecture suggéré** : `backend/tests/test_catalog_merge.py`, en
particulier `test_a_clean_box_produces_no_notes` — une mise à jour qui ne change
rien doit ne rien dire.

**Point de vigilance non couvert par les tests** : la fusion s'exécute avec
`${GAMECORE_PATH}/.venv/bin/python3` **après** `pip install`. Si le venv est
cassé à ce moment-là, la fusion est sautée avec un avertissement. Voulu, mais
jamais exercé en vrai.

### `catalog/` (données) — 200 fichiers

Livré par l'OTA, mais **inerte** : rien ne le lit tant que le backend ne
redémarre pas. Voir zone 2.

---

## 🟠 Zone 2 — le backend, après le redémarrage post-OTA

Ces fichiers ne s'exécutent pas pendant la mise à jour, mais dès que le service
repart.

### `backend/services/controller_profiles.py` (+77 / −1670)

**Le plus gros changement de tout le travail.** 1705 lignes → 111. La logique
est partie dans `backend/services/configgen/` et `catalog/*/generator.py`.

**Ce qui s'exécute, et quand** : à la connexion d'une manette
(`gamepad_monitor` → `apply_profile`). Donc : au premier branchement après le
redémarrage.

**Ce qui garantit l'équivalence** : 112 fixtures de caractérisation, générées
depuis l'**ancienne** implémentation, rejouées octet pour octet sur la nouvelle.
14 scénarios × 3 familles de manettes × 4 slots.

**La limite honnête, et c'est la principale de tout le travail** :

> Les fixtures ont été produites sur des **graines fraîches**. Vos configs
> réelles ont un historique — `.bak-ctrlmodel`, réglages faits à la main,
> sections que l'ancien code avait déjà réécrites. Ce cas-là n'est pas couvert.

**Vérification concrète après déploiement** :
```bash
# avant de brancher une manette
cp -a ~/.var/app/net.rpcs3.RPCS3/config/rpcs3/input_configs ~/rpcs3-avant
# brancher, puis
diff -r ~/rpcs3-avant ~/.var/app/net.rpcs3.RPCS3/config/rpcs3/input_configs
```
Seule la ligne `Device:` du joueur concerné doit bouger.

### `backend/routers/systems.py` (+52 / −3)

`serve_logo` résout désormais par pack quand `assets/logos/<nom>` est absent.
S'exécute au rendu de la grille. **Régression possible : des tuiles sans image.**
La surcharge locale reste prioritaire, donc un boîtier qui a ses logos ne change
pas. Vérification : ouvrir la grille, compter les images.

### `scraper.py` (+44 / −31) et `gamemedia.py` (+33 / −9)

Les tables de plateformes viennent du catalogue. S'exécute au scraping de
jaquettes. **Deux divergences corrigées au passage** : `melonds` gagne
« Download Play », `xenia` gagne enfin son repli libretro.

Repli testé : catalogue illisible → tables réduites aux extras, pas de crash.

### `backend/main.py` (+4 / −1)

Enregistre le router `catalog`. Trivial, mais c'est ce qui **expose** la zone 6.

---

## 🟠 Zone 3 — les graines, seulement sur acte délibéré

Les graines sont livrées par l'OTA mais **jamais déployées automatiquement** :
il faut lancer `install-emu-configs.sh` à la main. C'est ce qui rend cette zone
moins dangereuse qu'elle n'en a l'air.

**Six graines ont un contenu modifié** (toutes les autres sont des déplacements
purs) :

| Graine | Lignes | Pourquoi |
|---|---|---|
| `ryujinx/Config.json` | 18 | 4 GUID de DualShock 4 en dur → vidés |
| `rpcs3/…/Default.yml` | 8 | `Device: PS4 Controller 1..4` → `""` |
| `dolphin/GCPadNew.ini` | 8 | `Device = SDL/0..3/PS4 Controller` → vide |
| `azahar/qt-config.ini` | 6 | `/home/pavic` → `@HOME@` |
| `melonds/melonDS.toml` | 2 | `[Mic] Device = "JBL Charge 2"` → `""` |
| `ppsspp/ppsspp.ini` | 2 | `/home/pavic` → `@HOME@` |

**Conséquence à connaître** : après déploiement, les manettes des joueurs 1-4
sont *non liées* jusqu'à ce qu'un pad se connecte — moment où le générateur
écrit le bon nom. C'est déjà le comportement actuel pour toute manette qui n'est
pas une DS4 ; la différence est qu'il l'est maintenant pour tout le monde.

**Effet de bord Dolphin** : `GCPad1` sans ligne `Device` valide n'est plus
« réel » au sens de `_gcpad_is_real`, donc le générateur le reconstruit depuis
le template canonique plutôt que de conserver les bindings de la graine. Ces
bindings étaient déjà des jetons de rôle SDL identiques au template, à la
`Calibration` et au `Modifier` près — que le code retire de toute façon. **À
relire si vous tenez à la calibration de la graine.**

---

## 🟡 Zone 4 — l'installation

### `install/arch.sh` (+106 / −159)

17 hunks, tous dans deux régions :

- **l.466-593** : les app-ids et la liste viennent du catalogue ; les deux blocs
  sur-mesure DuckStation/Xenia (130 lignes) deviennent un appel de provider.
- **l.820-930** : substitution `@HOME@`, liste des apps, dossiers ROMs.

**Le risque n'est pas le code, c'est la dépendance nouvelle** : `arch.sh` appelle
maintenant `scripts/catalog-query.py` et `scripts/gamecore-provider.py`. Un test
vérifie que `scripts/` est bien embarqué dans les deux archives de release —
il ne l'était pas, et je l'ai découvert en phase 3.

### `install/install-emu-configs.sh` (+47 / −39)

La map `DEST` vient du catalogue. **C'est ici que meurt le bug gopher64.**
Testé de bout en bout avec un `HOME` bac à sable : 10 graines déployées, pas de
dossier fantôme, zéro `@HOME@` résiduel.

### `install/flatpakify-systems.sh` (+20 / −12)

`FLATPAK_MAP` vient du catalogue. **La passe *prune* est inchangée** — sa
prudence délibérée est préservée.

### `install/installer-gui/gamecore_installer.py` (+8 / −22)

Liste importée d'un module généré. Le binaire PyInstaller doit être rebâti pour
en profiter ; sinon il garde son ancienne liste, sans casse.

### `install/setup-update-permissions.sh` (+41 / −5)

**Ajoute une règle sudoers.** Voir zone 6.

---

## 🟡 Zone 5 — la désinstallation

### `install/uninstall.sh` (+28 / −22)

6 hunks, tous dans le bloc « Emulator configurations ». La map vient du
catalogue, **branche native incluse** — ce qui corrige au passage la divergence
D-2 (sur un boîtier en mgba natif, les `.bak-preinstall` n'étaient jamais
restaurés).

**Non testé de bout en bout.** Une désinstallation réelle n'a pas été jouée.
Si vous testez sur une machine jetable, `--dry-run` d'abord.

---

## 🟢 Zone 6 — les nouveaux outils

Six fichiers, **aucun ne s'exécute tant qu'on ne l'appelle pas** :
`gamecore-emu`, `catalog-query.py`, `gamecore-provider.py`, `check-catalog.py`,
`gen-catalog.py`, `catalog_data.py`.

**Sauf une chose, et elle mérite votre attention** : la règle sudoers.

```
<user> ALL=(root) NOPASSWD: /usr/local/bin/gamecore-emu
```

C'est le seul privilège nouveau posé sur la machine. Il ne s'active qu'en
exécutant `setup-update-permissions.sh` en root — ce que fait `arch.sh` à la
fin. Donc : **une réinstallation active ce canal.**

Les trois garde-fous, à relire ensemble :

1. le script est installé **root-owned dans `/usr/local/bin`** — une règle
   pointant dans `$GAMECORE_PATH`, inscriptible par l'utilisateur qu'elle
   autorise, serait un shell root déguisé ;
2. `gamecore-emu` refuse tout id absent du catalogue ;
3. un pack de `config/catalog.d/` est **données seules** — donc le nommer via ce
   canal n'exécute rien.

Ce n'est **pas** une règle `NOPASSWD: /usr/bin/flatpak`, qui aurait laissé
installer n'importe quelle application depuis n'importe quel dépôt.

---

## 🟢 Zone 7 — inerte

178 fichiers ajoutés qui ne s'exécutent jamais sur un boîtier :

- 114 fixtures de test
- 17 `pack.json`, 39 fichiers de graine, 17 logos
- 9 tests backend, 7 modules `configgen`, la doc

Relecture utile mais sans risque. Les 10 `catalog/*/generator.py` sont du code —
mais ils ne tournent qu'à la connexion d'une manette (zone 2).

---

## 🟢 Zone 8 — le frontend

4 fichiers. `systemColors.ts` devient généré (et corrige deux couleurs
divergentes), `CatalogPage.tsx` est nouveau, `SettingsModal.tsx` gagne une
entrée, `api/index.ts` gagne un client. Typecheck TypeScript propre.

Risque : une entrée de menu en plus. Si la page casse, elle casse seule.

---

## Ce que la fusion ferait sur VOTRE boîtier, mesuré

Simulé en lecture seule contre `/opt/GameCore/config/systems.json` réel, avec le
catalogue de ce clone :

```
entrées : 11 -> 13

 · azahar:      extensions gained *.cia
 · dolphin:     extensions gained *.wbfs, *.wad
 · duckstation: extensions gained *.cue, *.chd, *.pbp
 · pcsx2:       extensions gained *.chd
 · ppsspp:      extensions gained *.pbp
 · shadps4:     added — new in this release
 · xenia:       added — new in this release
```

Trois choses à en retenir :

**Aucun lanceur ne serait réécrit.** Votre `systems.json` pointe déjà les bons
app-ids partout — y compris le N64, qui dit déjà `com.github.Rosalie241.RMG` — et
`lib/duck` existe bien chez vous, donc DuckStation garde son binaire natif. La
règle conservatrice fait exactement ce qu'elle promet : elle ne touche rien.

**`duckstation` gagne `*.cue` — et j'avais d'abord surestimé l'effet.**

Mesuré en lançant réellement le backend sur un boîtier de test, avec le couple
`Dragon Ball Z .bin` / `.cue` copié depuis vos ROMs :

```
extensions d'avant  -> 1 jeu : 'Dragon Ball Z - Ultimate Battle 22 .bin'
extensions fusionnées -> 1 jeu : 'Dragon Ball Z - Ultimate Battle 22 .cue'
```

**Le jeu n'est pas perdu aujourd'hui.** La panne « d'un jeu à zéro » décrite
dans `rom_scanner.py` a été corrigée depuis : le scanner ne masque un fichier
que si son remplaçant sera effectivement listé, donc un `.cue` absent des
extensions ne masque rien. Ma première rédaction disait « votre boîtier est dans
cet état aujourd'hui » — c'était faux, et c'est le fait de lancer l'application
qui l'a montré.

Ce que la fusion change réellement : DuckStation recevra le `.cue` au lieu du
`.bin`. C'est le descripteur correct pour un disque multi-pistes, mais **le nom
listé change**, et le temps de jeu est stocké sous ce nom. `playtime_repair.py`
existe exactement pour ça et corrige dans les deux sens — à surveiller
néanmoins au premier lancement après la fusion.

**`dolphin` garde `*.wii`.** Cette extension est dans votre liste et dans aucun
pack : c'est un ajout à vous, et la règle additive le préserve. Démonstration sur
données réelles, pas sur un test.

Vous pouvez rejouer cette simulation vous-même à tout moment — elle n'écrit rien :

```bash
cd ~/Downloads/GamecoreRenew && python3 -c "
import sys, json; sys.path.insert(0,'.')
from pathlib import Path
from backend.services.catalog import load_catalog
from backend.services.catalog.merge import merge_systems
live = json.load(open('/opt/GameCore/config/systems.json'))
packs = load_catalog(Path('catalog'), Path('config/catalog.d'))
_, notes = merge_systems(live, packs, Path('/opt/GameCore'))
print('\n'.join(notes) or 'rien à changer')"
```

---

## Ce que le lancement réel de l'application a trouvé

L'appli a été démarrée pour de bon : backend isolé (`HOME` bidon,
`GAMECORE_PATH` sur un boîtier de test), frontend construit, trois ROMs copiées
depuis `/opt` en lecture seule, et un jeu lancé. Trois choses en sont sorties.

### 1. Un bug réel, corrigé — le token `@HOME@` non résolu

Les tuiles YouTube et Twitch lançaient
`firefox --profile '@HOME@/.mozilla/firefox/youtube-tv'`.

`arch.sh` était le **seul** endroit qui substituait le token, à l'installation.
Un `config/apps.json` arrivé autrement — restauré d'une sauvegarde, copié du
dépôt, écrit à la main — gardait le littéral. Échec silencieux : Firefox
démarre, ne trouve pas le profil, et la tuile a l'air cassée sans raison
visible.

Corrigé dans `backend/routers/systems.py` : les tokens se résolvent **à la
lecture**, quelle que soit la provenance du fichier. Deux tests le figent.
Votre boîtier n'était pas touché (chemin absolu déjà en place), mais le piège
était armé.

### 2. Une surestimation de ma part, corrigée

Voir plus haut : le `.cue` ne fait pas disparaître le jeu. Le scanner a été
corrigé depuis. Ce que la fusion change, c'est le fichier listé — donc le nom
sous lequel le temps de jeu est stocké.

### 3. Un défaut latent, préexistant, à connaître

`bundled_sdl2()` interroge `flatpak info --show-location`. Quand cet appel
échoue — flatpak occupé, timeout, installation utilisateur invisible — il rend
`""`, et `guid_for()` retombe **silencieusement** sur la SDL2 de l'hôte.

Mesuré : SDL2 de Ryujinx → `0-00000003-…` (bus USB) ; SDL2 de l'hôte →
`0-00000005-…`. Ryujinx résout par `IndexOf(id)`, donc le second donne −1 et le
slot est supprimé **sans un mot**. C'est exactement la panne que l'invariant #4
existe pour empêcher, mais par un autre chemin : pas un GUID inventé, un GUID
lu à la mauvaise source.

**Ce n'est pas une régression** — le code d'origine avait la même construction
(`_sdl2_probe(vendor, product, bundled_sdl2(RYUJINX_APP))`). C'est un cas que
le refactor n'a ni créé ni corrigé, et que je n'aurais pas vu sans lancer
l'application. Candidat pour un `Skip` explicite plutôt qu'un repli muet.

### 4. Une mesure fausse de ma part, corrigée

Le nom SDL3 d'un pad dépend de `SDL_GAMECONTROLLERCONFIG_FILE` :

```
sans la base communautaire : 045e -> Xbox One Wireless Controller
avec (ce que fait le code ET process_manager.py:180) : 045e -> Xbox One Controller
```

Mes premières mesures ont été prises **sans** la variable. Le nom Xbox était
donc faux dans la documentation et dans les fixtures de caractérisation. Les
fixtures ont été régénérées depuis l'**ancienne** implémentation — pour ne pas
perdre la propriété qui fait leur valeur — et la nouvelle les reproduit toujours
octet pour octet.

Sans lancer l'application, cette erreur serait passée : les fixtures étaient
cohérentes avec elles-mêmes, simplement pas avec un vrai boîtier.

### Ce qui a été validé sur matériel réel

Le backend a profilé votre DualShock 4 physique à travers le pipeline refactoré,
en écrivant dans le bac à sable :

```
RPCS3    Device: PS4 Controller 1        (dup 0, 1-based)      ✓
Dolphin  Device = SDL/0/PS4 Controller   (dup 0, 0-based)      ✓
Ryujinx  id écrit, sauvegarde .bak-ctrlmodel créée             ✓
joueurs 2-4                              laissés intacts       ✓
```

Le pad Xbox s'est déconnecté en cours de session, donc **le cas à deux manettes
n'a pas été rejoué sur matériel réel** — il ne l'est que par les fixtures.

Lancement de jeu de bout en bout : `POST /api/games/launch` → `mgba-qt
--fullscreen <rom>` démarré, session suivie, `POST /api/games/kill` l'a arrêté,
15 s de temps de jeu enregistrées. `process_manager.py` n'est pas dans le diff :
ce chemin est du code d'origine.

**Isolation vérifiée après coup : 0 fichier modifié dans `~/.var/app`, 0 dans
`/opt`.**

---

## Ordre de relecture recommandé

Si vous ne relisez que quatre choses :

1. **`update/linux.sh` l.370-410** — le seul code qui s'exécute tout seul sur
   tous les boîtiers, et il écrit désormais dans `config/`.
2. **`install/setup-update-permissions.sh`** — le seul privilège nouveau.
3. **Les six graines modifiées** — c'est ce qui atterrit dans vos configs.
4. **`backend/services/configgen/__init__.py`** — le dispatcher qui remplace
   1700 lignes ; en particulier l'ordre `STEP_ORDER` et le traitement
   `snapshot-or-synth`.

## Le protocole de test que je recommande

```bash
# 1. sur une VM ou une machine jetable, PAS la prod
sudo bash install/arch.sh --full

# 2. brancher une manette, vérifier qu'un jeu répond dans 2-3 émulateurs

# 3. vérifier ce que le catalogue croit
gamecore-emu list
gamecore-emu verify

# 4. simuler une OTA sur un boîtier existant : la fusion est le point neuf
python3 -c "
import sys; sys.path.insert(0,'/opt/GameCore')
from backend.services.catalog import load_catalog
from backend.services.catalog.merge import merge_file
from pathlib import Path
root = Path('/opt/GameCore')
for n in merge_file(root/'config/systems.json',
                    load_catalog(root/'catalog', root/'config/catalog.d'),
                    root, dry_run=True): print(n)
"
```

L'étape 4 est **non destructive** (`dry_run=True`) et peut se lancer sur la prod
sans rien changer : elle dit exactement ce que la fusion ferait.
