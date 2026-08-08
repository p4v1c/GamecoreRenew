# État de `~/.var/app` — ce que les sessions passées ont écrit

P1 a découvert que la suite de tests écrivait dans les **vraies** configurations
d'émulateur : `TestClient(main.app)` démarre le lifespan, le lifespan démarre
`gamepad_monitor.run()`, qui scanne le vrai `/dev/input` et profile la manette
trouvée contre `Path.home()`. Le correctif dans `conftest.py` (`045d7fc`) protège
l'avenir. **Il ne protège pas le passé** : chaque `pytest` lancé pendant l'audit,
pendant P13 et avant a pu modifier la boîte.

Cette enquête **mesure**, elle ne répare pas. Aucune écriture, aucun `mv`, aucune
restauration n'a été faite dans `~/.var/app` : tout ce qui suit vient de
`find -printf`, de `diff` en lecture, du journal systemd et de `git`.

---

## 1. La limite qu'il faut poser d'abord

**Un `mtime` n'enregistre que la DERNIÈRE écriture.** Les six fichiers de config
les plus susceptibles d'avoir été touchés par un `pytest` ont tous été réécrits
le 2026-08-08 à 21:43 par le démon GameCore vivant, en réaction à une vraie
DualShock 4. L'écriture que P1 a mesurée — azahar et melonDS à 20:55:33 — **a été
écrasée**. Elle n'est plus observable.

Ce document ne peut donc pas produire la liste complète demandée. Il produit ce
qui reste : l'attribution de chaque `mtime` encore visible, et ce que la
comparaison de contenu avec les `.bak-*` permet encore de dire.

---

## 2. Attribution des `mtime`, fenêtre de session par fenêtre de session

Fenêtres bornées par les horodatages de commit de `main`.

| fenêtre (2026-08-08) | session | fichiers écrits dans `~/.var/app` | dont **cibles de générateur** |
|---|---|---|---|
| 13:30–14:10 | audit, passes 1-6 | 901 | **aucune** |
| 14:10–17:10 | — | 0 | — |
| 17:10–20:35 | `fix/audit-urgences` | **0** | — |
| 20:35–21:15 | démarrage de P1 | 434 | *(voir §3)* |
| 21:15–21:45 | P1 | 7 | 7 |
| 22:11–… | P14 (cette session) | **0** | — |

**Les 901 fichiers de la fenêtre d'audit ne sont pas des configs** : trophées
RPCS3, `dev_hdd1/caches`, et l'installation d'un jeu (`dev_hdd0/game/BCUS98124/…`
à 13:37). Aucun des onze fichiers déclarés dans `controllers.target` n'y figure.
Le propriétaire jouait ; la suite de tests n'a rien écrit là.

**Les 7 fichiers de la fenêtre P1 sont le démon vivant, pas `pytest`** — et c'est
le journal qui le prouve, à la seconde près :

```
21:43:04  kernel: Registered DualShock4 controller
21:43:10  python3[187251]: > TEXT '{"event": "gp:connected", "data": {"player": 1, …
21:43:10  → azahar/qt-config.ini, mgba/config.ini, melonDS.toml, rpcs3/Default.yml
21:43:21  kernel: Disconnected: /dev/input/event11
21:43:24  python3[187251]: > TEXT '{"event": "gp:disconnected", …
21:43:24  → dolphin/GCPadNew.ini, dolphin/WiimoteNew.ini
```

Le septième, `Ryujinx/Config.json` à 21:42:58, n'a **pas** d'évènement journal
correspondant. Le contenu tranche : comparé à son `.bak-ctrlmodel`, il ne diffère
que par `system_time_offset`, un répertoire de jeux ajouté, la géométrie de
fenêtre et `start_fullscreen`. **`input_config` est identique.** C'est Ryujinx
lui-même qui a sauvegardé son état, pas un générateur.

Même raisonnement pour `PCSX2.ini` (2026-08-08 00:10:35), seule autre cible de
générateur au `mtime` récent : `memcards/Mcd001.ps2` est écrit 54 secondes plus
tard. C'est une partie de jeu, pas une passe de profilage.

---

## 3. Le seul cas où l'attribution de P1 reste incertaine

P1 rapporte azahar et melonDS écrits à **20:55:33** par un `pytest`. Cet instant
tombe dans une fenêtre où **le propriétaire jouait à azahar** (écritures dans
`sdmc/`, `shaders/vulkan/`, `sysdata/play_time.bin` entre 20:45 et 20:52, puis
Ryujinx à 20:52).

- La moitié **azahar** est donc confondue : azahar écrit son propre
  `qt-config.ini` en quittant.
- La moitié **melonDS** ne l'est pas : melonDS ne tournait pas. Deux configs
  d'applications différentes écrites à la **même seconde** est la signature d'un
  balayage unique, pas de deux émulateurs sauvegardant chacun de leur côté.

L'attribution de P1 est donc probablement juste, et je ne peux pas la confirmer :
les deux `mtime` ont été écrasés à 21:43:10. **Je ne sais pas** trancher plus
finement, et il n'existe plus de trace permettant de le faire.

---

## 4. Ce qui a une sauvegarde, ce qui n'en a pas

`backup()` (`backend/services/configgen/helpers/base.py:33`) copie vers
`<fichier>.bak-ctrlmodel` — **et seulement si ce fichier n'existe pas déjà**.

C'est la propriété qui décide de tout ici, et elle a deux faces :

- **Les onze cibles déclarées ont toutes leur `.bak-ctrlmodel`.** Rien n'est
  irréversiblement perdu par rapport à l'état d'avant la première écriture de
  GameCore. Vérifié un par un, y compris `~/.local/share/duckstation/settings.ini`
  qui vit hors de `~/.var/app`.
- **Ce `.bak` date de la PREMIÈRE écriture, pas de la dernière.** Toutes les
  écritures suivantes — dont celles d'un éventuel `pytest` — se sont faites sans
  nouvelle sauvegarde. **Ce que le propriétaire aurait réglé à la main après la
  première écriture de GameCore n'est récupérable nulle part.** C'est la réponse à
  « signaler ce qui n'a pas de `.bak` » : ce n'est pas un fichier, c'est un
  intervalle de temps.

Aucun `.gamecore-tmp` résiduel : aucune écriture atomique n'a été interrompue.

---

## 5. Ce que la boîte porte encore — deux constats, laissés en place

### 5.1 Ryujinx : quatre entrées pour une seule manette

```
$ python3 -c "…" ~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json
  GamepadSDL2 Player1 '0-00000003-054c-0000-cc09-000000006800' 'PS4 Controller (0)'
  GamepadSDL2 Player2 '1-00000003-054c-0000-cc09-000000006800' 'PS4 Controller (1)'
  GamepadSDL2 Player3 '2-00000003-054c-0000-cc09-000000006800' 'PS4 Controller (2)'
  GamepadSDL2 Player4 '3-00000003-054c-0000-cc09-000000006800' 'PS4 Controller (3)'
```

Quatre joueurs, un seul GUID, aucune manette branchée. C'est exactement le défaut
que P1 corrige. **Il n'est pas causé par `pytest`** : les quatre entrées sont déjà
présentes à l'octet dans `Config.json.bak-ctrlmodel` (2026-07-22), donc elles
précèdent la première écriture de GameCore, et `input_config` n'a pas bougé depuis.
Le `.bak-multids4` du 2026-07-10 n'en contenait qu'une — elles sont nées entre ces
deux dates.

RPCS3, lui, est sain (`Player 1: PS4 Controller 1`, slots 2 à 4 `Device: ""`).

**Pourquoi c'est encore là :** `/opt/GameCore` tourne en **v1.0.143** (`88c48d6`).
P1 est publiée en **v1.0.144**. L'OTA n'a pas été prise. `grep` sur l'installation
vivante le confirme — `catalog/ryujinx/generator.py` n'y a aucune `release()`.
Le correctif existe et n'a pas atteint la machine.

### 5.2 Cemu : un profil joueur 2 vidé de ses liaisons

`controllerProfiles/controller1.xml` fait aujourd'hui 513 octets contre 2155 pour
son `.bak-ctrlmodel`, et contient `<mappings />` — un Wii U Classic Controller
nommé « Xbox One Controller », **sans une seule liaison**. La sauvegarde, elle,
porte un jeu de mappings complet et le profil nommé du propriétaire (« Le V »).

Deux choses en découlent :

- Un profil configuré sans liaisons est un joueur 2 que le jeu voit et qui ne peut
  pas bouger — la même classe de panne que les slots fantômes.
- **GameCore a écrit ce fichier**, puisque seul `backup()` crée un `.bak-ctrlmodel`.
  Or `catalog/cemu/pack.json` déclare `maxPlayers: 1` et
  `target: controllerProfiles/controller0.xml`, et le générateur actuel n'écrit que
  `opts["target"]`. Une version antérieure écrivait donc `controller1.xml` et
  `controller2.xml`, hors des cibles déclarées. Le code actuel ne le fait plus.

`Le V.xml`, le profil nommé du propriétaire, est intact (2155 o).

**Ni l'un ni l'autre n'a été touché.** Les deux ont une sauvegarde à côté. La
décision de restaurer appartient au propriétaire.

---

## 6. Le correctif `conftest.py` tient — et comment il a été vérifié

**L'empreinte avant/après ne suffit pas, et il faut le dire.** Elle a été prise
(69 591 fichiers, `find -printf '%T@ %s %p'` sur les onze arbres d'émulateur plus
`~/.local/share/duckstation`), la ligne de base complète a été lancée, l'empreinte
reprise :

```
$ diff before.txt after-pytest.txt && echo IDENTIQUE
IDENTIQUE
```

Zéro différence. Mais **aucune manette n'était branchée pendant cette exécution**,
et sans manette le moniteur n'a rien à profiler : la mesure serait passée même sans
le correctif. C'est précisément l'erreur de la passe 6 de l'audit, et la refaire en
la présentant comme une preuve aurait été pire que de ne rien mesurer.

La preuve qui tient est donc ailleurs — `backend/tests/test_home_isolation.py`,
qui ne dépend pas de ce qui est branché :

1. `configgen.HOME` n'est pas le home réel du compte, lu par `pwd.getpwuid()` et
   non par `$HOME` — la variable d'environnement étant justement l'objet du test,
   la relire ne prouverait que la cohérence de `conftest` avec lui-même ;
2. la cible de **chaque** pack profilant des manettes se résout sous ce `HOME`,
   ce qui est ce qui rend la ligne unique de `conftest` suffisante plutôt que
   chanceuse — une seconde porte se verrait ici.

Vérifié en réintroduisant le défaut, ligne `os.environ["HOME"]` retirée de
`conftest.py` :

```
E   AssertionError: configgen.HOME is the real account home (/home/pavic).
E   Every emulator config this suite touches is the box's own.
E   assert PosixPath('/home/pavic') != PosixPath('/home/pavic')
1 failed, 1 passed
```

Le test tombe sur son propre bug. Correctif remis, les deux repassent au vert.

---

## 7. Ce dont je ne suis pas sûr

- **L'ampleur réelle des dégâts passés est inconnue et le restera.** Les `mtime`
  qui l'auraient documentée ont été écrasés le soir même par le démon vivant. Tout
  ce que ce document peut affirmer, c'est qu'aucune écriture de `pytest` n'est
  encore *visible*, et que les deux anomalies trouvées (§5) ont une autre cause
  démontrable ou antérieure.
- **`pytest` a-t-il jamais écrit ailleurs que sur azahar et melonDS ?** Le chemin
  fautif profile tous les packs d'un coup, donc c'est probable, mais aucune trace
  ne subsiste pour l'établir.
- **Les écritures des sessions antérieures au 2026-08-06** n'ont pas été
  attribuées : je n'ai pas de bornes de session fiables au-delà de ce que `git log`
  donne, et les `.bak-ctrlmodel` (18-25 juillet) montrent qu'il s'est passé quelque
  chose à ces dates sans dire quoi.
