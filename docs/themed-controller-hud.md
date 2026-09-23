# Notifications manette et batterie : rapport de livraison

Branche : `feat/themed-controller-hud`, issue de `origin/main` au commit
`8502d7b9d89452924a350960533a8ec7128b1f95`. Travail dans le clone neuf
`~/gamecore-dev/hud-theming`. Aucun déploiement ni merge.

Le HUD natif lit maintenant les jetons du thème actif transmis par le renderer
à chaque notification. Electron filtre ces valeurs avec une liste blanche avant
de construire son propre document HTML. Le contrat déclaratif partagé
`electron/hud-tokens.json` contient les noms, formats autorisés, palettes de
repli et messages batterie ; il est aussi intégré au bundle frontend et inclus
dans le paquet Electron. Aucun HTML, JavaScript ou CSS arbitraire de thème n'est
transmis au HUD. Les textes restent échappés et une CSP interdit les scripts et
les chargements réseau.

Orbit utilise un panneau bleu nuit, Shelf un papier clair, Summer un panneau
crème. Les titres thémés passent à 20px, les textes à 18px ; la fenêtre thémée
fait 560×240 et commence à y=140 pour dégager les en-têtes des thèmes fournis.
Elle reste transparente, non focalisable, traversable par les clics et toujours
au premier plan. Le repli historique reste à 440×100, y=66.

Le rendu React par défaut utilise les mêmes jetons. L'offre « not recognised /
Map it now » reste dans l'application, avec son action et sa durée de 30 secondes.
Les autres durées restent à 10 secondes. Le HUD remplace toujours la notification
précédente ; la file React et le routage ne changent pas.

La batterie affiche `Controller N battery at X%`, puis :

| Niveau | Texte anglais |
| --- | --- |
| ≤ 25 % | Keep a charger nearby. |
| ≤ 15 % | Battery is running low. |
| ≤ 10 % | Battery very low — connect a charger. |
| ≤ 5 % | Battery critical — charge it now. |

La sélection se fait sur le niveau réel, notamment lorsqu'il saute plusieurs
seuils. Le backend conserve ses seuils `(25, 15, 10, 5)`, son réarmement et sa
limitation à une alerte par franchissement ; seule sa docstring est corrigée.
Les niveaux non numériques, non finis ou hors de 0–100 sont rejetés par les
rendus. Les versions des thèmes augmentent pour permettre leur livraison future :
Orbit 3.7.3, Shelf 3.9.8, Summer 3.2.3, squelette 0.3.1. Leurs versions d'API
restent inchangées : Orbit est en API 7, Shelf et Summer sont en API 4 dans ce
checkout, contrairement à l'hypothèse du prompt.

Le contrat est documenté dans [le README du squelette](../config/themes/_skeleton/README.md).
Sur `:root`, préfixe `--gc-hud-` :

| Suffixes | Format |
| --- | --- |
| panel, border, text | Couleur hexadécimale à 6 ou 8 chiffres |
| radius, blur | Entier de 0px à 32px |
| font | Liste de familles locales non entourées de guillemets, avec repli générique |
| connected, disconnected, warning | Couleurs des états manette |
| battery-25, battery-15, battery-10, battery-5 | Couleurs des quatre gravités |

Chaque valeur invalide est ignorée ; sans jeton valide le style historique est
conservé. Un panneau clair sans palette explicite reçoit des couleurs foncées
lisibles. Les couleurs des trois thèmes fournis sont testées à 4,5:1 minimum.
Les familles sont locales : aucune police web n'est importée dans le HUD, une
famille absente utilise le prochain repli disponible.

Les captures sont dans `~/Downloads/gamecore-hud-captures/` : ouvrir `index.html`.
Elles utilisent Chromium headless, sans DISPLAY ni WAYLAND_DISPLAY, un profil
temporaire et le code réel de `main.js` évalué dans le banc VM. Aucun backend ou
Electron de production n'est lancé. Les jetons sont lus par `getComputedStyle`
sur les feuilles CSS réelles. Le rendu React est celui de `DefaultToastsView`,
compilé avec les dépendances déjà présentes.

| Apparence | Planche native avant/après | Repli React et bouton |
| --- | --- | --- |
| Sans thème | none-comparison.png | none-react.png |
| Orbit | orbit-comparison.png | orbit-react.png |
| Shelf | shelf-comparison.png | shelf-react.png |
| Summer | summer-comparison.png | summer-react.png |

72 PNG : 64 captures natives individuelles (connexion, déconnexion, système non
configuré, configuration automatique désactivée, batterie 25/15/10/5 ; avant et
après ; quatre apparences), quatre planches comparatives et quatre captures React.
Les documents HTML et jetons calculés sont également conservés. Les planches et
les rendus React ont été examinés visuellement. Aucun des cas capturés ne dépasse
la hauteur de la fenêtre (`layout.json`). Les quatre cas manette sans thème sont
identiques avant/après, pixel pour pixel ; les textes/couleurs batterie évoluent
volontairement, même sans thème.

Reproduction :

```sh
node electron/scripts/capture-hud.cjs /tmp/gamecore-hud-captures 8502d7b9d89452924a350960533a8ec7128b1f95
```

Inventaire des autres affichages, laissés intacts :

| Affichage | Constat |
| --- | --- |
| `frontend/src/components/TopBar/index.tsx`, `ControllerBattery` | Couleurs vert/jaune/rouge et texte codés en dur ; seuils >60 / >20, sans les quatre gravités. Défaut de personnalisation similaire si ce composant est réutilisé tel quel. |
| `config/themes/orbit/views/topbar.js` | En-tête propre au thème, sans pastilles batterie/joueur dans ce checkout. |
| `config/themes/shelf/views/topbar.js` | Jusqu'à quatre joueurs, jauge quatre segments ; styles Shelf, état bas à un segment (≤25 %), couleur rouge fixe dans son CSS. Déjà thémé, pas la palette historique du HUD. |
| `config/themes/summer/views/topbar.js` | Jusqu'à quatre joueurs, quatre segments ; variables Summer et bordure d'alerte à ≤25 %. Déjà thémé. |
| `frontend/src/components/modals/GamepadModal.tsx` et `gamepad/DefaultGamepadView.tsx` | Le rendu par défaut reçoit `ControllerBattery`, donc les mêmes couleurs fixes ; textes surtout blancs et quelques accents thémables. |
| `config/themes/orbit/views/controller.js` | Pourcentages et joueur en texte dans les lignes du thème, sans jauge ni quatre couleurs de gravité. Déjà thémé. |
| `config/themes/shelf/views/gamepad.js` et `summer/views/gamepad.js` | Rendus propres aux thèmes ; première manette affichée avec jauge quatre segments, pourcentage et charge. Ne reprennent pas le HUD historique. |
| `gamepad/ControllerArt.tsx`, `MappingWizard.tsx` | Diagramme et assistant partagés avec plusieurs couleurs fixes ; pas des notifications. Aucune modification. |

Vérifications finales : voir la table complétée ci-dessous. Les commandes Python
utilisent le venv du clone ; les tests isolent leur racine de données, HOME et
runtime dans des répertoires temporaires via le `conftest.py` existant.

| Commande | Résultat |
| --- | --- |
| `.venv/bin/ruff check .` | OK |
| `.venv/bin/shellcheck -S warning $(git ls-files '*.sh') install/bin/*` | OK |
| `.venv/bin/python3 scripts/check-catalog.py` | 17 packs OK |
| `.venv/bin/python3 scripts/gen-catalog.py --check` | Fichiers générés à jour |
| `.venv/bin/python3 -m pytest backend/tests catalog -m "not network"` | 2035 réussis, 6 ignorés, 4 exclus ; aucun échec |
| `cd frontend && npm run test:run` | 57 fichiers, 544 tests réussis |
| `cd frontend && npm run build` | TypeScript et Vite OK |
| `cd electron && npm test` | 33 tests réussis |
| Captures et vérification des dimensions | 72 PNG ; aucun cas capturé tronqué |
| Comparaison du repli natif sans thème | 4 cas manette identiques pixel pour pixel |

Les nouveaux tests couvrent les jetons malveillants (`red;}</style><script>`,
`url(javascript:...)`, police avec guillemets), le repli, l'échappement des textes,
les quatre gravités, les couleurs claires, le changement de thème entre deux
envois IPC, les propriétés de fenêtre et le maintien de l'offre de mapping.
Une erreur de jeu utilise aussi la palette critique lorsque le panneau partagé
est clair, pour ne pas introduire une régression de contraste.

Contrastes minimaux mesurés, y compris composition du panneau Orbit sur noir et
sur blanc : Orbit **5,60:1**, Shelf **6,15:1**, Summer **6,03:1**.
Les mesures sont conservées dans `verification.json`.

Le premier passage Python a trouvé quatre versions de thèmes non incrémentées :
elles ont été corrigées, puis toute la suite a été relancée et a réussi. Aucun
échec préexistant sur `main` n'a dû être isolé. Les avertissements restants sont
ceux des outils : API CJS Vite, taille du bundle >500 kB, avertissements de test
React/Node et deux dépréciations Python. Les journaux finaux sont dans `logs/`
du dossier de captures.

Limites : la lisibilité sur la TV à trois mètres, l'empilement réel au-dessus
d'un émulateur et le rendu du compositeur X11/Wayland restent à valider sur le
boîtier après revue. Le flou CSS est déclaré et partagé, mais ne peut pas flouter
le contenu d'une autre fenêtre native ; les captures ne prétendent pas vérifier
cet effet. Une police uniquement fournie par `@font-face` dans le renderer n'est
pas transférée au HUD. Les thèmes tiers doivent réserver l'espace d'en-tête
indiqué et vérifier le contraste de leurs propres surcharges. Les tests réseau
sont exclus conformément à la consigne.
