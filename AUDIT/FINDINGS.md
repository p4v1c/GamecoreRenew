# Registre d'audit — GameCore

Passe de constats **uniquement**. Aucun correctif n'est écrit ici : les seuls
fichiers ajoutés sont ce registre et les reproductions sous `AUDIT/repro/`.

Un constat n'entre au registre qu'avec une **preuve exécutable** : un test rouge
sur `main`, ou une commande dont la sortie prouve le défaut. « Ce code semble
fragile » n'est pas un constat et n'est pas écrit.

## Comment rejouer les preuves

`AUDIT/repro/` est **hors de `testpaths`** (`pytest.ini` : `backend/tests
catalog`), donc la ligne de base reste verte. Les repros se lancent à part :

```
python3 -m pytest AUDIT/repro -q          # doit être ROUGE sur main
```

Chaque fichier de repro contient au moins un **test garde-fou vert** qui prouve
que la prémisse du constat est vraie, à côté du test rouge qui porte le constat.
Sans ça, un repro pourrait passer au vert en ne vérifiant rien — le défaut que
la passe 5 traque.

## Ligne de base (identique avant / après cet audit)

```
ruff check .                          → All checks passed!
shellcheck -S warning …               → (aucune sortie)
python3 scripts/check-catalog.py      → 17 pack(s) OK
python3 scripts/gen-catalog.py --check→ 17 pack(s), .dist up to date
pytest backend/tests catalog -q       → 584 passed, 5 skipped, 4 deselected
frontend npm run test:run             → 51 passed
frontend npm run build                → built
```

---

# Passe 1 — Écriture sans inverse

### F-001 — le multitap s'allume tout seul et ne s'éteint jamais
Famille   : écriture sans inverse
Sévérité  : moyenne
Preuve    : `AUDIT/repro/test_f001_multitap_sans_inverse.py` (rouge sur main,
            2 failed / 2 passed — les deux verts sont les garde-fous qui
            prouvent que l'écriture a bien lieu)
Fichier   : `backend/services/configgen/helpers/tier0.py:52`
            (`if multitap and player_index >= multitap["fromPlayer"]`)
Effet     : `tier0.apply()` écrit la clé multitap déclarée par le pack dès qu'un
            joueur ≥ `fromPlayer` arrive — PCSX2 `[Pad] MultitapPort1 = true`,
            DuckStation `[ControllerPorts] MultitapMode = Port1Only`. C'est
            correct et nécessaire : sans ça le slot 3 est refusé au niveau SIO2.

            Mais `release_profile()` ne traverse que les générateurs exposant
            `release()`, et **1 générateur sur 10** en a un (dolphin). Aucun des
            deux packs à multitap n'en expose. La clé reste donc à `true` pour
            toujours : après une session à quatre, toutes les sessions solo
            suivantes tournent avec un accessoire virtuel branché sur le port 1.

            Le seed livre `MultitapPort1 = false` / `MultitapMode = Disabled`,
            donc l'état d'arrivée est bien « éteint » et la boîte n'y revient
            jamais seule.
Sortie     :
```
$ grep -n "MultitapPort1" catalog/pcsx2/seed/PCSX2.ini \
                          catalog/pcsx2/tests/fixtures/slot-3-only/PCSX2.ini
catalog/pcsx2/seed/PCSX2.ini:519:MultitapPort1 = false
catalog/pcsx2/tests/fixtures/slot-3-only/PCSX2.ini:519:MultitapPort1 = true
```
Correctif suggéré : donner un `release()` aux packs `sdl-index-clone` qui éteint
            la clé multitap quand plus aucun slot ≥ `fromPlayer` n'est occupé.
            Cela suppose que `release_profile()` connaisse le roster restant, ce
            qu'il ne reçoit pas aujourd'hui (il ne prend qu'un `player_index`) —
            **la signature est probablement le vrai sujet, pas le multitap.**
Confiance : haute (l'écriture et l'absence d'inverse sont toutes deux
            exécutées ; le coût réel pour le joueur — un multitap virtuel sur un
            jeu solo — n'a pas pu être mesuré sans matériel, voir Incertitudes)

### F-002 — `block_disagrees` garde `capture()` mais pas `restore()`
Famille   : écriture sans inverse
Sévérité  : haute
Preuve    : `AUDIT/repro/test_f002_restore_sans_garde.py` (rouge sur main,
            1 failed / 6 passed / 2 skipped — le garde-fou prouve que la
            protection existe bien côté capture, les skips disent quels packs ne
            peuvent pas porter la démonstration et pourquoi)
Fichier   : `backend/services/configgen/snapshots.py:115` (`restore`)
            vs `backend/services/configgen/snapshots.py:100` (`capture`)
Effet     : `capture()` refuse d'enregistrer un bloc dont le GUID nomme une
            autre manette. `restore()` n'appelle jamais `block_disagrees()` et
            applique donc n'importe quel snapshot déjà présent sur le disque.

            Ce n'est pas hypothétique : le docstring de `snapshots.py:59` dit que
            **la boîte porte déjà un tel snapshot** — `cemu/045e_02fd.snap`
            (Xbox) contenant la config de la DualShock 4. La garde a été ajoutée
            après coup et ne protège que les captures futures.

            Et il n'existe aucun geste pour effacer un snapshot :
            `backend/routers/controllers.py` n'expose que
            `POST /controllers/scan-mapping`, il n'y a pas de `DELETE`. Donc le
            snapshot empoisonné est réappliqué à **chaque connexion**, écrasant
            le mapping que le propriétaire refait à la main dans l'émulateur.
            Le docstring le dit lui-même : *« the moment the owner maps the Xbox
            by hand, the next connection overwrites their work »* — et décrit
            cela comme un risque futur, alors que rien n'empêche sa réalisation.
Correctif suggéré : appeler `block_disagrees()` dans `restore()` et refuser (en
            loggant) plutôt qu'appliquer ; et exposer une route pour oublier un
            snapshot, sans quoi un désaccord détecté reste sans issue.
Confiance : haute

---

# Passe 2 — Échecs silencieux

Critère appliqué : **si ça rate, l'utilisateur le voit-il ?** Les trois constats
ci-dessous répondent non. Les nombreux `except …: pass` de nettoyage (fermeture
de descripteur, `dev.close()`, `proc.kill()` sur un process déjà mort) ne sont
pas des constats et ne sont pas écrits : rien n'est perdu quand ils avalent.

### F-003 — `release_profile()` refuse un slot hors 1-4 sans un mot
Famille   : échecs silencieux
Sévérité  : basse
Preuve    : `AUDIT/repro/test_f003_release_profile_muet.py` (rouge sur main,
            5 failed / 1 passed — le vert est le garde-fou qui prouve que la
            moitié bavarde de la paire l'est bien)
Fichier   : `backend/services/configgen/__init__.py:240` (`return []`)
            vs `backend/services/configgen/__init__.py:170` (`log.warning`)
Effet     : `apply_profile()` traite le même plafond huit lignes plus haut et le
            logge, avec le commentaire qui dit ce que ça a coûté d'apprendre :
            *« a 5th pad used to get a player number, a TV toast, and no config
            at all, without a word anywhere »*. `release_profile()` fait
            `return []` et se tait, sur **toute** la plage refusée (0, négatif,
            ≥ 5). La leçon a été retenue d'un seul côté de la paire.

            Sévérité basse, et il faut être précis sur pourquoi : le schéma
            plafonne `controllers.maxPlayers` à `"maximum": 4`, donc un pack ne
            PEUT PAS déclarer 8 aujourd'hui — l'hypothèse « le jour où maxPlayers
            passe à 8 » supposerait aussi de lever cette borne. C'est une
            asymétrie de journalisation entre deux fonctions jumelles, pas une
            panne en cours. Elle est inscrite parce qu'elle est gratuite à
            corriger et qu'elle mine la confiance dans le journal : un lecteur
            qui voit `apply_profile` se plaindre en déduit que son jumeau le
            ferait aussi.
Correctif suggéré : le même `log.warning` que son jumeau.
Confiance : haute

### F-004 — evdev inaccessible : plus aucune manette, et rien dans le journal
Famille   : échecs silencieux
Sévérité  : haute
Preuve    : `AUDIT/repro/test_f004_evdev_muet.py` (rouge sur main, 2 failed /
            3 passed — les verts prouvent que le faux evdev détecte bien des
            manettes quand tout va bien, que le scénario de refus les perd
            vraiment toutes, et que le `glob` remplacé par les tests est bien
            celui que la fonction utilise)
Fichier   : `backend/services/gamepad_monitor.py:157` (`except ImportError:
            return {}`) et `backend/services/gamepad_monitor.py:199`
            (`except (PermissionError, OSError): pass`)
Effet     : les deux portes de sortie rendent `{}`, ce qui est **exactement** ce
            que rend une boîte sans manette branchée. Rien en aval ne peut
            rattraper la différence : `was != live` est faux, donc `_reconcile`
            n'est même pas appelé, et aucune ligne n'est écrite à aucun niveau.

            Ce n'est pas un cas théorique : le docstring de la fonction nomme
            lui-même le mode de panne — *« may be inaccessible without input
            group »* — et c'est précisément celui qui ne produit aucun signal.
            Depuis le canapé, le symptôme est « la manette ne fait rien », dans
            le menu comme dans les jeux, avec un journal vide pour diagnostiquer.
Correctif suggéré : compter les refus dans la boucle et logger une fois par
            passe (`n périphériques sur m refusés — utilisateur hors du groupe
            input ?`) ; logger l'`ImportError` au moins une fois au démarrage.
Confiance : haute

### F-005 — un nom de périphérique deviné est écrit dans la config sans un mot
Famille   : échecs silencieux (« écriture faite à partir d'une valeur devinée »)
Sévérité  : moyenne
Preuve    : `AUDIT/repro/test_f005_nom_devine.py` (rouge sur main, 1 failed /
            3 passed — un des verts établit le coût : la valeur devinée atterrit
            bien dans `Default.yml` de RPCS3)
Fichier   : `backend/services/configgen/controllers.py:167` (`resolve_name`)
            vs `backend/services/configgen/controllers.py:151` (le seul
            `log.warning` de la chaîne)
Effet     : `resolve_name()` est une chaîne de repli à quatre étages. Seul le
            premier signale son échec, et **seulement s'il lève**. Or l'échec
            courant n'est pas une exception mais une absence : SDL3 répond bien
            et ne connaît pas ce pad — le cas que le commentaire de
            `SDL3_FALLBACK_NAMES` nomme lui-même (*« the pad went back to sleep
            between the evdev scan and this call »*). La chaîne descend alors
            jusqu'au nom evdev brut en silence.

            Le docstring de `resolve_name` dit ce que ça produit : *« WRONG for
            SDL3 on some pads […] showed up live in RPCS3.log as "SDL: Adding
            empty device" and a dead pad in game »*. Le test vert montre le
            trajet complet : `Device: Generic X-Box pad 1` écrit dans
            `input_configs/global/Default.yml`. La seule trace du problème est
            donc dans le journal de l'émulateur, pas dans le nôtre.
Correctif suggéré : logger l'étage auquel la chaîne s'est arrêtée dès qu'il
            n'est pas le premier — c'est une information de diagnostic, pas une
            erreur, mais elle est la seule qui relie « manette morte dans RPCS3 »
            à sa cause.
Confiance : haute

---

# Passe 3 — Contrats du catalogue

Les deux sens ont été parcourus : ce que le pack déclare est-il honoré, et ce
que le générateur fait est-il déclaré. Vérifié sans constat : `maxPlayers`,
`order`, `padType`, `multitap` et `strategy` sont tous lus et honorés
(`profilable_packs`, `apply_profile`, `tier0.apply`), et
`backend/tests/test_generator_contract.py` couvre déjà la surface que chaque
stratégie oblige à exposer.

### F-006 — deux seeds livrés épinglent une DualShock 4 précise
Famille   : contrats du catalogue
Sévérité  : haute
Preuve    : `AUDIT/repro/test_f006_seed_nomme_une_manette.py` (rouge sur main,
            2 failed / 39 passed — les verts couvrent les 39 autres fichiers de
            seed, plus deux garde-fous : le décodeur reconnaît bien un GUID de
            DS4, et il ne se déclenche pas sur du hex quelconque)
Fichier   : `catalog/mgba/seed/config.ini:5` et `:32`
            `catalog/azahar/seed/qt-config.ini:42` et suivantes
Effet     : les deux seeds portent le GUID SDL d'une DualShock 4 réelle
            (`054c:09cc`), et azahar y ajoute les **indices de boutons bruts**
            (`button:0`, `button:12`…). C'est exactement ce que le docstring de
            `snapshots.py` décrit comme non synthétisable — livré en dur pour un
            seul modèle de manette.

            Le catalogue a un champ pour ce défaut précis, et le schéma dit
            pourquoi : *« A seed that names a device pins the grid to one
            controller model; CI fails on a hit »*. Mais `seedMustNotContain`
            est **déclaratif** : `check-catalog.py` ne teste que les motifs que
            le pack déclare. Cinq packs sur dix en déclarent ; ces deux-là n'en
            déclarent aucun, donc la garde ne les regarde même pas. D'où
            `check-catalog: 17 pack(s) OK` sur un catalogue qui porte le défaut.

            Le générateur dolphin raconte l'incident jumeau et sa correction :
            *« That seed used to pin `Device = SDL/0..3/PS4 Controller`, which
            is dead input on any box without a DualShock 4 […] the seed now
            names no device and check-catalog.py fails the build if one comes
            back »*. La leçon a été appliquée à dolphin, rpcs3, cemu, melonds et
            ryujinx, et pas à ces deux-là.

            Aggravant : azahar et mgba sont en `snapshot-restore`. Leur
            `generate()` ne fait que restaurer un snapshot s'il en existe un.
            Sur une boîte neuve avec une manette qui n'est pas une DS4, il n'y a
            aucun chemin de réparation automatique — contrairement à dolphin ou
            rpcs3 qui reconstruisent le slot. La seule issue est que le
            propriétaire mappe à la main puis presse « Scan mapping ».

            Les deux GUID diffèrent d'un octet (bus `03` pour azahar, `05` pour
            mgba) : ce sont deux récoltes de la même manette à deux moments et
            sur deux transports, ce qui confirme qu'il s'agit bien de résidus de
            la machine de récolte.
Sortie     :
```
$ grep -n "05008fe54c05\|03008fe54c05" catalog/mgba/seed/config.ini \
                                       catalog/azahar/seed/qt-config.ini | head -3
catalog/mgba/seed/config.ini:5:device0=05008fe54c050000cc09000000006800
catalog/mgba/seed/config.ini:32:[gba.input-profile.05008fe54c050000cc09000000006800]
catalog/azahar/seed/qt-config.ini:42:profiles\1\button_a="button:0,engine:sdl,guid:03008fe54c050000cc09000000006800,port:0"
```
Correctif suggéré : deux temps. Nettoyer les deux seeds ; puis rendre la garde
            NON déclarative — `check-catalog.py` peut refuser tout GUID de 32 hex
            décodant vers un vendor:product connu, dans n'importe quel seed, sans
            que le pack ait à le demander. `seedMustNotContain` reste utile pour
            les formes que le décodage ne voit pas (le `<display_name>` de Cemu).
Confiance : haute pour le constat (le GUID est là, la garde ne le regarde pas).
            Moyenne pour l'ampleur du symptôme : voir Incertitudes — je n'ai pas
            pu brancher une manette non-DS4 pour mesurer ce que fait azahar avec
            ce fichier.

### F-007 — le schéma autorise une liste de cibles, le répartiteur n'en passe qu'une
Famille   : contrats du catalogue
Sévérité  : basse (latente)
Preuve    : `AUDIT/repro/test_f007_target_liste_tronquee.py` (rouge sur main,
            1 failed / 2 passed — les verts vérifient que le schéma autorise
            bien la liste et qu'un pack la déclare, faute de quoi le constat
            n'aurait plus de porteur)
Fichier   : `backend/services/configgen/__init__.py:99` (`target = target[0]`)
            vs `catalog/_schema/pack.schema.json` (`"type": ["string", "array"]`)
Effet     : `generator_opts()` réduit la liste à son premier élément et jette le
            reste sans journal. Les autres cibles déclarées ne se retrouvent dans
            aucune clé de `opts`.

            Sans conséquence aujourd'hui, et pour une raison qui tient du
            hasard : le seul pack déclarant une liste (dolphin) est aussi le seul
            des dix dont le générateur ne lit **jamais** `opts["target"]` — il
            code ses deux noms de fichiers en dur. Les deux défauts se masquent
            mutuellement. Neuf générateurs sur dix lisent `opts["target"]`.

            Le piège est donc pour le pack suivant : deux cibles déclarées, la
            convention majoritaire suivie, la moitié des fichiers écrite, aucun
            signal, et un `pack.json` qui affirme le contraire.
Sortie     :
```
$ python3 -c '…'   # quel générateur lit sa cible déclarée
dolphin      target=['GCPadNew.ini', 'WiimoteNew.ini']   lit_opts_target=False
azahar       target='qt-config.ini'                      lit_opts_target=True
…             (les 9 autres : True)
```
Correctif suggéré : soit `opts["targets"]` (au pluriel) toujours présent en
            liste, soit le schéma restreint à une chaîne. Le choix dépend de si
            un pack multi-fichiers est attendu — c'est une question de
            conception, pas un correctif mécanique.
Confiance : haute sur le mécanisme, basse sur l'urgence — rien ne casse
            aujourd'hui.

---

# Passe 4 — Commentaires et docs qui mentent

Les deux constats annoncés au départ sont confirmés et inscrits. Le critère
appliqué : une affirmation **au présent sur ce que le code fait**, contredite
par le code. Les mentions historiques (« It used to be a bare openbox
session… ») sont légitimes et hors sujet.

Examinés et **écartés** — c'est le filtre qui compte autant que les constats :

- `docs/architecture/11-install-script-seams.md:55` décrit une arborescence
  `install/lib/` + `install/phases/` qui n'existe pas. Mais la section s'intitule
  « The seams, if a VM is available » et introduit le bloc par « So the split
  is: » — c'est une **proposition**, pas une description. Pas un mensonge.
- le même document date les phases d'`arch.sh` (« SDDM auto-login | 964–1051 »)
  avec ~19 lignes de dérive (réel : 983). L'en-tête de colonne dit
  « Lines (approx.) » et le texte désigne les appels `msg "<name>"` comme les
  vraies lignes de coupe. Hedgé, et le lecteur atterrit à côté de la bonne
  ancre. Pas un constat.
- `backend/tests/test_configgen_snapshots.py:5` et deux `test_generator.py` de
  packs citent `backend/tests/test_controller_profiles.py`, qui n'existe plus —
  mais au passé (« Moved out of … in phase 4 »). Légitime.

### F-008 — `process_manager.py` situe GameCore dans une session openbox
Famille   : commentaires et docs qui mentent
Sévérité  : basse
Preuve    : `AUDIT/repro/test_f008_commentaires_qui_mentent.py` (rouge sur main
            — 2 failed / 12 passed pour les deux constats du fichier ; les
            garde-fous lisent `PKGS` dans `install/arch.sh` et établissent
            qu'`plasma-desktop` y est et qu'`openbox` n'y est plus)
Fichier   : `backend/services/process_manager.py:205`
Effet     : le commentaire dit « GameCore runs in an X11 openbox session ».
            openbox n'est plus installé — absent de `PKGS`, l'installateur pose
            `plasma-desktop` et `plasma-x11-session` — et le CHANGELOG l'annonce
            sous *« The kiosk is hosted on the machine's own X11 desktop
            session. openbox is no longer installed and is no longer the
            auto-login target. »*

            La ligne de code que ce commentaire justifie
            (`env.pop("WAYLAND_DISPLAY", None)`) reste **correcte** : la pile
            entière est X11-only, `arch.sh` le redit à la ligne 421. C'est la
            RAISON qui est fausse — et c'est elle que le prochain lecteur
            utilisera pour décider si la ligne peut partir. Un lecteur qui sait
            qu'openbox a disparu conclura que le commentaire est mort, donc que
            la ligne l'est aussi ; elle ne l'est pas.
Correctif suggéré : remplacer « openbox » par « the machine's own X11 desktop
            session », qui est à la fois vrai et la vraie raison.
Confiance : haute

### F-009 — deux textes se contredisent sur ce qu'est une sous-page de réglages
Famille   : commentaires et docs qui mentent
Sévérité  : moyenne
Preuve    : `AUDIT/repro/test_f008_commentaires_qui_mentent.py`, second groupe
            (rouge sur main ; huit tests verts mesurent que **8/8** sous-pages
            rendent leur propre `<Overlay>`)
Fichier   : `frontend/src/components/defaults.tsx:63`
            vs `docs/themes/README.md:368`
Effet     : `defaults.tsx` dit *« They are fragments, not modals: dropped into a
            theme's own box they lose their width, padding and scroll — which is
            exactly how the Wi-Fi page came out broken »*, et expose
            `SettingsOverlay` pour les envelopper. `docs/themes/README.md` dit
            l'inverse : *« The pages already carry their own overlay — render
            them bare; SettingsOverlay is only there if you write a page of your
            own »*.

            La mesure tranche : les 8 sous-pages rendent chacune leur propre
            `<Overlay>`. C'est donc la doc qui est juste et le commentaire qui
            ment.

            Et il ne ment pas de façon inerte. Un auteur de thème qui suit
            `defaults.tsx` emboîte une `Overlay` dans une `Overlay` et obtient
            précisément la largeur, les marges et le défilement cassés que le
            commentaire dit vouloir éviter. **Les deux textes racontent le même
            incident Wi-Fi et en tirent des conclusions opposées** — ce qui
            suggère que le correctif a été appliqué (les pages ont gagné leur
            Overlay) sans que le commentaire qui décrivait l'ancien état soit
            retiré.
Correctif suggéré : réécrire le commentaire de `defaults.tsx` pour dire ce que
            `SettingsOverlay` sert vraiment (écrire une page NEUVE), et non ce
            qu'il fallait faire avant que les pages portent leur propre overlay.
Confiance : haute

---

# Passe 5 — Tests vacants

Méthode : réintroduire un défaut précis, lancer la ligne de base entière,
restaurer. Une mutation qui laisse la suite **verte** prouve qu'aucun test ne
garde ce comportement.

C'est la seule forme de preuve possible ici. Le code de production est correct
sur `main`, donc un « test rouge sur main » ne peut pas exister : c'est
l'ABSENCE de garde qui est le constat, et une mutation survivante est la façon
exécutable de la montrer.

    python3 AUDIT/repro/mutations.py

Dix mutations, dont **six témoins** dont on sait qu'elles doivent être
attrapées — sans elles, un harnais cassé rendrait « tout survit » et le constat
serait faux. Les six sont bien attrapées :

```
  multitap-jamais-ecrit:           attrapée   (11 failed)
  gcpad-toujours-sain:             attrapée   (32 failed)
  block-disagrees-aveugle:         attrapée   (1 failed)
  pack-file-sans-garde-de-chemin:  attrapée   (1 failed)
  event-sort-lexicographique:      attrapée   (1 failed)
  ordre-de-profilage-alphabetique: attrapée   (1 failed)

  rpcs3-toujours-lie:              SURVIT     (584 passed)
  maxplayers-ignore:               SURVIT     (584 passed)
  atomic-write-non-atomique:       SURVIT     (584 passed)
  seed-deploy-reecrit-tout:        SURVIT     (584 passed)
```

### F-010 — le chemin de réparation de RPCS3 n'est joué par aucun scénario
Famille   : tests vacants
Sévérité  : haute
Preuve    : `python3 AUDIT/repro/mutations.py rpcs3-toujours-lie` →
            **584 passed** ; et le comptage des fixtures de messages ci-dessous
Fichier   : `catalog/rpcs3/generator.py:37` (`_is_bound`) et `:59` (le donneur)
Effet     : remplacer `_is_bound()` par `return True` désactive exactement la
            réparation que le module existe pour faire — un slot en
            `Handler: "Null"` avec des bindings vides n'est plus reconstruit à
            partir d'un slot sain, il est « retargeté » tel quel, donc laissé
            mort. La suite entière reste verte.

            La cause est mesurable : le seed livre les quatre joueurs en
            `Handler: SDL` avec leurs bindings, et la caractérisation part
            toujours du seed. L'état malade que le code répare n'est donc
            **jamais construit** par aucun des 14 scénarios :
Sortie     :
```
$ grep -oh "rpcs3: Player [0-9] [a-z]*" catalog/_characterisation/*.messages \
    | sort | uniq -c
     11 rpcs3: Player 1 retargeted
      8 rpcs3: Player 2 retargeted
      4 rpcs3: Player 3 retargeted
      3 rpcs3: Player 4 retargeted
```
            Zéro « rebuilt ». Les occurrences de « rebuilt » dans ces fixtures
            appartiennent toutes à dolphin.

            Ce que ça garde n'est pas anodin : le docstring du module dit que
            c'est cette branche qui a manqué pendant que *« Players 2-4 on the
            reference box were in that state for a week »*. La correction d'une
            panne d'une semaine n'a pas de test.
Correctif suggéré : un scénario de caractérisation partant d'un `Default.yml`
            où Player 2 est en `Handler: "Null"` bindings vides et Player 1 sain
            — c'est-à-dire l'état réel de la boîte avant la correction. Le seed
            ne peut pas le porter (il doit rester neutre) : c'est une fixture
            d'entrée, pas un seed.
Confiance : haute

### F-011 — le garde `maxPlayers` du répartiteur n'est vérifié par rien
Famille   : tests vacants
Sévérité  : basse
Preuve    : `python3 AUDIT/repro/mutations.py maxplayers-ignore` → **584 passed**
Fichier   : `backend/services/configgen/__init__.py:191`
Effet     : supprimer `if player_index > ctl.get("maxPlayers", 4): continue`
            ne casse aucun test. `test_single_player_emulators_ignore_slots_above_one`
            annonce pourtant *« Invariant 5. azahar, mgba, Cemu and melonDS are
            single-player here: only slot 1 is ever touched, whatever player
            index arrives »*.

            Il reste vert parce que **les cinq générateurs mono-joueur se
            gardent eux-mêmes** (`if i != 1: return None` chez azahar, cemu,
            mgba, gopher64 ; `if i != 1 or not toml.is_file()` chez melonds).
            Le test vérifie donc la garde des GÉNÉRATEURS, pas celle du
            répartiteur qu'il nomme.

            Soyons précis sur la gravité : l'invariant est bien tenu
            aujourd'hui, par la couche du dessous. Ce n'est pas une panne, c'est
            une défense en profondeur dont un des deux étages n'est pas testé —
            et c'est l'étage que le commentaire présente comme le correctif de
            classe (*« melonDS lacked this guard once, so plugging in a second
            pad rewrote its one and only player config for the wrong pad »*).
            Un pack futur qui déclare `maxPlayers: 1` sans se garder lui-même
            n'a que cet étage, et rien ne dit s'il fonctionne.
Correctif suggéré : un test qui appelle `apply_profile` avec un faux pack
            `maxPlayers: 1` dont le générateur ne se garde pas, et vérifie qu'il
            n'est pas appelé pour le slot 2.
Confiance : haute

### F-012 — les deux primitives d'écriture ne sont testées nulle part
Famille   : tests vacants
Sévérité  : moyenne
Preuve    : `python3 AUDIT/repro/mutations.py atomic-write-non-atomique
            seed-deploy-reecrit-tout` → **584 passed** dans les deux cas ; et
            `grep -rl "atomic_write" backend/tests/ catalog/*/tests/` ne
            remonte **aucun** fichier.
Fichier   : `backend/services/configgen/helpers/base.py:40` (`atomic_write`)
            `backend/services/configgen/seed.py:48` (`deploy`)
Effet     : deux fonctions dont le docstring décrit une panne vécue et précise,
            et qu'aucun test ne nomme.

            `atomic_write` remplacée par un `write_text()` nu — précisément ce
            que le docstring dit avoir corrigé (*« write_text() truncates first
            […] a Config.json caught between the two is invalid JSON, and
            Ryujinx starts over from defaults »*) — laisse la suite verte.
            La caractérisation compare le CONTENU final, qui est identique ;
            elle ne peut pas voir par quel chemin il est arrivé.

            `deploy()` avec son court-circuit « c'est déjà notre propre copie »
            supprimé laisse la suite verte aussi. Le module entier n'a aucun
            test : c'est lui qui décide quand créer un `.bak-preinstall`, et le
            docstring explique que se tromper fait *« record GameCore's config
            as if it were the user's, and uninstall would then "restore" our
            file instead of deleting it »* — soit une désinstallation qui
            réinstalle.

            Nuance honnête sur `deploy()` : la mutation testée ne casse pas la
            décision de sauvegarde elle-même (le `filecmp.cmp` en aval la
            protège encore), elle supprime l'idempotence — chaque re-run
            réécrit tous les fichiers et les annonce comme modifiés. C'est
            moins grave que ce que le docstring redoute, et rien ne le voit
            quand même.
Correctif suggéré : pour `atomic_write`, un test qui observe qu'aucun lecteur
            ne voit le fichier tronqué (p. ex. en interceptant `os.replace` et
            en vérifiant que la cible est intacte jusque-là). Pour `deploy()`,
            les quatre lignes du tableau de son docstring sont déjà quatre cas
            de test écrits d'avance.
Confiance : haute

---

# Passe 6 — Chemins et frontières

**Le harnais de test n'écrit pas hors de ses répertoires temporaires.** C'est la
question la plus importante de cette famille — le seul chemin par lequel un
`pytest` pourrait toucher les vraies configs de la boîte — et la réponse est
non, mesurée deux fois :

```
$ HOME=<sentinelle vide> XDG_CACHE_HOME=… XDG_CONFIG_HOME=… \
      pytest backend/tests catalog -q -m "not network"
584 passed, 5 skipped, 4 deselected
$ find <sentinelle> -mindepth 1 | wc -l
0

$ # liste des fichiers du checkout avant / après une exécution complète
$ diff before.txt after.txt && echo AUCUNE
AUCUNE
```

`backend/tests/conftest.py` y est pour beaucoup : il pointe `GAMECORE_PATH` sur
un `tempfile.mkdtemp()` **avant** tout import, et neutralise aussi les
identifiants ScreenScraper pour que la suite ne se comporte pas différemment sur
la machine d'un développeur. C'est fait correctement et documenté.

Examinés et **écartés** :

- `backend/config.py:15` — `GAMECORE_ROOT` retombe sur l'emplacement du CODE
  quand `GAMECORE_PATH` est absent. C'est un chemin construit relativement au
  code, mais délibérément : en production le checkout **est** la racine de
  données (`/opt/GameCore`). Cohérent, pas un défaut.
- `resolve_path()` rend les chemins absolus tels quels — un `romsPath` sur un
  autre disque est un cas d'usage, pas une évasion.
- `snap_path()` normalise la casse du vendor:product sans test, mais les deux
  appelants formatent déjà en minuscules (`f"{info.vendor:04x}"`). Défense en
  profondeur non testée, sans chemin d'atteinte : pas inscrit.

### F-013 — la règle qui choisit l'arbre de config n'est vérifiée par rien
Famille   : chemins et frontières
Sévérité  : moyenne
Preuve    : `python3 AUDIT/repro/mutations.py config-dir-natif-toujours-prioritaire`
            → **584 passed** (la mutation inverse la règle et rien ne bronche)
Fichier   : `backend/services/configgen/__init__.py:87`
Effet     : `resolve_config_dir()` décide **où toutes les configs de manette
            sont écrites**. Sa règle est subtile et son docstring dit pourquoi :

                « The tree that EXISTS wins, native first: a native tree kept as
                  a post-migration backup must not shadow a live flatpak, and a
                  curated config written next to an uninstalled flatpak is never
                  read by anything. »

            Remplacer la condition par le seul `native_dir.is_dir()` — c'est-à-
            dire faire gagner le natif même quand le flatpak est vivant, la
            moitié de la règle que le docstring dit avoir apprise — laisse la
            suite entière verte.

            Le symptôme, si la règle se casse, est celui qui envoie chercher
            ailleurs : `apply_profile` réussit, écrit ses fichiers, retourne ses
            messages, la boîte affiche son toast « manette configurée » — et
            l'émulateur lit un autre répertoire. Une manette morte, sans aucune
            erreur nulle part. C'est la classe de panne que ce dépôt appelle
            « gopher64 » et que `check-catalog.py` empêche côté catalogue ; côté
            résolution, rien.

            Deux packs déclarent un `nativeDest` (mgba, melonds) : la règle n'est
            donc pas théorique, elle s'applique à des packs livrés.
Correctif suggéré : trois tests, un par ligne du docstring — flatpak seul,
            natif seul, les deux présents. Ils tiennent en quelques `mkdir` dans
            `tmp_path` et n'ont besoin d'aucun émulateur.
Confiance : haute sur l'absence de garde (mutation reproductible). Le défaut
            lui-même n'est PAS présent sur `main` : la règle est correctement
            écrite aujourd'hui, c'est sa protection qui manque.

---

# Classement final — les trois à traiter en premier

Critère : ce que ça coûte à quelqu'un assis sur son canapé, aujourd'hui, sur une
boîte livrée — pas l'élégance du correctif.

### 1. F-006 — les deux seeds qui épinglent une DualShock 4
**Pourquoi d'abord :** c'est le seul constat qui frappe **toute boîte neuve dont
le propriétaire n'a pas de DualShock 4**, sans action de sa part et sans
réparation automatique possible. azahar et mgba étant en `snapshot-restore`,
aucun code ne reconstruit le slot : la manette est simplement morte dans ces
deux émulateurs jusqu'à un mappage manuel. Et le correctif est le moins risqué
de la liste — nettoyer deux fichiers de seed, plus une garde non déclarative
dans `check-catalog.py` qui empêche la récidive pour tous les packs à la fois.
Diagnostic quasi impossible depuis le canapé, correctif quasi sans risque : le
meilleur rapport de la liste.

### 2. F-002 — `restore()` sans la garde que `capture()` a
**Pourquoi ensuite :** c'est le seul constat qui **détruit du travail
utilisateur**. Le propriétaire remappe sa manette à la main dans l'émulateur ; à
la connexion suivante, un snapshot empoisonné écrase son mapping. Et il n'a
aucun moyen de s'en sortir : aucune route n'efface un snapshot. Le docstring de
`snapshots.py` atteste qu'un tel snapshot **existe déjà** sur la boîte de
référence. Le correctif est petit — appeler `block_disagrees()` dans `restore()`
— mais il laisse la question de l'issue de secours, d'où la deuxième place et
non la première.

### 3. F-004 — evdev inaccessible, aucune trace
**Pourquoi en troisième :** la panne est plus rare que les deux précédentes,
mais quand elle arrive elle est **totale** (plus une seule manette, menu
compris) et **muette**. Le journal est le seul outil de diagnostic à distance
sur une boîte de salon, et il ne dit rien. Le correctif est trivial — compter
les refus, logger une fois — et il transforme « ma boîte ne répond plus » en
une ligne qui nomme la cause. Coût quasi nul, valeur de diagnostic élevée.

**Pourquoi pas F-010 malgré sa sévérité haute :** l'absence de test sur la
réparation RPCS3 est le constat le plus inquiétant pour l'AVENIR du code, mais
il ne casse rien aujourd'hui — la branche est correcte, elle n'est pas gardée.
Il vient juste après ces trois-là, et avant tous les autres.
