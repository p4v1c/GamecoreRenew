# 5 — Frontend

React 18 + Vite + Zustand + Framer Motion. **Aucun fichier CSS** — le style est
en objets inline à côté du balisage, ce qui explique la longueur des composants.

```
src/
  main.tsx                  createRoot
  App.tsx           157 l.  coquille, bindings manette globaux, orchestration des modales
  store/index.ts     57 l.  le store Zustand
  api/index.ts      119 l.  enveloppes fetch typées, BASE = "/api"
  hooks/
    useGamepad.ts   215 l.  API Gamepad → CustomEvents + état continu
    useWebSocket.ts  73 l.  push du backend → registre de handlers
  components/…
  lib/…
```

## Store — `store/index.ts`

Un seul store Zustand, aucun provider de contexte.

| Domaine | Champs | Actions |
|---|---|---|
| Navigation | `screen`, `selectedSystemId`, `selectedGameIdx`, `gridFocusIdx`, `gridPage` | `goHome()`, `goLibrary(id)`, `setGridFocus`, `setGridPage`, `setSelectedGameIdx` |
| Verrou de focus | `modalDepth` | `openModal()`, `closeModal()` |
| Alimentation | `powerPending` | `setPowerPending(action)` |
| Session | `sessionGameKey`, `sessionSystemId` | `setSession(gameKey, systemId)` |

`modalDepth` est le mécanisme qui empêche les handlers manette de se déclencher
deux fois. Chaque modale l'incrémente au montage et le décrémente au démontage
(`closeModal` borne à 0). Les écrans se retirent quand il est non nul :

```ts
const blocked = () => screenRef.current !== 'home' || modalDepthRef.current > 0
```

`powerPending` fige l'UI pendant l'extinction du système, pour que rien ne
resurgisse à l'écran en pleine coupure.

## Le bus d'événements manette — `hooks/useGamepad.ts`

`useGamepad()` fait tourner une boucle `requestAnimationFrame` et émet des
`CustomEvent` sur `window`. N'importe quel point de l'arbre s'y abonne avec
`onGp(event, handler)` et récupère une fonction de nettoyage.

```mermaid
flowchart LR
    gp["navigator.getGamepads()"] --> poll["poll() @60fps"]
    poll -->|front détecté| emit["emit(name)"]
    emit --> snd["playSound(soundForGpEvent(name))"]
    emit --> win["window.dispatchEvent(CustomEvent)"]
    win --> onGp["abonnés onGp(...)"]
    poll -->|instantané brut| frame["frameListeners"]
    frame --> state["useGamepadState()"]
    state --> art["ControllerArt"]
```

### Les événements

```
gp:dpad-up   gp:dpad-down   gp:dpad-left   gp:dpad-right
gp:confirm (A/✕)   gp:back (B/○)   gp:y (Y/△)   gp:x (X/□)
gp:menu (Start/Options)   gp:power (Select/Share)   gp:guide (PS/Home)
gp:l1   gp:r1   gp:l2   gp:r2
gp:connected(name)   gp:disconnected
```

### Les trois invariants

1. **Pendant qu'un jeu tourne, tout événement est supprimé sauf `gp:guide`.**
   `isPlaying()` lit Zustand de façon synchrone. Sinon l'entrée de l'émulateur
   piloterait le lanceur derrière le jeu. Reprend le comportement du C++
   d'origine.
2. **`gp:guide` exige un double appui en moins de `GUIDE_DOUBLE_PRESS_MS` (1 s).**
   Un appui unique ne doit jamais tuer un jeu par accident.
3. **Le stick gauche est converti en événements de croix sur front**, avec
   `DEAD_ZONE = 0.5`, pour qu'un stick maintenu émette une fois et non 60 fois
   par seconde.

### Deux API, volontairement

| API | Nature | Pour |
|---|---|---|
| `onGp(event, handler)` | déclenchée sur front | navigation, actions — « □ a été pressé » |
| `useGamepadState()` / `onGamepadFrame(cb)` | continue | dessin — « □ est maintenu », « le stick est à 40 % » |

`GamepadState` = `{connected, pressed[], values[], axes[]}`, indexé par
`GP_BTN` (le mapping standard). Les valeurs sont quantifiées au 1/50e pour
qu'un stick au repos ne provoque aucun rendu. Le seul consommateur est l'écran
manette.

### Indices de boutons — `BTN`

```
A 0   B 1   X 2   Y 3   L1 4   R1 5   L2 6   R2 7
SHARE 8   OPTIONS 9   L3 10   R3 11
DPAD ↑12 ↓13 ←14 →15   GUIDE 16
```

## WebSocket — `hooks/useWebSocket.ts`

Socket unique au niveau du module sur `ws://<host>/ws`, reconnexion toutes les
3 s à la fermeture. `onWsEvent(event, handler)` enregistre dans une
`Map<string, Set<Handler>>` et renvoie un désabonnement.

### Table des événements WebSocket

| Événement | Émis par | Charge utile | Effet UI |
|---|---|---|---|
| `game:started` | `process_manager.launch()` | `game_key`, `system_id` | Electron affiche le bezel |
| `game:finished` | `process_manager._watch()` | + `elapsed` | efface la session, masque l'overlay |
| `game:running` | `ws.connect()` | jeu en cours | un client arrivé tard se remet à jour |
| `gp:battery` | `battery.run()` | `name`, `level`, `threshold` | toast, ou HUD natif en jeu |
| `gp:guide` | `gamepad_monitor` | — | demande d'arrêt relayée |
| événements de veille | `standby._enter()` | étape | pilote `Screensaver` |
| événements d'addons | `POST /api/addons/notify` | libre | ex. rafraîchir après un envoi de ROM |

## Composants

| Fichier | Lignes | Rôle |
|---|---|---|
| `App.tsx` | 157 | monte tout, porte les quatre bindings manette globaux et `CONTROLLER_CLOSE_MS` |
| `components/Splash.tsx` | 374 | animation de démarrage en rAF ; `T_IMPACT`, `HOLD_MS` et `FRAGMENTS` pilotent la chronologie |
| `components/HomeScreen/index.tsx` | 282 | grille 4×2 (`COLS`, `ROWS`, `PER_PAGE`), pagination, focus |
| `components/HomeScreen/SystemCard.tsx` | 96 | une tuile ; `getColor(system)` retombe sur `SYSTEM_COLORS` |
| `components/LibraryScreen/index.tsx` | 458 | grille de jeux, recherche, pagination, `GameMetaPanel`, `CoverImage` |
| `components/TopBar/index.tsx` | 134 | horloge, IP, stockage, `ControllerBattery`, `TBtn` |
| `components/Screensaver.tsx` | 136 | diaporama de veille, `ROTATE_MS = 9000` |
| `components/OverlayScreen/index.tsx` | 109 | ce que rend la fenêtre Electron transparente |
| `components/modals/SettingsModal.tsx` | 88 | menu ; les pages vivent dans `settings/` |
| `components/modals/PowerModal.tsx` | 136 | Scan mapping · Restart · Shutdown, `POWER_FAILSAFE_MS = 10000` |
| `components/modals/GamepadModal.tsx` | 111 | l'écran manette |
| `components/modals/gamepad/ControllerArt.tsx` | 323 | le dessin de la manette — voir plus bas |
| `components/ui/index.tsx` | 133 | `Overlay`, `OverlayLabel`, `BackHeader`, `Toggle`, `SliderRow`, `Chip`, `Bars`, `hexToRgb`, `fmtTime`, `fmtDate` |
| `components/ui/VirtualKeyboard.tsx` | 205 | clavier à l'écran (mots de passe WiFi, recherche) |
| `components/ui/Toasts.tsx` | 117 | pile en haut à droite, `TOAST_MS = 10000` |

### Pages de réglages — `components/modals/settings/`

`WifiPage` (218), `AudioPage` (233), `BluetoothPage` (189), `StandbyPage`
(102), `UpdatePage` (143), `DesktopPage` (33). Toutes partagent
`useSubPageGamepad(onBack, onClose, enabled)` (18 l.), qui lie ○ → retour et
□ → fermer de façon cohérente : aucune page ne le réimplémente.

`AudioPage` nomme ses lignes (`ROW_VOLUME`, `ROW_OUTPUT`, `ROW_UI_TOGGLE`,
`ROW_UI_VOLUME`, `ROW_COUNT`) plutôt que de les indexer par numéro — à copier
en ajoutant une page.

### `ControllerArt.tsx` — le dessin de la manette

Porté depuis une maquette : des couches en position absolue dans l'espace
**372×238** de la maquette, mises à l'échelle en bloc par la prop `scale`
(défaut 1.35).

| Symbole | Rôle |
|---|---|
| `at(cx, cy, w, h)` | boîte absolue positionnée **par son centre** — comment chaque contrôle est placé |
| `DPAD_HOME` / `STICK_HOME` | les deux points d'ancrage qui **s'échangent** en disposition Xbox |
| `RSTICK`, `FACE` | ancrages fixes |
| `STICK_TRAVEL = 13` | px de débattement du stick à fond — le réglage de calibration |
| `Trigger` | analogique : s'enfonce selon `values[L2/R2]`, la luminosité suit |
| `Bumper`, `Pill`, `DpadArm`, `FaceButton`, `Socket`, `Stick` | les pièces |
| `glyph(seat, isXbox, pressed)` | formes PlayStation ou lettres Xbox |

Le logement est dessiné séparément du stick pour que le débattement ait un
rebord fixe contre lequel se lire — sans lui, le capuchon semble flotter.

## `lib/`

| Fichier | Exports |
|---|---|
| `sounds.ts` | `playSound(name)`, `soundForGpEvent(event)`, `soundSettings`, `getAudioContext`. Les sons sont **synthétisés** par `note()` sur un `AudioContext` partagé — aucun fichier audio. Réglages persistés en `localStorage` (`gc:uiSounds`, `gc:uiSoundsVolume`) |
| `systemColors.ts` | `SYSTEM_COLORS`, palette de repli par identifiant de système |
| `formatGameName.ts` | `formatGameName(raw)` — retire la région et les suites de langues en fin de nom (`REGION_RE`, `LANG_SEQ_RE`) |

## `api/index.ts`

`BASE = '/api'`, `get<T>` / `post<T>` génériques, et l'objet `api` regroupant
`systems`, `games`, `playtime`, `sysinfo`, `update`, `wifi`, `audio`,
`bluetooth`, `addons`, `standby`. Types exportés pour l'UI : `SystemEntry`,
`GameEntry`, `GameMeta`, `PlaytimeEntry`, `SysInfo`.

Même origine par construction — la SPA est servie par le backend, donc aucune
URL de base et aucun CORS.
