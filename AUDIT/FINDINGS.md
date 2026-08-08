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

            Sévérité basse aujourd'hui : aucun pack ne déclare `maxPlayers > 4`
            et `apply_profile` ne distribue pas de slot au-delà. C'est une
            asymétrie latente, pas une panne en cours — mais le jour où un pack
            monte à 8, la libération redevient inopérante sans aucun signal.
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
