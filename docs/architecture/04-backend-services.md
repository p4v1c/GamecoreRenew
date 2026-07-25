# 4 — Backend, services

Là où vit la logique. Aucun import FastAPI dans ce dossier : un service est
appelable depuis un test, un script, ou un autre service.

[`controller_profiles.py`](08-chaine-manettes.md) est assez gros pour avoir son
propre document.

---

## process_manager.py

Singleton de module : `process_manager = ProcessManager()`.

État : `_proc`, `_launching`, `_game_key`, `_system_id`, `_start_time`,
`_exec_path`, `_launch_args`.

| Membre | Rôle |
|---|---|
| `_display_env()` | reconstruit un environnement graphique pour un enfant de systemd — voir [1](01-topologie-execution.md#reconstruction-de-lenvironnement) |
| `is_running` | `_launching or (_proc and returncode is None)` |
| `current_game` | `{game_key, system_id}` ou `None` |
| `launch(exec_path, exec_args, rom_path, game_key, system_id)` | construit argv (`shlex.split` + ROM), lance, diffuse `game:started`, démarre `_watch()` |
| `kill()` | `_flatpak_kill()` puis `_proc_kill()` |
| `_flatpak_kill()` | retrouve l'app-id (le jeton après `run`) et lance `flatpak kill <app-id>`, timeout 1 s |
| `_proc_kill()` | `os.killpg(os.getpgid(pid), SIGKILL)`, repli sur `proc.kill()` |
| `_watch()` | attend la fin, enregistre le temps de jeu si > 5 s, diffuse `game:finished` |

Trois décisions qui paraissent étranges tant qu'on n'en connaît pas la raison :

1. **`_launching` est réservé de façon synchrone**, avant le premier `await`.
   Deux appels concurrents à `launch()` passeraient sinon tous deux le test
   `is_running` pendant que le premier attend encore le lancement.
2. **`start_new_session=True`** place l'enfant dans son propre groupe de
   processus. Sans cela, `killpg` atteindrait le backend lui-même.
3. **SIGKILL, pas de SIGTERM.** Plusieurs émulateurs répondent au SIGTERM par
   une confirmation impossible à cliquer à la manette.

L'en-tête du module consigne aussi un vrai bug : une version antérieure
exportait `SDL_GAMECONTROLLERDB`, une variable que SDL n'a jamais lue — la base
de mappings embarquée était donc silencieusement ignorée. Le bon nom est
`SDL_GAMECONTROLLERCONFIG_FILE`.

---

## `gamepad_monitor.py` (280 l.) — evdev, la source de vérité de l'entrée

Tourne en tâche de `lifespan`. Existe parce qu'on ne peut pas faire confiance à
l'API Gamepad du navigateur pour le bouton Guide, et qu'elle ne voit rien
pendant qu'un émulateur plein écran possède l'affichage.

| Fonction | Rôle |
|---|---|
| `run()` | boucle principale — rebalaye les périphériques toutes les quelques secondes |
| `_find_gamepad_devices()` | `chemin → (nom, uniq, is_pad, vendor, product)` pour chaque `/dev/input/event*` lisible |
| `_can_read(path)` | sonde de permission |
| `_watch_device(path)` | lit un périphérique jusqu'à déconnexion ou annulation |
| `_on_guide_pressed()` | la logique de double appui, puis `POST /api/games/kill` |

Il pilote aussi `controller_registry` à la connexion/déconnexion,
`controller_profiles.apply_profile()` / `release_profile()` pour la
configuration par émulateur de la manette, et `standby.on_input()` — c'est
ainsi qu'un bouton réveille un boîtier endormi.

---

## `controller_registry.py` (89 l.) — slots joueurs à la console

Attribue P1…P4 et les garde stables à travers les reconnexions.

| Fonction | Rôle |
|---|---|
| `normalize_mac(value)` | extrait une MAC `aa:bb:…` en minuscules de n'importe quelle chaîne |
| `key_for(uniq, path)` | clé stable : la MAC si connue, sinon le nœud périphérique |
| `has(key)` / `label_for(key)` | recherches |
| `connect(key, label)` | attribue le **plus petit slot libre** ; idempotent pour une clé connue |
| `disconnect(key)` | libère le slot, renvoie le numéro de joueur qu'il portait |
| `player_for_mac(value)` | slot pour toute chaîne porteuse de MAC — sert à rattacher une batterie sysfs à un joueur |
| `snapshot()` | `[{player, label}]` trié par slot — ce que renvoie `/api/sysinfo` |

---

## `battery.py` (116 l.)

| Fonction | Rôle |
|---|---|
| `read_batteries()` | sysfs → `[{name, level, charging}]` |
| `_check(batteries)` | **pure** — renvoie les alertes à envoyer pour ce cycle, donc testable unitairement |
| `run()` | sonde et diffuse `gp:battery` |

L'UI l'affiche en toast ; en jeu, Electron peint un HUD natif toujours au-dessus,
car le toast React est masqué par l'émulateur.

---

## `standby.py` (152 l.)

| Fonction | Rôle |
|---|---|
| `load_config()` / `save_config(cfg)` | `config/standby.json` |
| `get_state()` | `active` / `screensaver` / `asleep` |
| `_run_cmd(*argv)` | utilitaire, renvoie le succès |
| `_screen(on)` | DPMS allumé/éteint |
| `_governor(gov)` | `cpupower frequency-set -g …` — optionnel, nécessite une règle sudoers |
| `_enter(stage)` | transition d'étape + diffusion WS |
| `exit_standby()` | réveil |
| `on_input()` | appelée depuis la boucle evdev sur n'importe quel bouton |
| `run()` | la boucle de sondage d'inactivité |

Un jeu en cours bloque entièrement la veille.

---

## `cover_pipeline.py` (132 l.) — orchestration

| Fonction | Rôle |
|---|---|
| `resolve(system, filename, refresh=False)` | la résolution en quatre niveaux, [dessinée ici](02-flux-detailles.md#3-résoudre-une-jaquette) |
| `_id_urls(kind, value)` | paires `(url, ext)` candidates pour un identifiant de disque, meilleure d'abord |
| `_regions(letter)` | expansion des codes région pour les chemins GameTDB |
| `_fetch_by_id(kind, value, base)` | télécharge la première candidate qui existe |

Les résultats négatifs sont écrits en fichiers `.miss`, valables 7 jours, pour
qu'un boîtier hors ligne ne retente pas le réseau à chaque défilement.

## `local_media.py` (150 l.) — lire le jeu lui-même

Hors ligne et exact. Rien ici ne devine à partir d'un nom de fichier.

| Fonction | Rôle |
|---|---|
| `_ps3_icon(rom)` / `_ps3_sfo(rom)` | `PS3_GAME/ICON0.PNG`, `PARAM.SFO` |
| `_ps4_icon(rom)` / `_ps4_sfo(rom)` | `sce_sys/icon0.png`, `param.sfo` |
| `_psp_read(rom, inner)` / `_psp_sfo(rom)` | extrait un fichier **de l'ISO** via `iso9660` |
| `_gc_wii_id(rom)` | identifiant 6 caractères depuis l'en-tête d'une image GameCube/Wii |
| `_playstation_serial(rom)` | numéro de série PS1/PS2 (`SLUS-20946`) depuis `SYSTEM.CNF` dans l'image |
| `extract_icon(system_id, rom, dest)` | écrit l'icône embarquée, ou `None` |
| `get_title(system_id, rom)` | vrai titre depuis les métadonnées embarquées — pourquoi les dossiers PS3 affichent un nom et pas `BLES01234` |
| `disc_id(system_id, rom)` | `(kind, id)` pour une recherche en ligne exacte, ex. `("wii", "GALE01")` |

## `iso9660.py` (106 l.) — lecteur ISO minimal

`class Iso9660` avec `open(path)` (méthode de classe, détecte la disposition de
secteurs, renvoie `None` pour un non-ISO comme un `.cso` compressé), `_sector`,
`_read_extent`, `_entries` et `read_file("PSP_GAME/ICON0.PNG")` (insensible à
la casse). Supporte `with` via `__enter__`/`__exit__` — utilisez-le, la fabrique
ne ferme le descripteur que sur ses propres chemins d'échec.

## `scraper.py` (242 l.) — le niveau réseau

| Fonction | Rôle |
|---|---|
| `_normalize(name)` | minuscules alphanumériques, pour la correspondance floue |
| `_name_variants(base)` | les orthographes à essayer contre l'index du CDN |
| `_get_index(client, system_name)` | récupère et met en cache le listing libretro |
| `fetch_cover(rom_path, system_id, dest)` | libretro d'abord, puis TheGamesDB |
| `_fetch_tgdb_cover(name, system_id, dest)` | nécessite `THEGAMESDB_API_KEY`, ignoré silencieusement sinon |
| `_region_rank(n)` | privilégie la région probablement voulue quand plusieurs correspondent |

## `metadata.py` (119 l.)

`resolve(system, filename)` → description, année, genres, joueurs, note. Mis en
cache disque, y compris les échecs. `_genre_names(client)` résout la table des
genres une fois ; `_search_name(system, filename)` construit la requête ;
`_fetch_tgdb(platform_id, name)` fait l'appel.

## `sfo.py` (34 l.)

`parse_bytes(d)` et `parse(path)` — table clé/valeur PARAM.SFO, `{}` en cas
d'erreur. Même format binaire sur PS3, PS4 et PSP. Le dépôt d'addons a sa
propre copie dans `shared/py/` ; celle-ci expose en plus `parse_bytes()` pour
des données déjà en mémoire.

## `rom_scanner.py` (34 l.)

`clean_name(filename)` (retire l'extension et les balises entre crochets comme
`[!]`, `(USA)`), `matches_ext(filename, extensions)` et
`iter_rom_files(roms_path, extensions, scan_dirs)` — par ordre alphabétique,
avec les exclusions courantes. L'addon rom-manager en garde une copie miroir.

## `prefetch.py` (60 l.)

`run()` parcourt la bibliothèque au démarrage et appelle
`warm(system, filename)` pour que le premier défilement ne soit pas un
indicateur de chargement.

---

## `overlay_monitor.py` (277 l.) — veilleur X11, exécuté comme sous-processus

Pas importé par le backend : Electron le lance et lui parle en JSON-lines sur
stdio.

```
stdin  ← {"cmd":"watch","system_id":"dolphin","config":{…}}  |  {"cmd":"stop"}
stdout → {"event":"window:ready","system_id":…,"rect":{x,y,w,h}}
       → {"event":"window:waiting"|"window:closed"|"error", …}
```

| Symbole | Rôle |
|---|---|
| `emit(obj)` / `emit_error(msg)` | un objet JSON par ligne sur stdout, vidé immédiatement |
| `X11Manager._client_windows()` | fenêtres de premier niveau via `_NET_CLIENT_LIST`, avec repli récursif |
| `X11Manager.find_window(wm_classes)` | première fenêtre dont le `WM_CLASS` correspond |
| `X11Manager.dump_windows()` | aide au débogage — tous les `WM_CLASS` |
| `X11Manager.force_rect(wid, x, y, w, h)` | quitte le plein écran, retire les décorations (hints Motif), déplace et redimensionne |
| `X11Manager.get_rect(wid)` | géométrie traduite en coordonnées racine |
| `X11Manager.window_exists(wid)` | test de vie |
| `OverlayMonitor.watch(system_id, cfg)` | démarre le thread de surveillance |
| `OverlayMonitor.stop()` / `_run()` | cycle de vie |
| `main()` | la boucle stdio |

`force_rect()` quitte le plein écran avec un **ClientMessage `_NET_WM_STATE`
envoyé à la fenêtre racine**, comme EWMH l'exige pour une fenêtre mappée.
Écrire la propriété directement (ce qu'il faisait avant) efface *tous* les
états d'un coup — `_NET_WM_STATE_ABOVE` compris — et désynchronise la
comptabilité interne du gestionnaire de fenêtres.

`_WAYLAND_SESSION` désactive tout le module quand `WAYLAND_DISPLAY` est défini.

## `fullscreen_enforcer.py` (130 l.)

La même boîte à outils EWMH pointée dans l'autre sens, pour les applications
sans option plein écran en ligne de commande (clé `"fullscreen"` d'un système).

`_iter_client_windows`, `_find_window(disp, wm_classes)`, `_is_fullscreen`,
`_request_fullscreen` (ajoute `_NET_WM_STATE_FULLSCREEN` par message client),
`_enforce_sync(system_id, wm_classes, timeout_s)`, et l'asynchrone
« lancer et oublier » `enforce(system_id, cfg)`.

---

## `auth.py` (150 l.) — mot de passe partagé

| Fonction | Rôle |
|---|---|
| `_write_private(path, data)` | écriture atomique, **0600 dès le premier octet** |
| `_auth()` / `_secret()` | lisent `config/auth.json` et `config/auth_secret` |
| `is_configured()` | un mot de passe a-t-il déjà été défini |
| `set_password(new, reset_secret=False)` | hachage argon2id ; **incrémente toujours `generation`** |
| `verify_password(password)` | vérification argon2 |
| `_mac(secret, payload)` | HMAC-SHA256 |
| `make_cookie()` | `expiry.generation.HMAC(secret, "expiry.generation")` |
| `check_cookie(value)` | expiration + génération + MAC |
| `blocked_for(ip)` | secondes restant à attendre — 0 = non bloqué |
| `register_failure(ip)` / `register_success(ip)` | temporisation en mémoire, exponentielle après 5 échecs |

Incrémenter `generation` est la façon dont « changer le mot de passe »
invalide toutes les sessions vivantes sans stocker le moindre état de session.

---

## `ws.py` et `db.py` (racine du backend)

`ws.py` — `connect(ws)` (accepte et rejoue `game:running` si un jeu tourne
déjà), `disconnect(ws)`, `broadcast(event, data)` (élimine les clients morts),
`set_current_game(game)`.

`db.py` — `get_db()` renvoie une connexion `aiosqlite` vivante, en la
rouvrant si celle en cache est devenue inutilisable ; `init_db()` crée les
tables `playtime` et `sessions`. Schéma en
[7](07-config-et-donnees.md#playtimedb).
