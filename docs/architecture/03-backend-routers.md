# 3 — Backend, routers

Toute la surface HTTP, fichier par fichier. Les numéros de ligne sont
indicatifs — les noms de fonctions sont le contrat.

Tous les routers sont montés avec `prefix="/api"` dans `backend/main.py:41-55`.
Les routers analysent, valident et délèguent ; la logique vit dans les
[services](04-backend-services.md).

## Câblage — `main.py` (111 l.)

| Symbole | Rôle |
|---|---|
| `lifespan(app)` | crée les quatre tâches de fond au démarrage, les annule à l'arrêt |
| `overlay_page()` | `GET /overlay` — sert la SPA à la fenêtre Electron transparente |
| `gc_addons()` | `GET /gc/addons` — même charge utile que `/api/addons`, sur un chemin que Caddy proxifie **sans auth** (la barre de nav des addons en a besoin avant le login) |
| `login_page()` | `GET /login` — formulaire de connexion autonome pour les clients LAN |
| `websocket_endpoint(websocket)` | `WS /ws` — accepte puis lit en boucle ; tout envoi est un broadcast venant de `ws.py` |

Montages statiques, dans l'ordre : `/covers`, `/assets/logos`,
`/assets/overlays`, `/data`, puis `/` → `frontend/dist` avec `html=True`. La
boucle fait un `mkdir` de chaque dossier d'abord — un montage conditionnel
décidé à l'import laissait `/covers` mort jusqu'au redémarrage sur un clone
neuf.

> `@app.websocket("/ws")` **doit** rester déclaré avant le montage `/`. Le
> fourre-tout de la SPA avalerait sinon la requête d'upgrade.

## `systems.py` (63 l.) — le catalogue

| Fonction | Route | Notes |
|---|---|---|
| `_hot_load(path)` | — | relit le JSON **à chaque appel** ; aucun redémarrage nécessaire après édition, et une erreur de syntaxe casse l'API immédiatement |
| `get_systems()` | — | `config/systems.json` |
| `get_apps()` | — | `config/apps.json` |
| `list_all()` | — | liste fusionnée — *la* recherche utilisée par `games.py` et le pipeline de jaquettes |
| `list_systems()` | `GET /systems` | |
| `get_system(system_id)` | `GET /systems/{id}` | |
| `serve_logo(filename)` | `GET /assets/logos/{filename}` | |

## `games.py` (138 l.) — scan et lancement

| Fonction | Route | Notes |
|---|---|---|
| `scan_roms(roms_path, extensions, scan_dirs, system_id)` | — | enveloppe `rom_scanner.iter_rom_files` ; ignore les fichiers disparus au lieu de renvoyer un 500 ; pour les systèmes `scanDirs`, préfère le titre de `local_media.get_title()` au nom de dossier (un dossier PS3 s'appelle souvent `BLES01234`) |
| `list_games(system_id)` | `GET /systems/{id}/games` | renvoie `[]` pour les applications |
| `launch_game(req)` | `POST /games/launch` | 404 système inconnu · 409 déjà en cours · **403 si le chemin de ROM sort du `romsPath` du système** |
| `kill_game()` | `POST /games/kill` | |
| `get_session()` | `GET /games/session` | `process_manager.current_game or {}` |
| `_gamepad_trigger(rounds=3, delay=3.0)` | — | `sudo udevadm trigger` ×3, pour les applications Flatpak qui ne voient la manette qu'après un nouveau déclenchement udev |

Le contrôle de chemin est la ligne critique en sécurité :

```python
Path(req.rom_path).resolve().relative_to(roms_root.resolve())
```

Sans elle, un `rom_path` forgé transforme `/api/games/launch` en « exécuter
n'importe quel binaire du boîtier ».

## `covers.py` (28 l.) / `metadata.py` (19 l.)

| Fonction | Route |
|---|---|
| `get_cover(system_id, filename, refresh=False)` | `GET /covers/{system}/{file:path}` → `cover_pipeline.resolve()` |
| `get_metadata(system_id, filename)` | `GET /metadata/{system}/{file:path}` → `metadata.resolve()` |

`{filename:path}` (et non `{filename}`) parce que les noms de jeux contiennent
des barres obliques pour les jeux en dossier.

## `playtime.py` (36 l.)

`get_all_playtime()`, `get_system_playtime(system_id)`,
`get_game_playtime(game_key:path)` — lectures directes de la table `playtime`
([schéma](07-config-et-donnees.md#playtimedb)).

## `overlays.py` (69 l.) — envoi de bezels

| Fonction | Route | Notes |
|---|---|---|
| `_overlay_path(system_id)` | — | `assets/overlays/<id>.png` |
| `get_overlay(system_id)` | `GET /overlays/{id}` | |
| `_looks_like_image(head)` | — | **contrôle des octets magiques** — « l'en-tête Content-Type du client ne prouve rien » |
| `upload_overlay(system_id, file)` | `POST /overlays/{id}` | |
| `delete_overlay(system_id)` | `DELETE /overlays/{id}` | |

## `addons.py` (141 l.) — registre et cycle de vie

| Fonction | Route | Notes |
|---|---|---|
| `_cli()` | — | localise le binaire `gamecore-addon` |
| `_registry()` | — | lit `config/addons.json` |
| `list_installed()` | `GET /addons` | consommé par la TV **et** par la barre de nav de chaque addon |
| `list_available()` | `GET /addons/available` | exécute `gamecore-addon list --json` ; peut cloner le dépôt |
| `notify(body)` | `POST /addons/notify` | crochet générique : un addon pousse un événement sur le WebSocket du cœur |
| `_run_cli(action, name)` / `_pump()` | — | exécute le CLI, relaie sa sortie via le WS |
| `_start(action, name)` | — | empêche deux exécutions concurrentes du CLI |
| `install_addon` / `update_addon` / `remove_addon` | `POST /{name}/install`, `POST /{name}/update`, `DELETE /{name}` | |

Le cœur ne touche jamais aux fichiers d'addons lui-même — il délègue au CLI.
C'est ce qui garde le registre cohérent quelle que soit la façon dont la
commande a été lancée.

> `/api/addons/notify` est joignable par n'importe quel addon et sa charge
> utile finit dans le HTML des toasts HUD. Voir
> [pièges](09-pieges.md#des-chaînes-non-fiables-atteignent-le-hud).

## `update.py` (100 l.) — OTA

| Fonction | Route | Notes |
|---|---|---|
| `_version_int(tag)` | — | ordonnancement `x.y.z` tolérant — `v2.1.0-rc1` ou un tag malformé ne doit jamais faire planter la vérification |
| `check_update()` | `GET /update/check` | interroge l'API des releases GitHub |
| `apply_update()` | `POST /update/apply` | lance `update/linux.sh` en tâche de fond |
| `_run_update()` / `_pump()` | — | relaie stdout ligne par ligne sur le WebSocket, ce que la page de réglages affiche en direct |

## `sysinfo.py` (30 l.)

`_primary_ip()` + `get_sysinfo()` → `GET /sysinfo` : IP, stockage
utilisé/total/libre, `APP_VERSION`, et `controller_registry.snapshot()` (les
slots P1…P4 avec la batterie). La TopBar et l'écran manette le lisent tous deux.

## `standby.py` (30 l.)

`get_standby()` (état + config), `set_config(cfg)` (modèle `StandbyConfig`,
persisté dans `config/standby.json`), `wake()` → `standby.exit_standby()`.

## `controllers.py` (18 l.)

Une seule route : `POST /controllers/scan-mapping` →
`controller_profiles.scan_mapping()`. Tout l'intérêt est expliqué en
[8](08-chaine-manettes.md) : les émulateurs à GUID ne peuvent pas être mappés
par programme, donc l'utilisateur configure la manette une fois dans leur
propre interface et ceci en fait un instantané par manette.

## `auth.py` (109 l.) — login à mot de passe partagé

| Fonction | Route | Notes |
|---|---|---|
| `_client_ip(request)` | — | lit `X-Forwarded-For` (la requête arrive toujours via Caddy) |
| `_set_session(resp)` | — | cookie `gc_session` : HttpOnly, Secure, SameSite=Lax, 30 jours |
| `login(request)` | `POST /auth/login` | limité par `auth.blocked_for(ip)` |
| `verify(request)` | `GET /auth/verify` | **l'endpoint du `forward_auth`.** 200 → Caddy laisse passer et recopie `X-GC-User` ; 302 → page de login ; 401 |
| `logout()` | `POST /auth/logout` | |
| `change_password(request)` | `POST /auth/change-password` | incrémente `generation` → toutes les sessions existantes tombent |

## `settings/` — les enveloppes système

Chaque module enveloppe un outil en ligne de commande et fait attention à
l'environnement, car un service systemd n'a pas de bus de session. Les trois
définissent leur propre `_session_env()` et un `_run(*args)` asynchrone.

### `settings/wifi.py` (183 l.) — `nmcli`

| Fonction | Route |
|---|---|
| `_wifi_iface()` | — nom de l'interface WiFi active |
| `scan_networks()` (+ `_rescan()`) | `GET /wifi/networks` |
| `_iface_ip(iface)`, `_ethernet_status()` | — |
| `wifi_status()` | `GET /wifi/status` — SSID, IP **et état filaire**, pour que l'UI puisse sauter toute la procédure WiFi en ethernet |
| `connect_wifi(req)` | `POST /wifi/connect` — distingue explicitement `wrong_password` |
| `disconnect_wifi()` | `DELETE /wifi/connect` |
| `_spawn_bg(coro, label)` | — utilitaire de tâche de fond avec journalisation d'erreur |

### `settings/audio.py` (88 l.)

`get_audio()`, `list_sinks()`, `set_volume(req)`, `set_sink(req)`.

### `settings/bluetooth.py` (118 l.) — `bluetoothctl`

`list_devices()`, `start_scan()` (retourne immédiatement, `_do_scan()` tourne
8 s en tâche de fond), `connect_device`, `disconnect_device`,
`remove_device(mac)`.

> Les noms d'appareils Bluetooth sont des chaînes contrôlées par un tiers qui
> atteignent l'UI. C'est l'une des raisons d'être de `escHtml()` côté Electron.
