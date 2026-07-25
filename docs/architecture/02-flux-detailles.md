# 2 — Flux détaillés

Les chemins qui valent la peine d'être connus de bout en bout. Chaque flèche
nomme la fonction qui s'exécute.

## 1. Lancer un jeu

```mermaid
sequenceDiagram
    participant ui as LibraryScreen
    participant r as routers/games.py
    participant pm as process_manager
    participant ws as ws.py
    participant el as Electron
    participant mon as overlay_monitor
    participant emu as émulateur

    ui->>r: POST /api/games/launch {system_id, rom_path, game_key}
    r->>r: list_all() → système, sinon 404
    r->>pm: is_running ? → 409 si occupé
    r->>r: rom_path.resolve().relative_to(roms_root) → 403 si hors dossier
    r->>pm: launch(exec_path, exec_args, rom_path, …)
    pm->>pm: _launching = True (réservation synchrone)
    pm->>pm: _display_env()
    pm->>emu: create_subprocess_exec(start_new_session=True)
    pm->>ws: set_current_game() + broadcast("game:started")
    pm->>pm: create_task(_watch())
    ws-->>ui: game:started
    ui->>el: window.gamecore.overlayStart(system_id)
    el->>el: loadOverlayConfig() → config/overlays.json
    el->>mon: spawn + {"cmd":"watch","system_id":…,"config":…}
    mon->>mon: find_window(wm_classes) — sonde jusqu'à apparition
    mon-->>el: {"event":"window:ready","rect":{…}}
    el->>el: createOverlayWindow() — transparente, toujours au-dessus
    r-->>ui: {ok: true, game_key}
```

Après la réponse, `launch_game()` peut aussi programmer deux tâches
« lancer et oublier », pilotées par des clés optionnelles du système :

- `"gamepadTrigger": true` → `_gamepad_trigger()` exécute
  `sudo udevadm trigger` 3× à 3 s d'intervalle, pour que les applications
  Flatpak voient la manette.
- `"fullscreen": {…}` → `fullscreen_enforcer.enforce()`.

## 2. Terminer un jeu

Deux entrées, une seule sortie.

```mermaid
sequenceDiagram
    participant pad as manette
    participant gm as gamepad_monitor
    participant r as routers/games.py
    participant pm as process_manager
    participant ws as ws.py
    participant ui as React

    alt le joueur appuie 2× sur PS en moins d'1 s
        pad->>gm: evdev BTN_MODE
        gm->>gm: _on_guide_pressed()
        gm->>r: POST /api/games/kill
    else l'émulateur se termine seul
        Note over pm: _watch() attendait déjà
    end
    r->>pm: kill()
    pm->>pm: _flatpak_kill() — flatpak kill <app-id>
    pm->>pm: _proc_kill() — SIGKILL sur le groupe de processus
    pm->>pm: _watch() se réveille : elapsed = now - _start_time
    alt elapsed > 5 s
        pm->>pm: INSERT/UPDATE playtime (ON CONFLICT DO UPDATE)
    end
    pm->>ws: broadcast("game:finished", {elapsed})
    ws-->>ui: game:finished → efface la session, masque l'overlay
```

Pourquoi c'est construit ainsi :

- **evdev, pas le navigateur.** Chromium masque souvent le bouton Guide, et
  l'UI est de toute façon enfouie sous un émulateur plein écran.
- **Double appui.** Un seul appui sur Guide ne doit jamais tuer un jeu par
  accident (`GUIDE_DOUBLE_PRESS_MS`, dupliqué dans le hook frontend).
- **`flatpak kill` d'abord.** Un SIGTERM au wrapper `flatpak` n'atteint jamais
  l'application dans le bac à sable.
- **SIGKILL, jamais SIGTERM.** Plusieurs émulateurs répondent au SIGTERM par
  une boîte de dialogue de confirmation, impossible à cliquer à la manette.
- **Le plancher de 5 s.** Un émulateur qui meurt aussitôt n'est pas une
  session de jeu.

## 3. Résoudre une jaquette

```mermaid
flowchart TD
    start["GET /api/covers/{system}/{file}"] --> cache{"emu/covers/&lt;system&gt;/&lt;nom&gt;<br/>.png / .jpg existe ?"}
    cache -->|oui| serve["FileResponse"]
    cache -->|non| miss{"fichier .miss<br/>de moins de 7 jours ?"}
    miss -->|oui| none["404 — l'UI affiche la tuile de repli"]
    miss -->|non| t2["local_media.extract_icon()"]
    t2 -->|"PS3 ICON0.PNG · PS4 icon0.png<br/>PSP ICON0.PNG via iso9660"| serve
    t2 -->|rien| t3["local_media.disc_id()"]
    t3 -->|"en-tête GC/Wii · SYSTEM.CNF PS1/PS2"| fetch["_fetch_by_id() → GameTDB / xlenore"]
    fetch -->|trouvé| serve
    fetch -->|rien| t4["scraper.fetch_cover()"]
    t4 -->|"CDN libretro (_name_variants)"| serve
    t4 -->|"puis TheGamesDB si clé fournie"| serve
    t4 -->|rien| write["écrit .miss"] --> none
```

Point d'entrée : `services/cover_pipeline.py:resolve(system, filename, refresh)`.
`?refresh=1` ignore le cache et le `.miss`.

Les niveaux 2 et 3 sont **hors-ligne et exacts** — ils lisent le jeu lui-même,
donc ne se trompent jamais d'identification. Le niveau 4 est de la
correspondance floue par nom, atteint seulement quand le jeu ne porte aucune
identité.

## 4. Mise à jour OTA

```mermaid
sequenceDiagram
    participant ui as UpdatePage
    participant r as routers/update.py
    participant sh as update/linux.sh
    participant gh as GitHub
    participant sd as systemd

    ui->>r: GET /api/update/check
    r->>gh: dernière release
    r->>r: _version_int() — comparaison tolérante
    r-->>ui: {update_available, current, latest}
    ui->>r: POST /api/update/apply
    r->>sh: spawn, _pump() relaie stdout
    r-->>ui: lignes de progression via WS
    sh->>gh: télécharge gamecore-ota.tar.gz
    sh->>sh: rsync -a --exclude .venv/ emu/ config/ emu-configs/ assets/{overlays,logos}/
    sh->>sh: rsync --delete frontend/dist/ et frontend/src/
    sh->>sh: écrit VERSION, pip install, purge le cache Electron
    sh->>sd: systemctl start --no-block gamecore-restart.service
    Note over sh,sd: détaché volontairement — le script vit dans le cgroup<br/>du backend et se tuerait lui-même autrement
```

## 5. Veille, et réveil

```mermaid
stateDiagram-v2
    [*] --> Actif
    Actif --> Économiseur: inactivité > délai économiseur
    Économiseur --> Endormi: inactivité > délai sommeil
    Endormi --> Actif: on_input() depuis evdev
    Économiseur --> Actif: on_input()
    Actif --> Actif: un jeu tourne (veille bloquée)
```

`services/standby.py:run()` sonde. `_enter(stage)` pilote les transitions,
`_screen(False)` coupe l'écran via DPMS, `_governor("powersave")` abaisse le
CPU (optionnel, nécessite une règle sudoers). `on_input()` est appelée depuis
la boucle evdev de `gamepad_monitor` — c'est pour cela qu'une manette réveille
le boîtier alors même que l'UI dort et que le navigateur n'écoute pas.

## 6. Authentification LAN

```mermaid
sequenceDiagram
    participant c as navigateur (LAN)
    participant cad as Caddy :8443
    participant core as backend /api/auth
    participant addon as save-manager :8772

    c->>cad: GET /saves/
    cad->>core: forward_auth → GET /api/auth/verify (cookie)
    alt cookie absent ou invalide
        core-->>cad: 302 /login?next=/saves/
        cad-->>c: page de login (proxifiée sans auth)
        c->>core: POST /api/auth/login {password}
        core->>core: blocked_for(ip) ? vérification argon2
        core->>core: _set_session() → cookie gc_session
    else valide
        core-->>cad: 200 + X-GC-User
        cad->>addon: requête proxifiée + X-GC-User
    end
```

Le `/api/*` du cœur est **403 depuis le LAN, toujours**. Les addons ne
contiennent aucun code d'authentification — Caddy est le point d'application.
La TV contourne tout cela en loopback.

## 7. Cycle de vie d'un overlay

```mermaid
sequenceDiagram
    participant ui as React
    participant el as Electron main
    participant mon as overlay_monitor.py
    participant x as X11

    ui->>el: overlayStart(system_id)
    el->>mon: {"cmd":"watch", system_id, config}
    loop jusqu'au timeout (watch_timeout_s)
        mon->>x: find_window(wm_classes) via _NET_CLIENT_LIST
    end
    mon-->>el: window:waiting … puis window:ready {rect}
    el->>el: createOverlayWindow() + loadURL(/overlay?…)
    mon->>x: force_rect() — ClientMessage pour quitter le plein écran, puis configure
    Note over mon,x: écrire _NET_WM_STATE directement efface TOUS les états<br/>et désynchronise le WM — toujours passer par le ClientMessage
    mon-->>el: window:closed (l'émulateur s'est fermé)
    el->>el: destroyOverlayWindow()
```

Toute la fonctionnalité est désactivée quand `WAYLAND_DISPLAY` est défini
(`_WAYLAND_SESSION`), silencieusement. Une machine de dev sous Wayland ne
reproduira jamais un bug d'overlay.
