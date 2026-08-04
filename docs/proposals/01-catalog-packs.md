# Proposition — catalogue de packs & configgen

État : **conception + les cinq phases implémentées.**

**Phase 5 — installation à chaud.** Le catalogue était figé au moment de
l'install : ajouter un système imposait de relancer `arch.sh`, qui écrase
`config/systems.json`. Cinq livrables :

| | |
|---|---|
| `install/gamecore-emu` | `list` / `install` / `remove` / `reconfigure` / `verify`, sortie `--json`, sur les conventions de `gamecore-addon` |
| `backend/routers/catalog.py` | verrou `_busy_lock` et WebSocket repris d'`addons.py` |
| Écran UI | Réglages → « Emulators & apps », progression en direct |
| **La fusion OTA** | `update/linux.sh` **fusionne** au lieu d'imprimer des instructions que personne ne tape |
| Canal privilégié | `setup-update-permissions.sh` étendu — **une** règle sudoers, nommant **un** script |

La fusion est conservatrice, et chaque règle est testée : une tuile ajoutée à la
main est intacte ; un lanceur n'est réparé que s'il est *périmé* (app-id qu'aucun
pack ne déclare, ou chemin qui ne résout pas) — un binaire natif dans `lib/` qui
existe n'est jamais repoussé vers Flatpak ; les `extensions` s'ajoutent sans
jamais se perdre, parce qu'une liste périmée avait fait passer une bibliothèque
PS1 d'un jeu à zéro.

Sur la sécurité : la règle sudoers nomme `/usr/local/bin/gamecore-emu`, root, et
**pas** `flatpak` — qui aurait laissé installer n'importe quelle application
depuis n'importe quel dépôt. Le script refuse tout id que le catalogue ne déclare
pas. C'est ce qui rend la règle « données seules » de `config/catalog.d/`
portante et non décorative : un pack déposé là ne peut porter ni `generator.py`,
ni `postInstall`, ni `services`, ni `sources`, ni `packages` — donc le nommer ici
n'exécute rien non plus.

**Phase 3 — providers.**

**Phase 3 — providers.** Les deux blocs sur-mesure d'`arch.sh` (DuckStation
AppImage, Xenia zip+wine — 130 lignes, deux fonctions `fetch` quasi identiques)
sont devenus des **données** dans `catalog/<id>/pack.json`, et un seul helper
`backend/services/installer/` porte les protections qu'elles avaient gagnées :
URL fixe d'abord et API GitHub en repli (quota 60 req/h/IP), fichier `.part`,
magic bytes, échec d'extraction non fatal. `curl` est appelé avec **exactement**
les mêmes drapeaux — réécrire `--speed-limit`/`--retry-connrefused` en Python
était le meilleur moyen d'en perdre un en silence.

Ajouts demandés livrés : `sha256` optionnel (il n'existait **aucune**
vérification d'intégrité dans `install/` ni `update/`) et `version` épinglable.

22 tests couvrent chaque protection, un par panne d'origine.

**Un bug attrapé au passage, et il aurait été grave** : `arch.sh`,
`install-emu-configs.sh` et `uninstall.sh` appellent désormais `scripts/`, et
**aucune des deux archives de release ne l'embarquait**. Ça ne dégrade rien —
ça casse l'installation, sur un vrai boîtier, et jamais en CI. Corrigé, et
généralisé en test : tout répertoire qu'un installeur référence doit être dans
les deux archives.

Note de périmètre : la boucle Flatpak d'`arch.sh` reste en bash. Elle pilote la
barre de progression du wizard, et le mandat de la phase 3 portait sur les
130 lignes des deux blocs sur-mesure. Le provider `flatpak` existe et est testé
— il sert le chemin d'installation à chaud de la phase 5.

**Phase 2 — les consommateurs lisent le catalogue.**

**Phase 2 — les consommateurs lisent le catalogue.** Le bug gopher64 est mort
ici, test d'abord : `backend/tests/test_catalog_consumers.py` échouait sur six
points avant le refactor (les quatre sites de la migration N64, la divergence
libretro de melonDS, et les couleurs du frontend). Les 4 maps dupliquées ont
disparu :

| Consommateur | Avant | Après |
|---|---|---|
| `install-emu-configs.sh` | `declare -A DEST` (13 entrées) | `catalog-query.py config-dest` |
| `uninstall.sh` | la même map, recopiée | idem, branche native incluse (corrige D-2) |
| `arch.sh` | `EMU_FLATPAK`, liste d'ids, dossiers ROMs, override sandbox en dur | `catalog-query.py` |
| `flatpakify-systems.sh` | `FLATPAK_MAP` (6 entrées, ancien app-id N64) | `pack.launcher()` |
| `verify_emulators.py` | `FLATPAK_IDS` écrite à la main | dérivée du catalogue (+ les assets GitHub) |
| `scraper.py` | `TGDB_PLATFORM_MAP` + `PLATFORM_MAP` | catalogue + `_EXTRA_LIBRETRO` |
| `gamemedia.py` | `EMULATOR_ALIASES` | catalogue + `_EXTRA_ALIASES` |
| `systemColors.ts` | écrit à la main, divergent | **généré** |
| `gamecore_installer.py` | `EMULATORS` / `APPS` | **généré** dans `catalog_data.py` |
| `overlays.json` | `wm_class` à la main | `wm_class` + `overlay_asset` générés ; géométrie **et label du bezel** conservés |

Deux nouveautés de schéma, parce que le format était incomplet pour le wizard :
`emulatorName` et `description`. Le slot N64 y affichait encore « gopher64 »
alors qu'il lance RMG — il dit maintenant « Rosalie's Mupen GUI », l'id restant
`gopher64`.

Trois bugs attrapés **par mes propres tests** pendant la phase 2, et non par
relecture : `scraper.py` et `gamemedia.py` n'avaient aucun logger (ma branche de
repli aurait levé un `NameError` au lieu de dégrader proprement) ; et
`catalog-query.py` résolvait le catalogue via `GAMECORE_PATH` au lieu de le
prendre à côté de lui, ce qui rendait les installeurs muets si la variable
pointait ailleurs.

**Phase 1 — packs et génération.**

La phase 1 est en place et verte (`scripts/check-catalog.py`,
`scripts/gen-catalog.py --check`, 324 tests). Six écarts par rapport au plan
initial de la §6, tous constatés en implémentant :

| Écart | Pourquoi |
|---|---|
| `strategy: guid-rebind` renommé `rewrite-device-line` pour Dolphin | il lie par **nom**, pas par GUID. Le plan signalait « l'abus de nom » sans le corriger. |
| `config.generator` supprimé du schéma | un champ à valeur unique. `generator.py` est implicite comme `seed/` et `logo.png`. |
| `seedMustNotContain` = **regex**, pas sous-chaînes | `"Device:"` littéral est insatisfiable : le YAML de RPCS3 a structurellement besoin de la clé. Ce qui doit être interdit, c'est un `Device` qui **nomme** une manette. |
| `install-emu-configs.sh`, `uninstall.sh`, `arch.sh`, `release.yml` **modifiés** | le plan les disait intouchés en phase 1. Faux : déplacer les graines force leurs lecteurs à suivre, sinon l'installation casse. |
| `serve_logo` modifié | le plan la datait de la phase 2. Faux aussi : déplacer les logos la casse immédiatement. |
| Deux graines nettoyées | `emu-configs/dolphin/GCPadNew.ini` épinglait `SDL/0..3/PS4 Controller` et `melonDS.toml` portait `[Mic] Device = "JBL Charge 2"` (D-8). |

Effet de bord : `install-emu-configs.sh` ne crée plus le dossier fantôme
gopher64 — la graine ayant disparu, il journalise « no config bundled ». Le bug
lui-même (la map `DEST` dupliquée) reste pour la phase 2, avec le test qui
échoue sur le code actuel.

Tout ce qui suit a été vérifié sur le dépôt cloné dans `~/Downloads/GamecoreRenew`
(HEAD `492c414`) et mesuré sur la machine de référence, deux manettes connectées.
`/opt` n'a été lu qu'en lecture seule ; rien n'y a été écrit.

---

## 0. Méthode — ce qui est mesuré et ce qui est lu

**Matériel présent pendant les mesures** (heureux hasard : les deux pads sont de
**modèles différents**, donc le cas mixte est testable) :

| | evdev | vendor:product | bus | version |
|---|---|---|---|---|
| pad A | `Wireless Controller` (DualShock 4) | `054c:09cc` | `0x0005` Bluetooth | `0x8100` |
| pad B | `Xbox Wireless Controller` (Xbox One S) | `045e:02fd` | `0x0005` Bluetooth | `0x0903` |

Émulateurs réellement installés sur la machine, donc interrogeables :
azahar, cemu, dolphin, gopher64, **RMG**, melonDS, pcsx2, ppsspp, rpcs3, ryujinx,
Steam, Stremio. `io.mgba.mGBA` **n'est plus installé** (mgba tourne en natif) —
c'est important, voir §3.

> **Correction apportée après avoir lancé l'application.** Le nom SDL3 d'un pad
> dépend de `SDL_GAMECONTROLLERCONFIG_FILE`. Sans la base communautaire, SDL3
> annonce son nom HIDAPI intégré (`Xbox One Wireless Controller`) ; avec elle,
> le nom de la base l'emporte (`Xbox One Controller`). Or
> `process_manager.py:180` exporte cette variable à **tous** les émulateurs, et
> `_sdl3_live_names()` la pose pour la même raison — donc c'est le second que
> RPCS3 et Dolphin énumèrent. Mes premières mesures de cette session ont été
> prises sans la variable : le nom Xbox était faux, et il l'était dans les
> fixtures jusqu'à ce que le lancement réel le révèle. Les fixtures ont été
> régénérées depuis l'ancienne implémentation pour préserver la porte.

**Ce que deux pads ne permettent pas de vérifier** — listé ici une fois, répété
au fil du texte :

- les slots **3 et 4** : aucune assertion sur `[Pad3]`/`[Pad4]`, le multitap
  PCSX2/DuckStation, `Player 3/4 Input:` de RPCS3, `GCPad3/4`, ou `MultitapMode
  = BothPorts`. Tout ce qui suit sur les slots 3-4 est **lu dans le code et dans
  les sources des émulateurs**, pas mesuré ;
- le cas **deux pads du même modèle** (`dup_index = 1`) : mes deux pads ont des
  noms résolus différents, donc `dup` vaut 0 pour les deux. Le compteur par nom
  est confirmé *par lecture croisée du code Batocera* (§5), pas par mesure ;
- le **changement de transport** (USB ↔ Bluetooth) : les deux pads sont
  appairés en Bluetooth et je n'ai pas voulu les débrancher/rappairer sous la
  machine de l'utilisateur. La différence de bus USB/BT est donc reprise de la
  doc existante, sauf là où je l'ai recoupée autrement (§5, Ryujinx) ;
- le **débranchement à chaud** du joueur 2 : non testé, même raison.

---

## 1. Le format `pack.json`

### 1.1 Deux décisions de syntaxe, à valider

**(a) Un seul dialecte de token : `@NOM@`.** Le brief écrit
`"dest": "$FLATPAK_CONFIG/rpcs3"` d'un côté et `@HOME@` de l'autre. Deux
syntaxes pour la même chose, c'est une source de bugs, et `$…` est le mauvais
choix des deux : les consommateurs sont en **bash** (`arch.sh`,
`install-emu-configs.sh`), et un `$FLATPAK_CONFIG` littéral qui traverse un
`"…"` bash s'expanse en chaîne vide, silencieusement. `@FLATPAK_CONFIG@` ne peut
pas. Je propose donc `@HOME@`, `@FLATPAK_CONFIG@`, `@GAMECORE_PATH@`, `@USER@`.

Tokens définis :

| Token | Résolution |
|---|---|
| `@HOME@` | home de l'utilisateur GameCore |
| `@GAMECORE_PATH@` | racine d'install (`/opt/GameCore`) |
| `@USER@` | nom d'utilisateur |
| `@FLATPAK_CONFIG@` | `@HOME@/.var/app/<install.appId>/config` — **dérivé du même `appId` que le bloc `install`** |

`@FLATPAK_CONFIG@` n'est *utilisable* que si `install.provider == "flatpak"` ;
sinon le schéma le refuse. C'est ce qui rend le bug gopher64 impossible à
réintroduire : le chemin de config et l'app-id installé ne peuvent plus diverger,
ils ont une seule source.

**(b) `postInstall` est un tableau, pas une chaîne.** Twitch a besoin de deux
étapes irréductibles et **ordonnées** : générer le certificat TLS
(`make-cert.sh`, fourni par le dépôt cloné) *puis* l'importer dans la base NSS
(`certutil`). Une seule chaîne ne peut pas les exprimer sans réintroduire un
script bash qui en appelle deux autres.

### 1.2 Ce qui manque pour décrire `twitch` sans bash

Le brief demande de le dire plutôt que de contourner. Quatre points :

1. **La route Caddy.** `/twitch/*` est déclarée dans `install/Caddyfile:80,106`,
   avec un contrat précis (`BASE_PATH=/twitch`, pas de `handle_path`, derrière
   `forward_auth`). Aucun bloc de pack ne peut ajouter une route à un fichier
   central écrit en root. **Je ne propose pas de bloc `httpRoutes`** : ce serait
   laisser un pack local injecter une route dans le reverse-proxy, exactement ce
   que la règle « données seules » de `config/catalog.d/` interdit. La Caddyfile
   reste centrale, et le pack `twitch` livré dans `catalog/` documente sa route
   sans la créer. À acter explicitement comme une limite assumée.
2. **Un `files[]` conditionnel.** Sans identifiants, `arch.sh:719` copie
   `config.example.json` en `config.json` (mode démo). C'est un `if` sur la
   valeur d'un secret. Je propose le champ minimal `"when"`, qui n'accepte qu'une
   forme : `"secrets.<KEY>"` ou `"!secrets.<KEY>"` — présence/absence, pas
   d'expressions.
3. **L'ordre des blocs doit être normatif**, sinon `postInstall` devient un
   fourre-tout. Ordre fixe :
   `packages` → `install` (provider) → `sandbox` → `sources` → `secrets` (invites)
   → `files` → `services` → `postInstall[]`.
4. **La déduplication de paquets entre packs.** `twitch` et `youtube` demandent
   tous deux `firefox` + `nss`. Aujourd'hui `arch.sh:684` les installe une fois
   pour les deux (`if want_app twitch || want_app youtube`). L'installeur devra
   agréger les `packages` de tous les packs sélectionnés en **un** appel pacman,
   pas un par pack — sinon `pacman -S` tourne deux fois et le manifeste
   `record_new_pkgs` double les entrées.

### 1.3 Schéma — `catalog/_schema/pack.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://gamecore.local/schemas/pack.schema.json",
  "title": "GameCore catalog pack",
  "type": "object",
  "required": ["id", "kind", "label", "platform", "color", "launch"],
  "additionalProperties": false,

  "properties": {
    "id":       { "type": "string", "pattern": "^[a-z0-9][a-z0-9_-]*$" },
    "kind":     { "enum": ["emulator", "app"] },
    "label":    { "type": "string", "minLength": 1 },
    "platform": { "type": "string", "minLength": 1 },
    "color":    { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },

    "install": {
      "type": "object",
      "required": ["provider"],
      "oneOf": [
        { "properties": { "provider": { "const": "flatpak" },
                          "appId": { "type": "string", "minLength": 1 } },
          "required": ["provider", "appId"], "additionalProperties": false },

        { "properties": { "provider": { "const": "github-asset" },
                          "repo":   { "type": "string", "pattern": "^[^/]+/[^/]+$" },
                          "asset":  { "type": "string" },
                          "dest":   { "type": "string" },
                          "magic":  { "enum": ["ELF", "PK", "7z"] },
                          "mode":   { "type": "string", "pattern": "^[0-7]{3,4}$" },
                          "version":{ "type": "string" },
                          "sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" } },
          "required": ["provider", "repo", "asset", "dest", "magic"],
          "additionalProperties": false },

        { "properties": { "provider": { "const": "github-archive" },
                          "repo":         { "type": "string", "pattern": "^[^/]+/[^/]+$" },
                          "asset":        { "type": "string" },
                          "assetPattern": { "type": "string" },
                          "dest":         { "type": "string" },
                          "entrypoint":   { "type": "string" },
                          "magic":        { "enum": ["PK", "7z"] },
                          "requires":     { "type": "array", "items": { "type": "string" } },
                          "version":      { "type": "string" },
                          "sha256":       { "type": "string", "pattern": "^[0-9a-f]{64}$" } },
          "required": ["provider", "repo", "asset", "dest", "entrypoint", "magic"],
          "additionalProperties": false },

        { "properties": { "provider": { "const": "pacman" },
                          "packages": { "type": "array", "items": { "type": "string" },
                                        "minItems": 1 } },
          "required": ["provider", "packages"], "additionalProperties": false },

        { "properties": { "provider": { "const": "none" } },
          "required": ["provider"], "additionalProperties": false }
      ]
    },

    "sandbox": {
      "description": "Flatpak override. Absent = politique émulateur par défaut.",
      "type": "object", "additionalProperties": false,
      "properties": {
        "filesystem": { "type": "array", "items": { "type": "string" } },
        "device":     { "type": "array", "items": { "type": "string" } },
        "socket":     { "type": "array", "items": { "type": "string" } }
      }
    },

    "launch": {
      "type": "object", "required": ["path"], "additionalProperties": false,
      "properties": {
        "path": { "type": "string", "minLength": 1 },
        "args": { "type": "string" },
        "preferIfPresent": {
          "type": "object", "required": ["path"], "additionalProperties": false,
          "properties": { "path": { "type": "string" }, "args": { "type": "string" } }
        }
      }
    },

    "roms": {
      "type": "object", "required": ["dir"], "additionalProperties": false,
      "properties": {
        "dir":        { "type": "string", "pattern": "^emu/[a-z0-9_-]+$" },
        "scanDirs":   { "type": "boolean", "default": false },
        "extensions": { "type": "array", "items": { "type": "string", "pattern": "^\\*\\.[a-z0-9]+$" } }
      }
    },

    "config": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "dest":      { "type": "string", "minLength": 1 },
        "nativeDest":{ "type": "string",
                       "description": "Destination quand launch.path n'est pas 'flatpak' (mgba)." },
        "generator": { "type": "string", "pattern": "^generator\\.py$" }
      }
    },

    "controllers": {
      "type": "object", "required": ["maxPlayers", "strategy"],
      "additionalProperties": false,
      "properties": {
        "maxPlayers": { "type": "integer", "minimum": 0, "maximum": 4 },
        "strategy": {
          "enum": ["rewrite-player-block", "sdl-index-clone", "guid-rebind",
                   "snapshot-restore", "snapshot-or-synth", "none"]
        },
        "target":  { "type": ["string", "array"], "items": { "type": "string" } },
        "multitap":{ "type": "object", "additionalProperties": false,
                     "properties": { "section": { "type": "string" },
                                     "key": { "type": "string" },
                                     "value": { "type": "string" },
                                     "fromPlayer": { "type": "integer" } } },
        "seedMustNotContain": { "type": "array", "items": { "type": "string" } }
      }
    },

    "scraper": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "tgdbId":        { "type": "integer" },
        "screenscraper": { "type": "array", "items": { "type": "integer" } },
        "libretro":      { "type": "array", "items": { "type": "string" } },
        "mediaAlias":    { "type": "array", "items": { "type": "string" } }
      }
    },

    "overlay": {
      "type": "object", "required": ["wmClass"], "additionalProperties": false,
      "properties": {
        "wmClass": { "type": "object", "additionalProperties": false,
                     "properties": { "linux": { "type": "array",
                                                "items": { "type": "string" } } } },
        "asset":   { "type": "string" }
      }
    },

    "packages": { "type": "object", "additionalProperties": false,
                  "properties": { "pacman": { "type": "array",
                                              "items": { "type": "string" } } } },

    "sources": { "type": "array", "items": {
      "type": "object", "required": ["git", "dest"], "additionalProperties": false,
      "properties": { "git":   { "type": "string", "format": "uri" },
                      "dest":  { "type": "string" },
                      "owner": { "enum": ["user", "root"], "default": "user" } } } },

    "secrets": { "type": "array", "items": {
      "type": "object", "required": ["key", "label"], "additionalProperties": false,
      "properties": { "key":    { "type": "string", "pattern": "^[A-Z][A-Z0-9_]*$" },
                      "label":  { "type": "string" },
                      "hidden": { "type": "boolean", "default": false },
                      "help":   { "type": "string" } } } },

    "files": { "type": "array", "items": {
      "type": "object", "required": ["dest"], "additionalProperties": false,
      "properties": { "src":      { "type": "string" },
                      "template": { "type": "string" },
                      "dest":     { "type": "string" },
                      "owner":    { "enum": ["user", "root"], "default": "user" },
                      "mode":     { "type": "string", "pattern": "^[0-7]{3,4}$" },
                      "when":     { "type": "string", "pattern": "^!?secrets\\.[A-Z][A-Z0-9_]*$" } },
      "oneOf": [ { "required": ["src"] }, { "required": ["template"] } ] } },

    "services": { "type": "array", "items": {
      "type": "object", "required": ["unit", "scope"], "additionalProperties": false,
      "properties": { "unit":   { "type": "string" },
                      "scope":  { "enum": ["user"] },
                      "enable": { "type": "boolean", "default": true } } } },

    "postInstall": { "type": "array", "items": {
      "type": "object", "required": ["run"], "additionalProperties": false,
      "properties": { "run":       { "type": "string" },
                      "label":     { "type": "string" },
                      "timeoutSec":{ "type": "integer", "minimum": 1, "maximum": 300,
                                     "default": 120 },
                      "when":      { "type": "string",
                                     "pattern": "^!?secrets\\.[A-Z][A-Z0-9_]*$" } } } }
  },

  "allOf": [
    { "if":   { "properties": { "kind": { "const": "emulator" } } },
      "then": { "required": ["roms"] } },
    { "if":   { "properties": { "kind": { "const": "app" } } },
      "then": { "not": { "required": ["roms"] } } }
  ]
}
```

Notes de schéma :

- `seed/`, `logo.png`/`logo.svg` et `tests/` sont **implicites** : présents ou
  absents sur le disque, jamais déclarés. Pas de champ.
- `scope` de `services` n'accepte que `"user"`. C'est délibéré :
  `arch.sh:668` documente le bug où créer l'arborescence systemd en root a
  rendu `~/.config` `root:root` et empêché le kiosque de démarrer. Un pack ne
  peut pas demander une unité système.
- `install` est **optionnel** : `youtube` n'installe rien (il utilise le firefox
  du bloc `packages`) ; c'est `provider: "none"` ou pas de bloc du tout.
- `controllers.multitap.fromPlayer` porte le seuil (3 pour PS1/PS2). Il est dans
  le pack et non dans le code, comme demandé.

### 1.4 Les six packs

#### `catalog/dolphin/` — flatpak nu, multi-joueur

```
catalog/dolphin/
  pack.json
  logo.png                     ← assets/logos/gamecube.png
  seed/                        ← emu-configs/dolphin/
    Dolphin.ini  GFX.ini  Qt.ini  Logger.ini  DSUClient.ini
    FreeLook.ini  FreeLookController.ini  GBA.ini
    GCKeyNew.ini  GCPadNew.ini  WiimoteNew.ini
    RetroAchievements.ini  TimePlayed.ini
  generator.py
  tests/
    test_generator.py
    fixtures/GCPadNew.before.ini   fixtures/GCPadNew.expected.ini
    fixtures/WiimoteNew.before.ini fixtures/WiimoteNew.expected.ini
```

```json
{
  "id": "dolphin",
  "kind": "emulator",
  "label": "GameCube / Wii",
  "platform": "GameCube/Wii",
  "color": "#ff8c00",

  "install": { "provider": "flatpak", "appId": "org.DolphinEmu.dolphin-emu" },

  "launch": { "path": "flatpak", "args": "run org.DolphinEmu.dolphin-emu -b" },

  "roms": {
    "dir": "emu/dolphin",
    "extensions": ["*.iso", "*.gcm", "*.rvz", "*.wbfs", "*.wad", "*.zip"]
  },

  "config": {
    "dest": "@FLATPAK_CONFIG@/dolphin-emu",
    "generator": "generator.py"
  },

  "controllers": {
    "maxPlayers": 4,
    "strategy": "guid-rebind",
    "target": ["GCPadNew.ini", "WiimoteNew.ini"],
    "seedMustNotContain": ["Device = SDL/", "Device = evdev/"]
  },

  "scraper": {
    "tgdbId": 2,
    "screenscraper": [13, 16],
    "libretro": ["Nintendo - GameCube", "Nintendo - Wii"],
    "mediaAlias": ["gamecube", "wii"]
  }
}
```

`strategy: guid-rebind` est un abus de nom pour Dolphin, qui lie par **nom** —
mais la famille « le générateur réécrit la ligne device de la section du joueur »
est la même que Ryujinx. Le générateur du pack porte la mécanique exacte
(`SDL/<dup>/<nom>`, 0-based par nom) ; le `pack.json` ne porte que la politique.
`seedMustNotContain` interdit à la graine de figer un device : c'est la même
faute que le `Device: PS4 Controller 1` de RPCS3, et `emu-configs/dolphin/`
**la commet déjà** (voir §3).

#### `catalog/duckstation/` — AppImage GitHub, multitap

```
catalog/duckstation/
  pack.json
  logo.png                     ← assets/logos/ps1.png
  seed/settings.ini            ← emu-configs/duckstation/settings.ini
  generator.py
  tests/
    test_generator.py
    fixtures/settings.before.ini
    fixtures/settings.p2.expected.ini
    fixtures/settings.p3.expected.ini   ← multitap (non mesurable ici, 2 pads)
```

```json
{
  "id": "duckstation",
  "kind": "emulator",
  "label": "PlayStation",
  "platform": "PS1",
  "color": "#0046ff",

  "install": {
    "provider": "github-asset",
    "repo": "stenzek/duckstation",
    "asset": "DuckStation-x64.AppImage",
    "dest": "bin/duckstation.AppImage",
    "magic": "ELF",
    "mode": "755",
    "version": "latest"
  },

  "packages": { "pacman": ["fuse2"] },

  "launch": {
    "path": "bin/duckstation.AppImage",
    "args": "-nogui -fullscreen",
    "preferIfPresent": { "path": "lib/duck", "args": "-nogui -fullscreen" }
  },

  "roms": {
    "dir": "emu/duckstation",
    "extensions": ["*.bin", "*.iso", "*.img", "*.cue", "*.chd", "*.pbp", "*.zip"]
  },

  "config": {
    "dest": "@HOME@/.local/share/duckstation",
    "generator": "generator.py"
  },

  "controllers": {
    "maxPlayers": 4,
    "strategy": "sdl-index-clone",
    "target": "settings.ini",
    "multitap": {
      "section": "ControllerPorts", "key": "MultitapMode",
      "value": "Port1Only", "fromPlayer": 3
    }
  },

  "overlay": {
    "wmClass": { "linux": ["duck", "duckstation-qt", "duckstation", "DuckStation",
                           "org.duckstation.DuckStation", "AppRun.wrapped"] },
    "asset": "duckstation.png"
  },

  "scraper": {
    "tgdbId": 10,
    "screenscraper": [57],
    "libretro": ["Sony - PlayStation"],
    "mediaAlias": ["psx"]
  }
}
```

Deux points. `preferIfPresent` est **inversé** par rapport à RPCS3 : ici le
lanceur principal est l'AppImage que l'installeur pose, et `lib/duck` (le binaire
natif de la machine de référence, hors git) est la préférence. C'est ce que
`flatpakify-systems.sh:45` fait aujourd'hui à l'envers — `systems.json.dist` dit
`lib/duck` et la passe REWRITE le remplace. Exprimer le nominal comme nominal
supprime la réécriture. `fuse2` est dans `packages` et non dans `install`
(`arch.sh:579` : `pacman_optional fuse2`, sans quoi l'AppImage type-2 ne se
monte pas).

#### `catalog/xenia/` — archive + wine

```
catalog/xenia/
  pack.json
  logo.png                     ← assets/logos/xenia.png
  (pas de seed/ : la config de Xenia est portable et vit à côté de l'exe,
   emu-configs/xenia/ n'existe pas dans le dépôt)
  (pas de generator.py : aucun profilage manette — voir §5)
```

```json
{
  "id": "xenia",
  "kind": "emulator",
  "label": "Xbox 360",
  "platform": "X360",
  "color": "#107c10",

  "install": {
    "provider": "github-archive",
    "repo": "xenia-canary/xenia-canary-releases",
    "asset": "xenia_canary_windows_.zip",
    "assetPattern": "windows",
    "dest": "lib/xenia",
    "entrypoint": "xenia_canary.exe",
    "magic": "PK",
    "requires": ["wine", "unzip", "p7zip"],
    "version": "latest"
  },

  "launch": {
    "path": "/usr/bin/wine",
    "args": "lib/xenia/xenia_canary.exe --fullscreen=true"
  },

  "roms": { "dir": "emu/xenia", "extensions": ["*.iso", "*.xex"] },

  "config": { "dest": "@GAMECORE_PATH@/lib/xenia" },

  "controllers": { "maxPlayers": 0, "strategy": "none" },

  "scraper": {
    "tgdbId": 15,
    "screenscraper": [33],
    "libretro": ["Microsoft - Xbox 360"],
    "mediaAlias": ["xbox 360"]
  }
}
```

`asset` **et** `assetPattern` : le premier est l'URL fixe
(`/releases/latest/download/<asset>`, un 302 hors quota), le second sert
uniquement au repli API. C'est exactement la logique de `arch.sh:609-624`, et
c'est le seul provider où le repli mérite vraiment sa place — Xenia Canary tague
ses releases avec un hash de commit, donc le nom d'asset est la seule partie
fixe de l'URL. `requires` est distinct de `packages` : ce sont des paquets requis
par le **provider** (pour extraire et lancer), installés avant le téléchargement.

`maxPlayers: 0` + `strategy: none` dit explicitement « pas de profilage
manette », ce qui rend l'absence de `generator.py` intentionnelle et non un oubli
— le test de symétrie de la phase 1 peut alors l'exiger.

#### `catalog/melonds/` — mono-joueur, index SDL bruts

```
catalog/melonds/
  pack.json
  logo.png                     ← assets/logos/ds.png
  seed/melonDS.toml            ← emu-configs/melonds/melonDS.toml
  generator.py
  tests/
    test_generator.py
    fixtures/melonDS.before.toml
    fixtures/melonDS.ds4.expected.toml     ← D-pad boutons 11-14
    fixtures/melonDS.xbox.expected.toml    ← D-pad hat
    fixtures/sdl2-map.ds4.txt              ← mapping SDL2 capturé (§5)
    fixtures/sdl2-map.xbox.txt
```

```json
{
  "id": "melonds",
  "kind": "emulator",
  "label": "Nintendo DS",
  "platform": "DS",
  "color": "#0096ff",

  "install": { "provider": "flatpak", "appId": "net.kuribo64.melonDS" },

  "launch": {
    "path": "flatpak",
    "args": "run net.kuribo64.melonDS -f",
    "preferIfPresent": { "path": "lib/melon", "args": "-f" }
  },

  "roms": { "dir": "emu/melonds", "extensions": ["*.nds", "*.zip"] },

  "config": {
    "dest": "@FLATPAK_CONFIG@/melonDS",
    "nativeDest": "@HOME@/.config/melonDS",
    "generator": "generator.py"
  },

  "controllers": {
    "maxPlayers": 1,
    "strategy": "snapshot-or-synth",
    "target": "melonDS.toml",
    "seedMustNotContain": ["Instance0.Joystick"]
  },

  "overlay": {
    "wmClass": { "linux": ["melonds", "melonDS", "net.kuribo64.melonDS",
                           "AppRun.wrapped"] },
    "asset": "melonds.png"
  },

  "scraper": {
    "tgdbId": 8,
    "screenscraper": [15],
    "libretro": ["Nintendo - Nintendo DS", "Nintendo - Nintendo DS (Download Play)"],
    "mediaAlias": ["nds"]
  }
}
```

`strategy: snapshot-or-synth` encode l'invariant #6 dans le format : snapshot
s'il existe, **sinon** synthèse — jamais `snapshot_restore(...) or _synth(...)`.
`libretro` prend les **deux** entrées de `scraper.py`, pas la seule de
`systems.json.dist` (divergence D-4, §3). `nativeDest` existe pour melonDS et
mgba, les deux émulateurs que `_flatpak_or_native()` gère.

#### `catalog/twitch/` — le cas d'application le plus lourd

```
catalog/twitch/
  pack.json
  logo.png                     ← assets/logos/twitch.png
  files/
    embertv-config.json.tmpl
    embertv-config.demo.json
    twitch-tv.user.js          ← install/firefox-profiles/twitch-tv.user.js
    embertv.service
  steps/
    make-cert.sh               ← wrapper 3 lignes autour de /opt/Twitch-TV/make-cert.sh
    trust-cert.sh              ← import certutil
```

```json
{
  "id": "twitch",
  "kind": "app",
  "label": "Twitch",
  "platform": "Web",
  "color": "#800080",

  "packages": { "pacman": ["firefox", "nss"] },

  "sources": [
    { "git": "https://github.com/p4v1c/Twitch-TV.git",
      "dest": "/opt/Twitch-TV", "owner": "user" }
  ],

  "secrets": [
    { "key": "TWITCH_CLIENT_ID", "label": "Twitch Client ID", "hidden": false,
      "help": "https://dev.twitch.tv/console/apps — redirect http://localhost:8097" },
    { "key": "TWITCH_CLIENT_SECRET", "label": "Twitch Client Secret", "hidden": true }
  ],

  "files": [
    { "template": "files/embertv-config.json.tmpl",
      "dest": "/opt/Twitch-TV/config.json", "mode": "600", "owner": "user",
      "when": "secrets.TWITCH_CLIENT_ID" },
    { "src": "files/embertv-config.demo.json",
      "dest": "/opt/Twitch-TV/config.json", "mode": "600", "owner": "user",
      "when": "!secrets.TWITCH_CLIENT_ID" },
    { "src": "files/twitch-tv.user.js",
      "dest": "@HOME@/.mozilla/firefox/twitch-tv/user.js",
      "owner": "user", "mode": "644" }
  ],

  "postInstall": [
    { "run": "steps/make-cert.sh",  "label": "EmberTV TLS certificate", "timeoutSec": 60 },
    { "run": "steps/trust-cert.sh", "label": "trust cert in the Firefox NSS db",
      "timeoutSec": 60 }
  ],

  "services": [
    { "unit": "files/embertv.service", "scope": "user", "enable": true }
  ],

  "launch": {
    "path": "firefox",
    "args": "--profile '@HOME@/.mozilla/firefox/twitch-tv' --kiosk 'https://localhost:8097/'"
  },

  "scraper": {}
}
```

Le `.tmpl` est substitué avec les tokens **et** les secrets
(`@secrets.TWITCH_CLIENT_ID@`). `host: "127.0.0.1"` reste écrit en dur dans le
gabarit, et le commentaire d'`arch.sh:700` qui explique pourquoi (EmberTV
n'authentifie rien, un bind LAN donne le compte à tout le Wi-Fi) part avec lui.

Ce qui **ne rentre pas** et reste central : la route Caddy `/twitch/*` (§1.2).

#### `catalog/stremio/` — flatpak à politique de sandbox divergente

```
catalog/stremio/
  pack.json
  logo.png                     ← assets/logos/stremio.png
```

```json
{
  "id": "stremio",
  "kind": "app",
  "label": "Stremio",
  "platform": "Media",
  "color": "#8a5fff",

  "install": { "provider": "flatpak", "appId": "com.stremio.Stremio" },

  "sandbox": { "device": ["all"], "filesystem": ["host"] },

  "sources": [
    { "git": "https://github.com/p4v1c/stremio-gamepad-keyboard.git",
      "dest": "/opt/Stremio", "owner": "user" }
  ],

  "launch": { "path": "bash", "args": "/opt/Stremio/stremio-tv.sh" },

  "scraper": {}
}
```

C'est le pack qui justifie le bloc `sandbox`. Défaut (émulateurs) :
`filesystem: ["@GAMECORE_PATH@"], device: ["all"], socket: ["x11"]`
(`arch.sh:512`). Stremio : `device: ["all"], filesystem: ["host"]`, **sans**
`socket: x11` (`arch.sh:894`). Deux politiques réellement différentes, donc
explicites. Noter que le pack déclare `install` (le client Flatpak, ce que la
sandbox vise) **et** `sources` (le proxy clavier que `launch` lance) : les deux
sont nécessaires, et `stremio-tv.sh` passe un `--url` au client.

---

## 2. Inventaire exhaustif des sites de duplication

Vérifié fichier par fichier. Les sites **absents du tableau du brief** sont
marqués **NOUVEAU**.

### 2.1 Catalogue (id → métadonnées)

| # | Fichier:ligne | Ce qui est redéfini | Couverture |
|---|---|---|---|
| 1 | `install/arch.sh:466` `EMU_FLATPAK` | id → app-id Flatpak | 11 émulateurs |
| 2 | `install/arch.sh:483` | liste ordonnée des ids installés | 11 |
| 3 | `install/arch.sh:488` | steam → `com.valvesoftware.Steam` | 1 |
| 4 | `install/arch.sh:518-581` | bloc sur-mesure DuckStation (AppImage) | 1 |
| 5 | `install/arch.sh:583-647` | bloc sur-mesure Xenia (zip + wine) | 1 |
| 6 | `install/arch.sh:853-854` | app → profil Firefox | 2 |
| 7 | `install/arch.sh:949` | liste des apps filtrables | 4 |
| 8 | `install/arch.sh:983` | liste des dossiers ROMs à créer | 13 + covers |
| 9 | `install/systems.json.dist` | path/args/extensions/logo/couleur/libretro | 13 |
| 10 | `install/apps.json.dist` | idem, applications | 4 |
| 11 | `install/installer-gui/gamecore_installer.py:40` `EMULATORS` | id → libellé + plateforme | 13 |
| 12 | `install/installer-gui/gamecore_installer.py:56` `APPS` | id → libellé + description | 4 |
| 13 | `install/flatpakify-systems.sh:41` `FLATPAK_MAP` | id → (path, args) de repli | 6 |
| 14 | `install/install-emu-configs.sh:29` `DEST` | id → dossier de config | 13 |
| 15 | `install/uninstall.sh:398` `EMU_DEST` | la même map, recopiée | 13 |
| 16 | `verify_emulators.py:3` `FLATPAK_IDS` | app-ids à vérifier | 13 |
| 17 | `backend/services/scraper.py:34` `TGDB_PLATFORM_MAP` | id → id TheGamesDB | 13 |
| 18 | `backend/services/scraper.py:54` `PLATFORM_MAP` | id → systèmes libretro | 11 + 4 fantômes |
| 19 | `backend/services/gamemedia/gamemedia.py:181` `EMULATOR_ALIASES` | id → slug plateforme | 13 + alias |
| 20 | `backend/services/gamemedia/gamescrape.py:750` `SS_SYSTEM_IDS` | slug → systemeid ScreenScraper | 27 |
| 21 | `config/overlays.json` | id → wm_class + géométrie bezel | 6 |
| 22 | **NOUVEAU** `frontend/src/lib/systemColors.ts:1` `SYSTEM_COLORS` | id → couleur | 12 + 8 fantômes |
| 23 | `install/gamecore-install.conf.example:11,14` | listes d'ids en commentaire | 13 + 4 |
| 24 | `install/arch.sh:104-106` | mêmes listes, en commentaire | 13 + 4 |

### 2.2 Chemins de configuration par émulateur — **quatre copies**

| # | Fichier:ligne | Entrées | Remarque |
|---|---|---|---|
| 14 | `install/install-emu-configs.sh:29-43` (+ override mgba l.50) | 13 | la référence |
| 15 | `install/uninstall.sh:398-411` | 13 | copie verbatim, **sans** l'override mgba |
| 25 | **NOUVEAU** `install/apply-multi-ds4.sh:19-22` | 4 | ryujinx, dolphin, pcsx2, duckstation |
| 26 | **NOUVEAU** `backend/services/controller_profiles.py:105-118` + `120-170` | 10 | `RYUJINX_CFG`, `AZAHAR`, `DOLPHIN_DIR`, `CEMU_PROFILES`, `RMG_CFG`, `DUCK_INI`, + les 4 paires `_flatpak_or_native` |

C'est le vrai foyer du bug gopher64 : **quatre** endroits qui doivent s'accorder
sur « où vit la config de tel émulateur », et un cinquième implicite (l'app-id
dans `EMU_FLATPAK`).

### 2.3 Divers — **NOUVEAU**

| # | Fichier:ligne | Ce qui est dupliqué |
|---|---|---|
| 27 | `backend/services/local_media.py:101,125,141,144` | logique média par id (`rpcs3`, `duckstation`) |
| 28 | `install/apply-multi-ds4.sh:71` | `(pcsx2, "pcsx2"), (duck, "duckstation")` — copie de `_TIER0` |
| 29 | `update/linux.sh:363-383` | id `gopher64` + son app-id cible, en dur dans un message |
| 30 | `backend/routers/systems.py:58` `serve_logo` | résout par **nom de fichier**, pas par id de pack |

---

## 3. Divergences détectées

Sept, dont le cas gopher64. Les six autres sont nouvelles.

### D-1 — gopher64 : le slot N64 (confirmé, et pire que décrit)

Le brief décrit une erreur de **chemin**. C'en est aussi une de **format**.

Mesuré sur cette machine :

```
~/.var/app/io.github.gopher64.gopher64/config/gopher64/
    cheats.json          ← IDENTIQUE à emu-configs/gopher64/cheats.json
    config.json          ← 11 147 o, controller_assignment = [null,null,null,null]
    config.json.bak-multids4        (écrit par apply-multi-ds4.sh)

~/.var/app/com.github.Rosalie241.RMG/config/RMG/
    mupen64plus.cfg                 ← ce que RMG lit réellement
    mupen64plus.cfg.bak-ctrlmodel   (écrit par controller_profiles.backup())
```

`cheats.json` est **bit pour bit** la graine du dépôt : la preuve directe que
`install-emu-configs.sh:33` a déployé dans le dossier fantôme. Et
`controller_assignment = [null, null, null, null]` confirme l'invariant #8, sur
cette machine, aujourd'hui.

Le point nouveau : `emu-configs/gopher64/` est au **format gopher64** (JSON,
`input_profiles`), alors que RMG lit un **INI mupen64plus**
(`[Rosalie's Mupen GUI - Input Plugin]`, `[… Profile 0-3]`). **Corriger le chemin
ne suffit pas** — la graine N64 est inexploitable telle quelle. En phase 1,
`catalog/gopher64/seed/` doit soit être re-moissonné au format RMG, soit rester
vide avec la raison écrite dans le pack. Je recommande **vide** : `_rmg_extract`
explique déjà pourquoi rien n'est synthétisé côté N64, et une graine RMG
moissonnée porterait `DeviceName`/`DevicePath`/`DeviceSerial`, donc l'identité
d'une manette précise — exactement ce que `seedMustNotContain` doit interdire.

Sites à corriger : `install-emu-configs.sh:33`, `uninstall.sh:402`,
`flatpakify-systems.sh:48`, `verify_emulators.py:9`.

### D-2 — mgba natif : **le même bug, jamais signalé** — et cette machine est touchée

`install-emu-configs.sh:50-52` a une branche native :

```bash
if [[ ! -d "$HOME/.var/app/io.mgba.mGBA" && -d "$HOME/.config/mgba" ]]; then
  DEST[mgba]="$HOME/.config/mgba"
fi
```

`uninstall.sh:404` **n'a pas cette branche** — il ne connaît que le chemin
flatpak. Sur une machine qui fait tourner le mgba d'Arch, l'installeur écrit
dans `~/.config/mgba` et la désinstallation n'y touche jamais : la config
GameCore reste, et les `*.bak-preinstall` de l'utilisateur ne sont **jamais
restaurés**. Perte silencieuse de la config d'origine.

Mesuré ici :

```
io.mgba.mGBA installé en flatpak ?   NON
/usr/bin/mgba-qt                      présent
~/.config/mgba/config.ini.bak-ctrlmodel   présent (GameCore a écrit là)
~/.var/app/io.mgba.mGBA/config/mgba/      présent (résidu d'un déploiement plus ancien)
```

Les deux arbres coexistent. C'est la même classe de faute que gopher64 : deux
consommateurs, une seule vérité, aucun mécanisme pour les tenir ensemble.

### D-3 — `systemColors.ts` diverge de `systems.json.dist`

| id | `systems/apps.json.dist` | `frontend/src/lib/systemColors.ts` |
|---|---|---|
| `pcsx2` | `#003087` | `#0046ff` |
| `rpcs3` | `#00439c` | `#0046ff` |
| `xenia`, `shadps4`, `twitch`, `stremio`, `youtube` | définis | **absents** |

Latent et non actif : `SystemCard.tsx:6` fait
`system.color || SYSTEM_COLORS[id] || '#7c3aed'`, donc le JSON gagne tant qu'il
porte `color`. La divergence mord dès qu'un pack omet `color` — et le schéma
ci-dessus rend `color` obligatoire précisément pour ça. `systemColors.ts` doit
devenir **généré**, ou disparaître.

### D-4 — `melonds` : les systèmes libretro ne concordent pas

- `install/systems.json.dist:197` : `["Nintendo - Nintendo DS"]`
- `backend/services/scraper.py:55` : `["Nintendo - Nintendo DS", "Nintendo - Nintendo DS (Download Play)"]`

Le pack doit prendre les deux (le scraper est le consommateur réel).

### D-5 — `xenia` absent de `scraper.PLATFORM_MAP`

`systems.json.dist:237` déclare `["Microsoft - Xbox 360"]`, mais `PLATFORM_MAP`
(`scraper.py:54`) n'a **aucune** entrée `xenia`. Le repli jaquettes libretro ne
s'active donc jamais pour la Xbox 360, alors que `TGDB_PLATFORM_MAP` a bien
`xenia: 15`. Deux tables, deux vérités, sur le même id.

### D-6 — quatre ids fantômes dans `scraper.PLATFORM_MAP`

`retroarch`, `snes9x`, `nestopia`, `mame` sont dans `PLATFORM_MAP` et
n'existent dans aucun `systems.json`. Inoffensif, mais c'est du catalogue
non catalogué : sans pack, personne ne sait s'ils sont morts ou à venir.
`systemColors.ts` en a huit autres (`snes`, `nes`, `ps1`, `n64`, `gba`,
`genesis`, `mame`, `nds`).

### D-8 — un nom d'appareil personnel dans la graine melonDS

Trouvé en implémentant le contrôle `seedMustNotContain` :
`emu-configs/melonds/melonDS.toml:14` portait

```toml
[Mic]
Device = "JBL Charge 2"
```

Une enceinte Bluetooth appairée à la machine de moissonnage, committée dans un
dépôt public. Même classe que `/home/pavic`, jamais signalée. Aucune autre boîte
n'a ce périphérique : melonDS y pointait son micro dans le vide. Remis à `""`.

### D-7 — `flatpakify-systems.sh` : la mine documentée par le brief, confirmée

`FLATPAK_MAP["gopher64"] = ("flatpak", "run io.github.gopher64.gopher64 -f")`
(`flatpakify-systems.sh:48`) pointe l'ancien app-id. Inoffensif **aujourd'hui
seulement** parce que `systems.json.dist` dit déjà `path: "flatpak"` et que
`launcher_exists("flatpak")` retourne `True` avant (l.72-73), donc la réécriture
n'a jamais lieu. Le jour où le slot N64 repasse par un binaire natif, elle a
lieu, et elle écrit un app-id que personne n'installe. Confirmé par lecture ;
non déclenchable sur cette machine sans modifier `systems.json`.

---

## 4. Migration `emu-configs/` + `assets/logos/` → `catalog/`

### 4.1 Table de migration

| Source | Destination | Note |
|---|---|---|
| `emu-configs/<id>/**` | `catalog/<id>/seed/**` | 11 émulateurs ont une graine |
| `emu-configs/gopher64/**` | *(supprimé)* | mauvais format, voir D-1 |
| `assets/logos/3ds.png` | `catalog/azahar/logo.png` | renommage id, pas plateforme |
| `assets/logos/wiiu.png` | `catalog/cemu/logo.png` | |
| `assets/logos/gamecube.png` | `catalog/dolphin/logo.png` | |
| `assets/logos/switch.png` | `catalog/ryujinx/logo.png` | |
| `assets/logos/ps1.png` | `catalog/duckstation/logo.png` | |
| `assets/logos/ps2.png` | `catalog/pcsx2/logo.png` | |
| `assets/logos/ps3.png` | `catalog/rpcs3/logo.png` | |
| `assets/logos/psp.png` | `catalog/ppsspp/logo.png` | |
| `assets/logos/n64.png` | `catalog/gopher64/logo.png` | id conservé (délibéré) |
| `assets/logos/ds.png` | `catalog/melonds/logo.png` | |
| `assets/logos/gba.png` | `catalog/mgba/logo.png` | |
| `assets/logos/xenia.png` | `catalog/xenia/logo.png` | |
| `assets/logos/shadps4.png` | `catalog/shadps4/logo.png` | |
| `assets/logos/steam.png` | `catalog/steam/logo.png` | |
| `assets/logos/twitch.png` | `catalog/twitch/logo.png` | |
| `assets/logos/stremio.png` | `catalog/stremio/logo.png` | |
| `assets/logos/snes.png`, `nes.png` | *(restent)* | aucun pack — ids fantômes D-6 |
| `install/firefox-profiles/*.user.js` | `catalog/{twitch,youtube}/files/` | |
| `assets/overlays/<id>.png` | **restent où ils sont** | géométrie ≠ pack |

`youtube` n'a **pas** de logo aujourd'hui (`apps.json.dist:14-22` n'a pas
d'`iconPath`). Le test de symétrie de la phase 1 exigeant un logo par pack, il
faut soit en fournir un, soit rendre le logo optionnel pour `kind: app`. Je
recommande **fournir le logo** et garder la règle stricte.

### 4.2 Le littéral `/home/pavic`

Trois occurrences, toutes supprimées par la migration :

| Site | Devient |
|---|---|
| `install/apps.json.dist:21,32` (chemins de profils Firefox) | `@HOME@` dans `catalog/{youtube,twitch}/pack.json` |
| `install/arch.sh:946` (`sed -i "s|/home/pavic|$USER_HOME|g"`) | supprimé — plus de littéral à rattraper |
| `install/install-emu-configs.sh:19,94-95` (`SRC_HOME` + passe sed) | remplacé par la substitution de tokens de `configgen/seed.py` |

Vérification CI : `grep -rn '/home/pavic' catalog/ install/ config/` doit ne
rien retourner. À ajouter au workflow.

### 4.3 Ce que devient chaque exclusion de `update/linux.sh`

L'exclusion des logos est celle qui change de sens. Aujourd'hui
(`update/linux.sh:143-149`) :

```bash
rsync -a \
  --exclude='.venv/' --exclude='emu/' --exclude='config/' \
  --exclude='assets/overlays/' --exclude='assets/logos/' \
  "${SRC_DIR}/" "${GAMECORE_PATH}/"
```

| Exclusion | Aujourd'hui | Après | Pourquoi |
|---|---|---|---|
| `.venv/` | exclue | **inchangée** | reconstruite par pip |
| `emu/` | exclue | **inchangée** | ROMs, données utilisateur, plusieurs Go |
| `config/` | exclue | **inchangée, mais `config/catalog.d/` en devient un bénéficiaire explicite** — c'est ce qui préserve les packs locaux |
| `assets/overlays/` | exclue | **inchangée** | bezels téléversés par le ROM manager |
| `assets/logos/` | exclue | **exclusion conservée, mais le répertoire n'est plus la source** | les logos livrés vivent dans `catalog/<id>/logo.png`, qui n'est **pas** exclu → un logo corrigé arrive enfin par OTA. `assets/logos/` reste exclu pour continuer à protéger les logos ajoutés à la main, qui deviennent une **surcharge** : `serve_logo` cherche `assets/logos/<id>.png` d'abord, `catalog/<id>/logo.png` ensuite. |
| — | — | **ajout : `catalog/` n'est pas exclu** | c'est du contenu livré, il *doit* être écrasé |
| — | — | **ajout : `--exclude='config/catalog.d/'` est déjà couvert par `config/`** | rien à faire, mais à écrire dans le commentaire |

Conséquence pour `backend/routers/systems.py:58`. `serve_logo(filename)` prend
aujourd'hui un **nom de fichier** ; il doit prendre un **id de pack** :

```python
@router.get("/assets/logos/{system_id}")
def serve_logo(system_id: str):
    # L'id vient de l'URL : il ne doit jamais composer un chemin sans contrôle.
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", system_id):
        raise HTTPException(404)
    for candidate in (ASSETS_DIR / "logos" / f"{system_id}.png",      # surcharge locale
                      CATALOG_D / system_id / "logo.png",             # pack local
                      CATALOG   / system_id / "logo.png"):            # pack livré
        if candidate.is_file():
            return FileResponse(candidate)
    raise HTTPException(404)
```

La regex est la protection anti-traversée : elle interdit `.`, `/` et `..`
d'entrée, plutôt que de normaliser après coup.

---

## 5. Rapport de comparaison Batocera / GameCore

Référence lue : `batocera.linux` HEAD, `package/batocera/core/batocera-configgen/`.

### 5.0 La différence de structure qui explique tout le reste

Batocera **possède sa pile SDL**. Une seule libSDL sert EmulationStation et les
émulateurs, et `controller.py:266` régénère un `gamecontrollerdb.txt` par session
depuis les entrées mesurées par ES, passé aux émulateurs via
`SDL_GAMECONTROLLERCONFIG`. Dans ce monde, « le GUID du pad » et « le nom du
pad » sont des valeurs **uniques** — c'est pourquoi `Controller`
(`controller.py:110-127`) porte un seul `guid` et un seul `real_name`.

GameCore ne possède pas sa pile SDL. Le même pad a donc **plusieurs** identités
selon le consommateur. Attention à la nature des lignes ci-dessous — elles ne sont
**pas** toutes de même nature :

- lignes 1-2 : **mesures live et simultanées** (ce jour, même DualShock 4) ;
- lignes 3-4 : **contenu des configs écrites par les émulateurs eux-mêmes**, à des
  dates antérieures (azahar 03/08, Cemu 24/07) — vérité terrain sur ce qui est
  en place, **pas** une mesure concurrente ;
- ligne 5 : formule, pas mesure.

| Source | bus | crc | vendor | product | queue |
|---|---|---|---|---|---|
| host libSDL3 / sdl2-compat (live) | `0x0005` | `0xe58f` | `054c` | `09cc` | `00006800` |
| libSDL2 embarquée par Ryujinx (live) | `0x0003` | `0xe58f` | `054c` | `09cc` | `00006800` |
| **azahar**, config écrite le 03/08 | `0x0003` | `0xe58f` | `054c` | `09cc` | `00006800` |
| **Cemu**, config écrite le 24/07 | `0x0005` | `0x519b` | `054c` | `09cc` | `00810000` |
| formule Batocera (synthèse evdev) | `0x0005` | `0x0000` | `054c` | `09cc` | `00810000` |

**Quatre GUID pour un pad, et aucun des trois axes (bus, CRC, queue) ne covarie
avec les autres.** Ce qui est établi et ce qui ne l'est pas :

- **Établi, par mesure simultanée** : la libSDL2 embarquée par Ryujinx et la SDL
  de l'hôte répondent **deux GUID différents pour le même pad au même instant**
  (bus `0x0003` vs `0x0005`). Cela suffit à lui seul à disqualifier un champ
  `guid` unique.
- **Établi, par lecture des configs** : ce que Cemu et azahar ont en place
  aujourd'hui ne correspond à aucune des deux réponses live. Substituer la
  réponse de l'hôte réécrirait donc une config qui fonctionne.
- **NON établi — hypothèse** : que la SDL de Cemu *diverge aujourd'hui* de celle
  de l'hôte. Vérification faite, **Cemu n'embarque aucune libSDL** (il prend celle
  du runtime). L'écart de CRC (`0x519b` vs `0xe58f` — le CRC16 porte sur le nom du
  périphérique) et la queue `00810000` (= version evdev `0x8100`, donc backend
  joystick historique, là où `00006800` est une signature HIDAPI) s'expliquent
  aussi bien par une **version de SDL différente au moment de l'écriture**, il y
  a onze jours. Trancher demanderait de relancer Cemu et de relire ce qu'il
  écrit — non fait.

La conclusion pour le refactor ne change pas (snapshot plutôt que substitution),
mais elle repose sur le deuxième point, pas sur le troisième.

**Conclusion structurelle : le modèle `Input`/`Controller` de Batocera ne peut
pas porter la vérité de GameCore.** Un seul champ `guid` là où il en faut un par
consommateur. C'est le critère que le brief pose — « il doit pouvoir porter le
GUID SDL2 exact de Ryujinx et le nom SDL3 de RPCS3 sans les aplatir » — et le
modèle échoue au test. **Non adopté.**

Ce que je retiens en revanche de la structure : **un générateur par émulateur**,
et une abstraction manette commune — mais dont le type d'identité est
`resolve_name(consumer)` / `resolve_guid(consumer)`, résolus **par
consommateur**, pas un scalaire.

### 5.1 Par émulateur

#### RPCS3 — *même fait, même encodage* (confirmation indépendante)

`rpcs3Controllers.py:578-583` :

```python
if ctrlname in controller_counts: controller_counts[ctrlname] += 1
else:                             controller_counts[ctrlname] = 1
f.write(f'  Device: {ctrlname} {controller_counts[ctrlname]}\n')
```

Compteur **1-based, par nom** — exactement `dup_index + 1` de `_rpcs3()`. Deux
bases de code arrivées séparément au même fait. L'invariant #2 est confirmé.

Trois divergences, toutes tranchées en faveur de GameCore :

1. **Source du nom.** Batocera écrit `pad.real_name` (le nom de *sa* SDL) et
   force les émulateurs à s'y conformer en réécrivant la base. GameCore résout
   contre la libSDL3 du système. Sur une machine flatpak, la méthode Batocera
   n'est pas disponible — **garder GameCore**.
2. **Portée de l'écriture.** Batocera réécrit `Default.yml` **en entier**, les 7
   joueurs, à chaque lancement. Incompatible avec la philosophie
   `.bak-preinstall` du dépôt. **Garder GameCore** (réécriture de la seule ligne
   `Device:` du bloc du joueur).
3. **Handler natif DualShock/DualSense — à reprendre, mais pas comme ça.**
   Batocera peut écrire `Handler: DualShock 4` + `Device: "DS4 Pad #1"` au lieu
   de `Handler: SDL`, ce qui donne rumble, motion et touchpad par le pilote natif
   de RPCS3. GameCore n'utilise **jamais** ce chemin — alors qu'`arch.sh:1020-1034`
   installe déjà les règles udev hidraw DS4 « needed by RPCS3's native DS4 pad
   handler (rumble, motion, correct mapping) ». **La règle udev est du poids mort
   aujourd'hui.**

   Mais la sélection de Batocera se fait par **liste blanche de GUID**
   (`rpcs3Controllers.py:323-339`), et mesuré ici : mon DS4 est
   `05008fe54c050000cc09000000006800`, CRC neutralisé
   `050000004c050000cc09000000006800`. La liste de Batocera contient
   `050000004c050000cc09000000010000` et `…00810000`. **Aucune correspondance** —
   les octets de queue diffèrent. Le chemin natif de Batocera ne se
   déclencherait donc **pas** pour ce DualShock 4 ; il retomberait sur SDL.
   Démonstration mesurée qu'une liste blanche de GUID est fragile.

   → **Reprendre l'idée, jeter le mécanisme** : si GameCore adopte le handler
   natif, la sélection doit se faire sur `vendor:product` (`054c:05c4/09cc/0ba0`
   → DS4, `054c:0ce6/0df2` → DualSense), jamais sur un GUID complet. À traiter
   comme une **fonctionnalité à part**, signalée comme telle, pas comme un effet
   de bord du refactor.

#### Dolphin — *même compteur, backend différent*

`dolphinControllers.py:527-531` :

```python
nsamepad = double_pads.get(pad.real_name.strip(), 0)
double_pads[pad.real_name.strip()] = nsamepad + 1
f.write(f"Device = evdev/{nsamepad}/{pad.real_name.strip()}\n")
```

Compteur **0-based, par nom** — identique à GameCore. Invariant #2 confirmé une
seconde fois, indépendamment.

Mais Batocera pilote Dolphin par son backend **evdev**, GameCore par **SDL**.
Deux espaces de noms différents, et l'écart est concret sur cette machine :
evdev appelle mon DS4 `Wireless Controller`, SDL3 l'appelle `PS4 Controller`.
Les chaînes de Batocera ne sont donc **pas transposables**. Choix de conception,
pas fait : le backend evdev donne accès aux capteurs de mouvement par
périphérique (`IMUGyroscope/*`, l.623-635), le backend SDL donne des jetons de
rôle indépendants du modèle. La graine `emu-configs/dolphin/` et `_GCPAD_BODY`
sont déjà en jetons de rôle SDL → **garder SDL**, cohérence avec l'existant.

#### PCSX2 / DuckStation — *même fait pour le multitap, divergence réelle sur l'index*

Multitap, `duckstationGenerator.py:321-326` : `if nplayer > 2 → Port1Only`,
`if nplayer > 4 → BothPorts`. GameCore (`_TIER0`) : `if i >= 3 → Port1Only`.
**Même seuil, même valeur.** Invariant #7 confirmé. PCSX2 idem :
`pcsx2Generator.py:654` écrit `MultitapPort1 = true` sous `[Pad]`, comme
`_TIER0["pcsx2"]`. *(Non mesuré : je n'ai que deux pads.)*

Batocera gate le tap sur un réglage utilisateur (`pcsx2_multitap`, défaut 2 = pas
de tap même à 3 pads) ; GameCore l'active automatiquement au slot 3. Pour une
console de salon, **garder GameCore**.

**La divergence qui compte** : `duckstationGenerator.py:328` écrit
`SDL-{pad.index}` — l'index **global** du joystick. GameCore écrit
`SDL-{i-1}` — le numéro de joueur moins un (`_tier0_ini`, `p1.replace("SDL-0/",
f"SDL-{i-1}/")`). Les deux ne coïncident que si l'ordre des joueurs est l'ordre
d'énumération SDL.

Sur cette machine ils coïncident (SDL3 énumère `[0] = DS4`, `[1] = Xbox` ; les
slots joueur suivent le même ordre). **Je n'ai pas pu produire un désaccord sans
débrancher/rappairer les pads, ce que je me suis interdit.**

Mais l'analyse tranche autrement : Batocera n'a raison que par **couplage
temporel** — il génère la config puis lance l'émulateur dans la foulée, donc
`pad.index` est encore valide. GameCore écrit à la **connexion**, longtemps avant
le lancement ; ni `pad.index` ni `i-1` n'est connaissable à l'avance. Adopter
`pad.index` exigerait de déplacer la génération au lancement — ce que le brief
interdit explicitement.

→ **Garder `i-1`**, mais le documenter comme limite connue, et c'est l'argument
le plus fort en faveur du **troisième point de déclenchement** que le brief
mentionne (`ProcessManager.launch()`, `process_manager.py:329`) : recalculer
l'index SDL juste avant le lancement est la seule façon correcte, et elle ne
casse pas les sections possédées.

#### Ryujinx — *Batocera est mesurablement faux ; ne pas adopter*

`ryujinxGenerator.py:156-174` **synthétise** le GUID depuis evdev :

```python
ctrlUUID = f"{pad.index}-{bustype}-{vendor}-0000-{product}-0000{version}0000"
```

C'est exactement l'approche que GameCore a retirée. Test décisif, formule
transcrite verbatim et confrontée à la vérité terrain (la libSDL2 embarquée par
Ryujinx, celle que Ryujinx utilisera) :

| pad | GameCore (lu depuis la SDL2 de Ryujinx) | Batocera (synthétisé) | |
|---|---|---|---|
| DualShock 4 `054c:09cc` | `0-00000003-054c-0000-cc09-000000006800` | `0-00000005-054c-0000-cc09-000000810000` | **FAUX** |
| Xbox One S `045e:02fd` | `0-00000005-045e-0000-fd02-000003090000` | `0-00000005-045e-0000-fd02-000003090000` | juste |

La formule tombe juste sur la Xbox et faux sur la DualShock 4 — précisément sur
le pad piloté par HIDAPI, où SDL2 2.30 annonce le bus USB et une signature de
pilote au lieu de la version evdev. Deux erreurs indépendantes et simultanées
(bus **et** queue).

Bénéfice secondaire : cette mesure **recoupe** la note de
`09-gotchas.md` (« le même pad Xbox est `0x05` en Bluetooth et `0x03` en USB,
alors qu'une DualShock 4 lit `0x03` dans les deux cas parce que HIDAPI la
pilote ») par une voie entièrement différente. La doc est exacte.

Batocera utilise en outre `pad.index` comme préfixe `dup`, là où Ryujinx compte
**par GUID** (`SDL2GamepadDriver.GenerateGamepadId`). Deuxième raison de ne pas
adopter. **Garder GameCore intégralement** (invariant #4 confirmé).

#### azahar / Cemu — *Batocera synthétise ; testé ; le snapshot reste*

Le brief demande de tester plutôt que de conclure. Les deux synthétisent, donc
les deux sont testables.

**Cemu** — `cemuControllers.py:262` : `uuid = f"{guid_n[pad.index]}_{pad.guid}"`,
compteur 0-based par GUID. Le **format** est confirmé (c'est bien ce que décrit
le commentaire `_ANY_GUID_RE` de GameCore). Mais `pad.guid` est le GUID de la SDL
d'ES. Vérité terrain lue dans `controller0.xml` de cette machine :

```
<uuid>0_05009b514c050000cc09000000810000</uuid>
<display_name>PS4 Controller</display_name>
```

À comparer à ce que la SDL3 de l'hôte répondrait :
`05008fe54c050000cc09000000006800`. **CRC et queue diffèrent tous les deux.**
Sur Batocera ça marche parce que la SDL d'ES *est* celle de Cemu ; sur GameCore,
substituer la réponse de l'hôte écrirait un périphérique que Cemu ne voit pas.
→ **Snapshot conservé.** Invariant #5 vérifié par la mesure.

**azahar** — synthétise les bindings depuis les entrées enregistrées par ES
(`azaharGenerator.py:244`, `setButton`). Vérité terrain, `qt-config.ini` :

```
profiles\1\button_a ="button:0, engine:sdl, guid:03008fe54c050000cc09000000006800, port:0"
profiles\1\button_up="button:11,engine:sdl, guid:03008fe54c050000cc09000000006800, port:0"
```

Deux observations. Le GUID d'azahar est **identique** à celui que rend la SDL2
embarquée par Ryujinx — donc GameCore *saurait* le calculer (`_sdl2_probe` avec
une lib bundlée). Mais les bindings sont des **index bruts**, et là est le
vrai obstacle : `button_up = 11`, `down = 12`, `left = 13`, `right = 14`.

Or c'est **exactement** la table codée en dur dans `_MELONDS_DPAD_BUTTONS` pour
`054c:09cc` — `{'Up': 11, 'Down': 12, 'Left': 13, 'Right': 14}` — dérivée de
melonDS. Deux émulateurs indépendants, les mêmes numéros, sur cette machine.
Pendant ce temps la couche GameController de la SDL3 hôte annonce
`dpup:h0.1` (un hat) et `b11 = touchpad`.

→ **Confirmation mesurée que la synthèse « fais confiance au jeton hat de SDL »
serait fausse pour une DualShock 4**, et que l'exception `_MELONDS_DPAD_BUTTONS`
est juste. Le snapshot azahar reste ; je note qu'azahar est le **meilleur
candidat** à une future promotion vers la synthèse (son GUID est calculable),
mais ce serait une fonctionnalité à part, avec ses propres mesures.

#### melonDS — *Batocera ne synthétise pas du tout*

`melondsGenerator.py:82` : `"Joystick": {}`. La table est laissée **vide** ;
seuls des réglages numériques y sont réinjectés plus loin (l.228). Batocera
délègue à SDL et aux défauts de melonDS.

→ La question « ta restauration est-elle superflue ? » a une réponse nette :
**non**, GameCore fait strictement plus que Batocera ici. Rien à reprendre.

#### gopher64 / RMG, ppsspp, xenia, shadps4

Batocera pilote le N64 par `mupenControllers.py` (générateur mupen64plus
complet), ce que GameCore ne fait pas — cohérent avec l'invariant #8
(« gopher64 n'est PAS couvert »). Reprendre serait une fonctionnalité à part.
`ppsspp` : Batocera a `ppssppControllers.py` ; GameCore a délibérément un fichier
statique (un `controls.ini` sans identité de périphérique suffit) — position
défendable, à conserver. `xenia` : le générateur Batocera n'écrit pas de mapping
manette. `shadps4` : pas de générateur Batocera.

### 5.2 Bilan

| Sujet | Verdict | Fondé sur |
|---|---|---|
| Modèle `Input`/`Controller` de Batocera | **non adopté** | mesure : 4 GUID pour un pad |
| Un générateur par émulateur | **adopté** | structure |
| Fichier frontend généré | **adopté** | structure (phase 1) |
| Régénération intégrale au lancement | **non adopté** | philosophie du dépôt, brief |
| RPCS3 — compteur 1-based par nom | **confirmé** | lecture croisée |
| Dolphin — compteur 0-based par nom | **confirmé** | lecture croisée |
| Dolphin — backend evdev | **non adopté** | cohérence avec la graine SDL |
| Multitap PS1/PS2 seuil 3 | **confirmé** | lecture croisée (non mesuré) |
| `SDL-{index}` vs `SDL-{i-1}` | **GameCore conservé** + limite documentée | analyse ; non mesurable ici |
| Ryujinx — synthèse du GUID | **rejeté, mesuré faux** | mesure décisive |
| Cemu — GUID de l'hôte | **rejeté** | config en place ≠ réponse live ; divergence *live* non établie |
| azahar — snapshot | **conservé** ; promotion possible plus tard | vérité terrain `qt-config.ini` |
| melonDS — synthèse | **conservé** (Batocera ne fait rien) | lecture |
| RPCS3 handler DS4 natif | **à reprendre, hors refactor**, sélection par vendor:product | mesure : liste GUID inopérante |

---

## 6. Plan de phase 1

Objectif : le catalogue existe et est la source ; **aucun changement de
comportement à l'installation**. `install/systems.json.dist` et
`install/apps.json.dist` deviennent générés et restent **bit pour bit
identiques** à ceux d'aujourd'hui — c'est le critère d'acceptation.

### 6.1 Fichiers créés

```
catalog/_schema/pack.schema.json
catalog/<id>/pack.json                    × 17  (13 émulateurs + 4 apps)
catalog/<id>/logo.png                     × 17  (git mv depuis assets/logos/)
catalog/<id>/seed/**                      × 10  (git mv depuis emu-configs/, gopher64 exclu)
catalog/twitch/files/**                   (user.js, service, gabarits)
catalog/youtube/files/twitch-tv…user.js   (git mv depuis install/firefox-profiles/)
config/catalog.d/.gitkeep
config/catalog.d/README.md                règle « données seules » + opt-in
scripts/gen-catalog.py                    génère les .dist (+ --check pour la CI)
backend/services/catalog/__init__.py      chargeur fusionné, local prioritaire
backend/services/catalog/loader.py
backend/services/catalog/schema.py        validation sans dépendance nouvelle
backend/tests/test_catalog_symmetry.py
backend/tests/test_catalog_loader.py
backend/tests/test_catalog_seeds.py       seedMustNotContain + absence de /home/pavic
```

### 6.2 Fichiers modifiés

| Fichier | Modification |
|---|---|
| `install/systems.json.dist` | devient **généré** (contenu inchangé) |
| `install/apps.json.dist` | idem — sauf `/home/pavic` → `@HOME@`, substitué au déploiement |
| `.github/workflows/release.yml` | + validation de schéma, + `gen-catalog.py --check`, + symétrie, + `seedMustNotContain`, + `grep -rn '/home/pavic'`, + découverte de `catalog/*/tests/` |
| `pytest.ini` | `testpaths` inclut `catalog` |
| `update/linux.sh` | commentaire du bloc rsync : dire que `catalog/` est livré et **doit** être écrasé, et que `config/catalog.d/` est préservé via `config/` |
| `docs/architecture/07-config-and-data.md` | section catalogue |

### 6.3 Fichiers **non** touchés en phase 1

`arch.sh`, `uninstall.sh`, `flatpakify-systems.sh`, `install-emu-configs.sh`,
`gamecore_installer.py`, `verify_emulators.py`, `scraper.py`, `gamemedia.py`,
`overlays.json`, `controller_profiles.py`, `systems.py`. Ils continuent de lire
leurs maps actuelles. **C'est la phase 2 qui les branche** — et c'est aussi ce
qui garantit qu'un `.dist` généré identique prouve la correction du catalogue
avant qu'un seul consommateur n'en dépende.

Corollaire : **le bug gopher64 n'est pas corrigé en phase 1.** Le pack portera
le bon `@FLATPAK_CONFIG@` (donc `com.github.Rosalie241.RMG`), mais
`install-emu-configs.sh` lira encore sa propre map. Le test qui échoue sur le
code actuel s'écrit en phase 2, comme le demande le brief.

### 6.4 Ordre de travail

1. Schéma + `catalog/_schema/`, avec un validateur maison (pas de `jsonschema` en
   dépendance — `backend/requirements.txt` doit rester tel quel).
2. Les 17 `pack.json`, dérivés **mécaniquement** des `.dist` actuels.
3. `scripts/gen-catalog.py` + `--check`, jusqu'à ce que la sortie soit identique
   aux `.dist` committés.
4. `git mv` des logos et des graines ; suppression de `emu-configs/gopher64/`.
5. Chargeur fusionné + tests (symétrie, graines, origine journalisée).
6. CI.

### 6.5 Questions ouvertes à trancher avant de coder

1. **Tokens `@NOM@` plutôt que `$NOM`** (§1.1a) — d'accord ?
2. **`postInstall` en tableau** (§1.1b) — d'accord ?
3. **`emu-configs/gopher64/` supprimé** plutôt que re-moissonné au format RMG
   (§D-1) — d'accord ? C'est la seule perte de contenu de la migration.
4. **Un logo pour `youtube`** (§4.1), ou logo optionnel pour `kind: app` ?
5. **La route Caddy reste centrale** (§1.2.1) — limite assumée ?
