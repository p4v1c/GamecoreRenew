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
