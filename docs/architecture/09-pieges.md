# 9 — Pièges

Des invariants qui ressemblent à du bruit jusqu'au jour où ils cassent quelque
chose. Chacun est ici parce qu'il a déjà coûté une session de débogage.

## Processus et cycle de vie

**`_launching` est réservé de façon synchrone.**
`ProcessManager.launch()` le pose avant le premier `await`. Deux lancements
concurrents passeraient sinon tous deux le test `is_running` pendant que le
premier attend encore le lancement, et le boîtier ferait tourner deux
émulateurs.

**`start_new_session=True` est structurant.**
Il place l'émulateur dans son propre groupe de processus. Sans cela, le
`killpg` de `_proc_kill()` vise le groupe du backend — le bouton « arrêter »
tuerait GameCore.

**Ne jamais envoyer SIGTERM à un émulateur.**
Plusieurs y répondent par une confirmation impossible à cliquer à la manette.
`_proc_kill()` va directement au SIGKILL. Pour Flatpak,
`flatpak kill <app-id>` doit venir d'abord : un signal au wrapper n'atteint
jamais le bac à sable.

**Un plantage en une image n'est pas une session de jeu.**
`_watch()` n'enregistre le temps de jeu qu'au-delà de 5 s, sinon un émulateur
qui boucle sur un crash gonflerait les statistiques.

## Câblage du backend

**`/ws` doit rester enregistré avant le montage statique `/`.**
Le fourre-tout de la SPA (`html=True`) avale sinon la requête d'upgrade
WebSocket, et l'UI cesse silencieusement de recevoir les événements.

**Les montages statiques font un `mkdir` d'abord.**
La boucle de `main.py` crée chaque dossier avant de le monter. Un montage
conditionnel décidé à l'import laissait `/covers` mort jusqu'au redémarrage sur
un clone neuf.

**`_hot_load()` relit le JSON à chaque appel.**
Éditer `systems.json` sur le boîtier prend effet sans redémarrage — et une
erreur de syntaxe casse l'API dès la requête suivante.

**`config/` est l'identité du boîtier.**
Jamais dans git, jamais touché par l'OTA. Écraser l'un de ces fichiers est une
perte de données : disposition de la bibliothèque, mot de passe, registre des
addons, historique de jeu.

## Entrée

**Pendant qu'un jeu tourne, l'UI ignore tout événement manette sauf `gp:guide`.**
Sinon l'entrée de l'émulateur pilote le lanceur caché derrière le jeu.

**Guide exige un double appui en moins d'1 s.**
Appliqué à la fois dans `useGamepad.ts` et `gamepad_monitor.py`. Un appui
unique ne doit jamais tuer un jeu en cours.

**Le navigateur ne voit pas le bouton Guide de façon fiable.**
Chromium le masque souvent, et l'UI n'a pas le focus sous un émulateur plein
écran. Le veilleur evdev du backend est le chemin principal ; le navigateur est
le repli.

**L'écran manette se ferme par un double □, et ○ ne le ferme pas.**
Chaque bouton y est une cible de test, donc aucun bouton ne peut être une
action. `CONTROLLER_CLOSE_MS` dans `App.tsx`.

## Affichage

**Les overlays ne fonctionnent que sous X11.**
`_WAYLAND_SESSION` désactive la fonctionnalité quand `WAYLAND_DISPLAY` est
défini — silencieusement, par conception. Une machine de dev sous Wayland ne
reproduira jamais un bug d'overlay.

**Quitter le plein écran par un ClientMessage, pas par une écriture de propriété.**
EWMH réserve `_NET_WM_STATE` au gestionnaire de fenêtres dès qu'une fenêtre est
mappée. L'écrire directement retire bien le plein écran sur certains WM, mais
efface **tous** les états d'un coup (`_NET_WM_STATE_ABOVE` compris) et
désynchronise le WM : la fenêtre ignore ensuite toute demande d'état.
`force_rect()` envoie le ClientMessage.

**`_display_env()` retire `WAYLAND_DISPLAY`.**
Les émulateurs Qt lancés depuis l'unit systemd tenteraient sinon Wayland et
échoueraient en silence.

**Les boutons de manette ne sont pas un « geste utilisateur ».**
Chromium garde WebAudio suspendu jusqu'à une entrée souris ou clavier. Sur un
kiosque uniquement manette, l'UI serait muette à jamais — d'où
`autoplay-policy: no-user-gesture-required` dans `electron/main.js`.

**`XDG_RUNTIME_DIR` ou aucun son du tout.**
`start-ui.sh` l'exporte avant de lancer Electron. Un service systemd n'en
hérite pas, et Chromium atteint PipeWire par lui.

## Sécurité

### Des chaînes non fiables atteignent le HUD

Le texte des toasts HUD vient de diffusions WebSocket, qui incluent
`POST /api/addons/notify` (n'importe quel addon peut l'appeler) et les noms
d'appareils Bluetooth. `escHtml()` et `safeColor()` existent pour cela. Ne
jamais interpoler brut.

**`rom_path` est validé par confinement, pas par motif.**
`Path(rom_path).resolve().relative_to(roms_root.resolve())` dans
`launch_game()`. Sans cela, `/api/games/launch` exécute des binaires
arbitraires.

**Les envois d'overlay sont contrôlés par octets magiques.**
`_looks_like_image(head)` — le `Content-Type` du client ne prouve rien.

**Le cœur n'est jamais exposé au LAN.**
`/api/*` renvoie 403 à travers Caddy. La TV ne l'atteint qu'en loopback. Si
vous ajoutez un endpoint, partez du principe que le LAN ne pourra jamais
l'appeler.

## OTA

### Le piège du rebuild OTA

L'archive OTA livrait `frontend/dist` **sans** `frontend/src`. Un boîtier
faisait donc tourner un bundle frais de la CI par-dessus des sources figées à
l'installation initiale, et rien ne signalait la dérive.

Cela tient jusqu'à ce que quelque chose recompile *sur le boîtier* — le repli
de `update/linux.sh` quand une release ne livre pas de `dist/`, ou un
`npm run build` lancé à la main. L'un comme l'autre régénère `dist/` depuis des
sources vieilles de plusieurs mois et fait silencieusement régresser l'UI.

Cela a coûté une vraie fonctionnalité : le bouton « Scan mapping » livré en
v1.0.62 manquait sur un boîtier en v1.0.66, alors que sa route backend était
active et répondait depuis le début.

L'archive livre désormais `frontend/` en entier et `linux.sh` synchronise
`frontend/src/` avec `--delete`. **Gardez-le ainsi**, et retenez la
conséquence : les modifications locales du frontend d'un boîtier sont effacées
à la mise à jour suivante. Poussez-les.

**Le script de mise à jour ne doit pas redémarrer les services lui-même.**
`update/linux.sh` tourne dans le cgroup du backend. Il démarre à la place
l'unit détachée `gamecore-restart.service` avec `--no-block` — un
`systemctl restart` direct tuerait le script en pleine mise à jour.

**`VERSION` est écrit par le script de mise à jour, pas par git.**
Le dépôt le fige à `v1.0.0` ; la vraie version vit dans les tags et dans le
fichier que l'OTA écrit. C'est pourquoi `VERSION` apparaît toujours modifié
dans `git status` sur un boîtier.

## Tests

**Chromium headless ne déclenche jamais `requestAnimationFrame` sous
`--virtual-time-budget`.**
Le splash (piloté par rAF) et la boucle manette à 60 fps se figent tous deux :
rien ne se passe et chaque assertion échoue pour la mauvaise raison. À
polyfiller :

```js
window.requestAnimationFrame = cb => window.setTimeout(() => cb(performance.now()), 16)
window.cancelAnimationFrame = id => window.clearTimeout(id)
```

**Tester le code manette ne demande aucun matériel.** Remplacez
`navigator.getGamepads` par une fausse manette et laissez tourner la vraie
boucle.

**`npm run build` est la vérification complète la moins chère de l'UI** — il
lance `tsc` d'abord, donc une erreur de type fait échouer le build.

**Deux drapeaux `DEBUG`.** `backend/config.py` et `electron/main.js`. Les deux
doivent valoir `false` sur un boîtier ; `DEV` (Electron chargeant Vite) vaut
`DEBUG && ELECTRON_DEV=1`.
