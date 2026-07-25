# 7 — Config & données

Tout ce que le boîtier stocke, et qui l'écrit.

## Résolution des chemins — `backend/config.py`

Rien ne code en dur `/opt/GameCore`. Tout chemin dérive de `GAMECORE_ROOT`,
qui vaut `$GAMECORE_PATH` ou la racine du dépôt.

| Constante | Valeur |
|---|---|
| `GAMECORE_ROOT` | `$GAMECORE_PATH` ou la racine du dépôt |
| `SYSTEMS_FILE` | `config/systems.json` |
| `APPS_FILE` | `config/apps.json` |
| `PLAYTIME_DB` | `config/playtime.db` |
| `COVERS_DIR` | `emu/covers` |
| `ASSETS_DIR` | `assets/` |
| `BACKEND_PORT` | `$GAMECORE_BACKEND_PORT` ou 8765 |
| `APP_VERSION` | contenu de `VERSION` (écrit par le script OTA) |
| `GITHUB_REPO`, `UPDATE_ASSET` | `p4v1c/GamecoreRenew`, `gamecore-ota.tar.gz` |
| `THEGAMESDB_API_KEY` | environnement uniquement — jamais commitée |
| `DEBUG` | doit valoir `false` sur un boîtier |

`resolve_path(raw)` transforme une chaîne relative à la config en `Path`
absolu ; une entrée absolue passe telle quelle. Chaque `romsPath` et
`iconPath` y passe.

## Ce qui vit dans `config/`

| Fichier | Écrit par | Lu par |
|---|---|---|
| `systems.json` | installeur / à la main | `routers/systems.py` |
| `apps.json` | installeur / à la main | `routers/systems.py` |
| `overlays.json` | à la main | `routers/overlays.py`, `electron/main.js`, `overlay_monitor.py` |
| `addons.json` | le CLI `gamecore-addon` | `routers/addons.py` |
| `standby.json` | `POST /api/standby/config` | `services/standby.py` |
| `auth.json`, `auth_secret` | `services/auth.py`, mode 0600 | idem |
| `playtime.db` | le backend (SQLite) | le backend |

**Aucun n'est dans git, et le rsync OTA exclut `config/` en entier.** Ce sont
l'identité du boîtier : disposition de la bibliothèque, identifiants, addons
installés, historique de jeu. Écraser l'un d'eux, c'est une perte de données.

---

## `config/systems.json`

Un tableau. Une entrée par émulateur :

```jsonc
{
  "id": "azahar",                    // clé primaire, utilisée partout
  "type": "emulator",
  "label": "Nintendo 3DS",           // affiché sur la tuile
  "platform": "3DS",                 // badge court
  "color": "#ff0096",                // couleur d'accent de ce système
  "iconPath": "assets/logos/3ds.png",
  "path": "flatpak",                 // "flatpak" ou un chemin de binaire absolu
  "args": "run org.azahar_emu.Azahar -f",
  "romsPath": "emu/azahar/",
  "extensions": ["*.3ds", "*.zip"],
  "libretroSystems": ["Nintendo - Nintendo 3DS"],   // clé de scraping des jaquettes
  "scanDirs": false                  // true → les jeux sont des dossiers (PS3, PS4)
}
```

| Clé | Consommée par |
|---|---|
| `id` | tout — recherches `list_all()`, chemins de cache des jaquettes, config d'overlay |
| `path` + `args` | `process_manager.launch()` ; `args` passe par `shlex.split`, le chemin de ROM est ajouté à la fin |
| `romsPath` | `list_games()`, **et le contrôle de confinement de `launch_game()`** |
| `extensions` | `rom_scanner.matches_ext` (motifs glob) |
| `scanDirs` | `iter_rom_files` renvoie des dossiers ; active `local_media.get_title()` |
| `libretroSystems` | `scraper._get_index()` |
| `color`, `iconPath`, `label`, `platform` | l'UI uniquement |

Deux clés optionnelles que le code honore mais que la config livrée n'utilise
pas actuellement :

| Clé | Effet |
|---|---|
| `"gamepadTrigger": true` | `_gamepad_trigger()` exécute `sudo udevadm trigger` ×3 après le lancement, pour les applications Flatpak qui ne voient la manette qu'après un nouveau déclenchement udev. Nécessite une règle sudoers. |
| `"fullscreen": {…}` | `fullscreen_enforcer.enforce()` force la fenêtre en plein écran via EWMH, pour les applications sans option dédiée |

## `config/apps.json`

Même forme, sans les clés de ROM, plus `"kind": "app"` :

```jsonc
{ "id": "steam", "kind": "app", "type": "application", "label": "Steam",
  "platform": "Steam", "color": "#1f6fb3", "iconPath": "assets/logos/steam.png",
  "path": "flatpak", "args": "run com.valvesoftware.Steam" }
```

`list_all()` concatène systèmes + applications. `list_games()` renvoie `[]`
pour tout ce qui a `kind == "app"` ou `type == "application"`.

## `config/overlays.json`

Indexé par identifiant de système :

```jsonc
"melonds": {
  "label": "Nintendo DS",
  "wm_class": { "linux": ["melonds", "melonDS", "net.kuribo64.melonDS", "AppRun.wrapped"] },
  "window_rect": { "x": 0, "y": 0, "w": 1920, "h": 1080 },
  "overlay_asset": "assets/overlays/melonds.png",
  "hole": { "x": 600, "y": 0, "w": 720, "h": 1080 },
  "watch_timeout_s": 60
}
```

| Clé | Utilisée par |
|---|---|
| `wm_class.linux` | `X11Manager.find_window()` — plusieurs orthographes parce que les wrappers Flatpak renomment la classe (noter `AppRun.wrapped`) |
| `window_rect` | géométrie cible de `force_rect()` |
| `overlay_asset` | le PNG affiché par la fenêtre overlay |
| `hole` | la zone transparente — **doit correspondre au PNG** ; c'est le cadre de repli dessiné quand le PNG manque |
| `watch_timeout_s` | combien de temps le veilleur attend la fenêtre avant d'abandonner |

## `config/addons.json`

Écrit par le CLI `gamecore-addon` depuis chaque `addon.json`. Servi tel quel
par `GET /api/addons` et `GET /gc/addons`. Champs qui comptent en aval :
`name`, `label`, `port`, `path` (`/roms`, `/saves`, `/rpcs3`), `type` (les
addons `web` obtiennent un lien de navigation), `version`.

## `config/standby.json`

`{enabled, screensaver_delay, sleep_delay, governor}` — forme imposée par le
modèle pydantic `StandbyConfig` de `routers/standby.py`.

## `config/auth.json` + `auth_secret`

`auth.json` = `{hash: argon2id, generation: int}`. `auth_secret` = 32 octets
aléatoires, la clé HMAC des cookies de session. Les deux en 0600, écrits
atomiquement par `_write_private()`. Incrémenter `generation` invalide toutes
les sessions vivantes.

---

## `playtime.db`

Créée par `db.py:init_db()`.

```sql
CREATE TABLE playtime (
    game_key      TEXT PRIMARY KEY,
    system_id     TEXT NOT NULL,
    total_secs    INTEGER NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    last_played   TEXT
);
CREATE TABLE sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_key   TEXT NOT NULL,
    system_id  TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    duration   INTEGER
);
```

`_watch()` écrit par upsert :

```sql
INSERT INTO playtime (…) VALUES (…)
ON CONFLICT(game_key) DO UPDATE SET
    total_secs = total_secs + excluded.total_secs,
    session_count = session_count + 1,
    last_played = excluded.last_played
```

`game_key` est le nom de fichier de la ROM (ou l'identifiant du système pour
une application), c'est pourquoi renommer une ROM remet son historique à zéro.

`get_db()` rouvre la connexion si celle en cache est devenue inutilisable —
une connexion aiosqlite de longue durée peut mourir au fil des cycles de veille
du boîtier.

---

## Caches sur disque

| Chemin | Contenu | Invalidation |
|---|---|---|
| `emu/covers/<system>/<nom>.png\|jpg` | jaquette résolue | manuelle — **y déposer un fichier fige la jaquette** |
| `emu/covers/<system>/<nom>.miss` | cache négatif | 7 jours, ou `?refresh=1` |
| cache de métadonnées | textes TheGamesDB, échecs compris | idem |
| `~/.config/gamecore-electron/Cache` | cache HTTP de Chromium | purgé par le script OTA et à chaque démarrage d'Electron |

## Assets

| Chemin | Contenu |
|---|---|
| `assets/logos/` | tuiles des systèmes — **exclues de l'OTA**, les utilisateurs ajoutent les leurs |
| `assets/overlays/` | PNG de bezels — exclus de l'OTA |
| `backend/data/gamecontrollerdb.txt` | SDL_GameControllerDB embarquée, exportée en `SDL_GAMECONTROLLERCONFIG_FILE` |
| `emu/<system>/` | ROMs — exclues de l'OTA |
