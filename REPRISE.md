# Reprise — fix/audit-urgences

Phase P13 : les trois constats de `AUDIT/FINDINGS.md` qui cassent chez
l'utilisateur (F-006, F-002, F-004), plus les commentaires qui mentent
(F-008, F-009).

## État

**Verte, et l'arbre de travail est propre.** Six commits, tous poussés. Rien
n'est à moitié fait : il n'y a aucun commit `WIP` et rien de non commité.

| | Départ | Maintenant |
|---|---|---|
| `ruff check .` | vert | vert |
| `shellcheck` | vert | vert |
| `check-catalog.py` | 17 pack(s) OK | 17 pack(s) OK |
| `gen-catalog.py --check` | up to date | up to date |
| backend `pytest` | 584 passed, 5 skipped, 4 deselected | **598 passed, 5 skipped, 4 deselected** |
| frontend `test:run` | 51 passed | 51 passed |
| frontend `build` | OK | OK |

- Le nombre de tests n'a **pas baissé** : +14, tous ajoutés par cette branche.
- **Aucun skip ni xfail nouveau.** Les 5 skips sont ceux de `main`, mot pour mot
  (4 dans `test_catalog_consumers.py` sur la migration du catalogue, 1 dans
  `test_generator_contract.py` parce que le pack N64 ne livre pas de seed).
- **Aucune fixture de caractérisation touchée** : 98 fichiers sous
  `catalog/*/tests/fixtures/` des deux côtés, `git diff main..HEAD` sur ce
  chemin est vide. Ce n'est pas une chance : ni azahar ni mgba ne figurent dans
  `WATCHED`/`SEED_DEST` de `backend/tests/characterisation.py`, ils ne sont donc
  pas une entrée du harnais. Vérifié avant de toucher aux seeds.

`AUDIT/repro/` reste **hors de `testpaths`** et se lance à part.

## Terminé

### Partie 1 — F-006 : deux seeds épinglaient une DualShock 4 (`040b464`)

- `catalog/mgba/seed/config.ini` : `device0=` vidé, section
  `[gba.input-profile.<GUID>]` retirée, et `[gba.input-profile.PS4 Controller]`
  retirée aussi — elle nommait la manette par son nom.
- `catalog/azahar/seed/qt-config.ini` : 17 clés porteuses du GUID retirées avec
  leur `\default=false` (34 lignes).
- `scripts/check-catalog.py` : garde **non déclarative**. Tout GUID de 32 hex
  dont le `vendor:product` décode vers une manette connue est refusé dans
  n'importe quel seed, sans que le pack le demande.
- `seedMustNotContain` ajouté à mgba et azahar pour les formes que le décodage
  ne voit pas.

Ordre respecté : garde d'abord, elle refuse les deux seeds d'origine
(17 constats), nettoyage ensuite. Puis vérifiée contre un GUID DS4 réinjecté
dans **pcsx2** (pack qui ne déclare rien) et contre un GUID Xbox — celui-ci
reconnu via `gamecontrollerdb.txt`, pas via la table de repli.

`AUDIT/repro/test_f006_seed_nomme_une_manette.py` : **41 passed** (2 failed au
départ).

### Partie 2 — F-002 : `restore()` sans la garde de `capture()` (`5aee2a0`)

- `block_disagrees()` appelée dans `restore()`, **avant** le test « déjà
  appliqué ».
- Le refus n'est **pas un `Skip`** — un Skip veut dire « réessaie », et le
  moniteur réessaierait toutes les 3 s indéfiniment.
- L'inverse qui manquait : `snapshots.forget()`, `forget_mapping()`,
  `DELETE /controllers/scan-mapping`, et le bouton « Forget mapping » dans
  `PowerModal.tsx`.
- Tests dans `backend/tests/` et non seulement dans `AUDIT/repro/` : ce dernier
  est hors de `testpaths`, s'y fier aurait laissé le correctif sans garde en CI.

`AUDIT/repro/test_f002_restore_sans_garde.py` : **3 passed, 6 skipped**.
Les skips sont passés de 2 à 6 — voir « Incertitudes ».

### Partie 3 — F-004 : evdev inaccessible, aucune trace (`ead138d`)

- Refus comptés, une ligne qui nomme le groupe `input` ; `ImportError` loggée en
  erreur.
- `except PermissionError` placé **avant** `except OSError` : c'en est une
  sous-classe, la clause large l'avalait et le compteur serait resté à zéro.
- Un `OSError` qui n'est pas un refus (manette débranchée pendant le scan) reste
  silencieux.
- L'avertissement n'est réémis que si le compte change : la boucle tourne toutes
  les 3 s et une ligne par passe ferait 1200 à l'heure.
- Le **silence** est testé au même titre que le bruit : une boîte sans manette
  ne produit aucun enregistrement, à aucun niveau.

`AUDIT/repro/test_f004_evdev_muet.py` : **5 passed** (2 failed au départ).

### Partie 4 — F-008 / F-009 : commentaires qui mentent (`e7daed6`)

- `process_manager.py` : openbox → « the machine's own X11 desktop session ».
  La ligne `env.pop("WAYLAND_DISPLAY")` reste, c'est la RAISON qui était fausse.
- `defaults.tsx` : corrigé **après mesure** — les 8 sous-pages rendent
  `<Overlay>` comme racine, donc `docs/themes/README.md` avait raison.
- Statut en tête de `docs/themes/README.md` corrigé.

### Deux correctifs non demandés, trouvés en branchant une manette Xbox

Le propriétaire a branché une Xbox (`045e:02fd`) et signalé « le stick ne
fonctionne qu'à gauche ». Deux défauts réels en sont sortis, tous deux dans du
code que la Partie 2 rendait actif :

- **`8197848`** — `block_disagrees()` comptait un slot non assigné comme un
  désaccord. Rosalie's Mupen GUI (pack `gopher64`, appId
  `com.github.Rosalie241.RMG`) écrit `DeviceName = "None"` avec
  `PluggedIn = False` pour les slots que personne n'a assignés : 3 de ses 4
  profils sur une boîte à une manette. Inoffensif tant que seul `capture()`
  posait la question ; avec `restore()` qui la pose aussi, le mapping N64
  sauvegardé aurait été refusé à chaque connexion.

- **`6feb05d`** — la garde était **aveugle aux GUID des liaisons composées
  d'azahar**. azahar échappe `:` en `$0`, donc un GUID de stick s'écrit
  `guid$00300…` — et le `0` de l'échappement est un chiffre hexadécimal, ce qui
  fait échouer le `(?<![0-9a-fA-F])` de `_ANY_GUID_RE`. Toutes les liaisons de
  stick étaient invisibles, **dans `capture()` comme dans `restore()`** : c'est
  par là qu'un snapshot mixte a pu être écrit. Mesuré : sur le seed azahar
  d'avant nettoyage, la garde voit maintenant 23 GUID au lieu de 15.
  `check-catalog.py` importe désormais le motif et la normalisation depuis
  `snapshots.py` au lieu d'en garder une copie.

## Pas terminé

**Tout le périmètre demandé est fait.** Ce qui suit est hors périmètre et
volontairement laissé :

- **F-001, F-003, F-005, F-007** restent rouges dans `AUDIT/repro/` — ils ne
  faisaient pas partie de cette phase. `python3 -m pytest AUDIT/repro -q` donne
  **10 failed, 70 passed, 6 skipped** (16 failed au départ).

- **Un repro rouge est de mon fait** :
  `test_f008_…::test_defaults_tsx_les_decrit_bien_comme_des_fragments`. C'est le
  garde-fou qui établit que la moitié fautive de la contradiction existe — il
  **exige la présence du texte que la Partie 4 retire**, donc il ne peut pas
  survivre à sa propre correction. Les deux CONSTATS du fichier sont verts. Je
  n'ai pas modifié `AUDIT/repro/` : le prompt disait de ne pas le réécrire.

## Décisions prises seul

Aucun prompt ne demandait ces choix.

1. **Verbe et chemin de la route d'effacement** : `DELETE
   /controllers/scan-mapping`, même chemin que le POST, plutôt qu'un
   `/controllers/mapping` séparé. Scan et oubli sont deux moitiés d'un même
   geste ; une route par pack aurait exposé une notion que l'UI n'a pas.
2. **`forget_mapping()` agit sur la manette connectée, pas sur un `emu_id`.**
   Le geste du propriétaire est « oublie ce que tu crois savoir de CETTE
   manette », même forme que le scan qui l'a créé. Signature :
   `forget_mapping() -> dict` avec `{ok, controller, forgotten: [pack_id]}`.
3. **Bouton « Forget mapping » ajouté à `PowerModal.tsx`.** Le prompt demandait
   une route ; une route qu'aucune UI n'appelle reste inatteignable depuis un
   canapé, ce qui était le reproche du constat. Double pression comme les
   actions d'extinction, mais **jamais `powerPending`** : l'OS reste debout.
4. **Le refus de `restore()` n'est pas un `Skip`.** Voir Partie 3 ci-dessus.
5. **Tests ajoutés dans `backend/tests/`** (14), dont un fichier nouveau
   `test_controllers_router.py`. `AUDIT/repro/` étant hors de `testpaths`, s'y
   fier laissait les correctifs sans garde en CI.
6. **Nettoyage azahar par SUPPRESSION des clés**, pas en vidant leur valeur.
   Pari : azahar régénère ses défauts quand la clé est absente, ce que signale
   son propre `\default=true`. Non vérifié en lançant azahar — voir Incertitudes.
7. **`AUDIT/` est commité sur la branche** (11 fichiers). Le prompt disait de
   récupérer les repros depuis `chore/audit` ; ils sont les tests d'acceptation.
   Ça fait 11 fichiers dans le diff vs `main` qui ne sont pas des correctifs.
   **À retirer si tu préfères une branche qui ne porte que le code.**
8. **`[gba.input-profile.PS4 Controller]` retirée du seed mgba** alors que
   l'audit ne signalait que le GUID. Elle nomme un périphérique par son nom,
   donc elle contredit l'objectif « un seed qui ne nomme aucun périphérique ».

## Incertitudes

- **Le stick d'azahar après remappage.** Le snapshot `azahar/045e_02fd.snap` de
  la boîte a `circle_pad.left` sur le GUID Xbox et `right`/`up`/`down` sur celui
  de la DS4, ce qui correspond exactement au symptôme rapporté. J'ai corrigé la
  **détection** ; je n'ai pas vérifié qu'un remappage complet suivi d'un
  « Scan mapping » donne un stick fonctionnel dans les quatre directions.
  *Pour le vérifier :* effacer ce `.snap`, ne garder que la Xbox branchée,
  remapper le circle pad **en entier** dans azahar, puis « Scan mapping ».

- **Le comportement d'azahar avec un seed nettoyé.** Mesuré en simulation :
  avec un snapshot présent, `generate()` rend
  `azahar: restored saved mapping (045e:02fd)` et relie 15 boutons ; sans
  snapshot, il rend `None` et la config reste vierge. **Je n'ai pas lancé
  azahar** pour confirmer qu'il régénère bien ses défauts clavier quand les clés
  sont absentes (décision 6).

- **Régression assumée, mesurée** : sur une boîte **vraiment neuve** sans aucun
  snapshot, un propriétaire de DS4 perd 15 liaisons qui marchaient (azahar) et 1
  (mgba). Pour toute autre manette elles étaient déjà mortes — elles portaient
  le GUID `054c:09cc`. Le changement réel est « configuré pour la manette de
  quelqu'un d'autre » → « pas configuré ».

- **Les skips de F-002 passent de 2 à 6.** Effet de la Partie 1, pas une
  régression : les seeds azahar et mgba ne portant plus de GUID, leur
  `extract()` ne remonte plus celui que le test injecte et le test se déclare
  incapable de porter la démonstration au lieu de passer à vide. Sur `main`,
  `restore[azahar]` et `restore[mgba]` étaient verts par le chemin « déjà
  appliqué », sans rien prouver. **cemu**, le pack que le constat nomme,
  continue de la porter.

- **La branche `DeviceName` de `block_disagrees()` est inerte dans la suite**
  tant qu'on ne stubbe pas la base SDL : `conftest.py` redirige `GAMECORE_ROOT`
  vers une racine factice, `gamecontrollerdb.txt` n'y est pas, `db_name_for()`
  rend `None`, et la branche refuse alors de juger. Mes deux tests la stubbent.
  **Tout test futur de cette branche qui ne le fait pas passera à vide.**

- **Je n'ai pas pu observer l'état mixte en direct.** La Xbox s'est déconnectée
  avant, et la DS4 en se reconnectant a réappliqué son propre snapshot — la
  config vivante d'azahar est actuellement 100 % DS4. Le contenu du snapshot et
  le symptôme correspondent, mais le lien n'est pas observé de bout en bout.

## Remarqué et laissé en place

- **Les indices de boutons bruts du seed mgba** (`keyA=0`, `keyB=1`,
  `hat0Up=6`…) dans `[gba.input.SDLB]` viennent de la récolte DS4. mgba les
  applique à n'importe quelle manette SDL et les retirer laisserait une boîte
  neuve sans aucun binding. L'audit ne les signalait pas. **À trancher par le
  propriétaire.**

- **Un `409 Conflict` de `POST /api/games/launch` ne dit pas pourquoi.**
  Observé en vrai : un jeu resté ouvert (fenêtre non visible) a produit six 409
  d'affilée, vécus comme « je ne peux plus lancer de jeux ». Même famille que
  F-004 — un état légitime rendu indistinguable d'une panne. Hors périmètre,
  non touché, mériterait une entrée au registre.

- **`gopher64` est l'id du pack, mais l'émulateur est Rosalie's Mupen GUI**
  (`emulatorName`, `appId com.github.Rosalie241.RMG`). Le répertoire de
  snapshots hérite de l'id. Source de confusion réelle, non renommée : un
  renommage d'id touche le catalogue, les snapshots existants et les configs.

## Prochaine action concrète

Effacer `~/.local/share/gamecore/controller-snapshots/azahar/045e_02fd.snap`
(capture mixte : `circle_pad.left` sur le GUID Xbox, les trois autres directions
sur celui de la DS4), puis, Xbox seule branchée, remapper le circle pad **en
entier** dans azahar et refaire « Scan mapping » — et vérifier que les quatre
directions répondent. C'est la seule chose que le code ne peut pas prouver seul.
