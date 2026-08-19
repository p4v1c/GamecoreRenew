# Factorisation — diagnostic et décisions (2026-08-19)

Branche `factorisation`, basée sur `installer`. Méthode : chaque « mort » prouvé
par recherche de ses appelants (scripts, docs, CI, tests, units, sudoers) ;
chaque factorisation justifiée par un cas **vécu** de double édition, pas par la
ressemblance ; chaque décision de NE PAS factoriser écrite ici, pour qu'une
passe future ne défasse pas ce qui est dupliqué exprès.

## Retiré (prouvé mort)

| quoi | preuve |
|---|---|
| `scripts/revert-migration.sh` | zéro appelant nulle part ; restaure des snapshots d'un mécanisme de migration antérieur qui n'existent plus ; la voie de retour vivante est l'épilogue de `migrate-userdata.py` |
| `emu/**/.gitkeep` (12 fichiers) + règles `.gitignore` | squelette de dossiers ROM maintenu à la main, déjà périmé (ni shadps4 ni xenia) ; l'installeur crée ces dossiers depuis le catalogue (`catalog-query rom-dirs`), `provision_userdata` crée `emu/`, `rom_scanner` traite l'absence comme vide |
| `verify_emulators.py` (racine) | déplacé en `scripts/verify-emulators.py` — même nommage que les onze autres outils ; 2 appelants mis à jour (CI `verify-catalog.yml`, `test_catalog_consumers`) |

## Factorisé (un fait, un endroit)

| fait | avant | après |
|---|---|---|
| politique bac à sable Flatpak | `providers.sandbox_flags()` **et** une copie dans `catalog-query.py` — les deux éditées dans le même commit le 18/08 (l'arrivée de la racine des données) | le script importe la vraie ; chaîne d'import stdlib vérifiée au python3 système, la contrainte d'`arch.sh` |
| écriture atomique (coupure de courant) | **six** exemplaires : `configgen/helpers/base.py`, `pergame._atomic_write`, inline dans `bezels` (×2), `bezel_capture`, `merge` (×2), `ota` (×2) | `backend/utils.atomic_write` (+ `atomic_write_json`, kwargs json passés tels quels — pas un octet de sortie ne change) ; `base.py` délègue en gardant son nom |
| frontière des ids système | même regex dans `routers/overlays.py` et `routers/pergame.py` | `backend/utils.SYSTEM_ID_RE` |
| plafond 10 Mo d'un bezel | `_MAX_BEZEL_BYTES` (bezels) + `_MAX_OVERLAY_BYTES` (router) | `bezels.MAX_BEZEL_BYTES`, le router s'y réfère |

## Examiné et laissé tel quel — les faux positifs

Ces duplications **sont voulues**. Les fusionner casserait un contrat.

- **`install/bin/gamecore-addon` autonome.** Copié dans `/usr/local/bin` par
  l'installeur : il ne peut rien importer du dépôt. Ses helpers python-heredoc
  qui ressemblent au backend restent à lui.
- **`_data_root_from_backend_unit` en double** (CLI + `update/linux.sh`).
  L'updater ne doit pas dépendre de la présence ni de la version du CLI.
- **rom-manager (dépôt addons) miroir de `fmt_size`/`clean_name`/
  `iter_rom_files`.** Contrat d'addon auto-contenu — dit dans son source ;
  un import du cœur lierait l'addon à l'arbre d'installation.
- **`arch.sh` monolithique.** Décision documentée
  (`11-install-script-seams.md`) ; on n'extrait pas de phases ici.
- **Encodeur PNG de `make-console-bezel.py` vs `_encode` de `test_bezels`.**
  Deux besoins (rendu d'un vrai bezel vs fixtures par filtre PNG) ; fusionner
  coulerait un couplage outil↔tests.
- **`_human` (migrate-userdata) vs `utils.fmt_size`.** Formats différents
  (binaire une-décimale vs affichage court) et le script de migration se lit
  seul, hors venv.
- **`_FreshStatic` (addons) vs `_NoCacheStatic` (cœur).** Deux dépôts, deux
  cycles de vie.
- **`data_path_problem` (GUI Python) vs `_conf_path` (arch.sh).** La même règle
  aux deux frontières, chacune dans sa langue ; un pont serait plus fragile que
  la duplication.
- **`mkstemp` du router d'upload d'overlays.** Pas le même problème que
  `atomic_write` : des écrivains **concurrents** — le nom unique est la
  protection, le commentaire du site raconte la panne qui l'a exigé.

## Vu, non traité (hors périmètre, à décider plus tard)

- `docs/rapports/*.md` : les comptes rendus de sessions (celui-ci compris) —
  utiles comme mémoire du projet ; à élaguer un jour si le dossier enfle.
- `backend/utils.fmt_size` étiquette KB/MB en divisant par 1024 — cosmétique,
  figé par l'affichage existant des addons ; à corriger avec leur UI, pas ici.

## Repasse du 2026-08-19 (revue d'une heure, chrono)

Relecture hunk par hunk du diff complet, plus exécution réelle de chaque
consommateur. Deux vraies trouvailles, deux resserrages :

1. **Régression attrapée : `scripts/verify-emulators.py` ne tournait plus.**
   Déplacé d'un cran, son `sys.path.insert(...parent)` visait `scripts/` au
   lieu de la racine — `ModuleNotFoundError: backend` en exécution réelle. Le
   test passait quand même : il charge le fichier avec un `sys.path` déjà
   garni. La CI du lundi aurait cassé en silence. Corrigé (`parents[1]`,
   comme les dix autres outils), prouvé en exécutant le job du lundi de bout
   en bout — vert, réseau compris. Leçon écrite ici : un test qui importe un
   script ne prouve pas que le script se lance.
2. **`atomic_write` écrit désormais `encoding="utf-8"` explicitement.**
   `merge.py` et `ota.py` le faisaient (JSON `ensure_ascii=False`) ; l'hériter
   de la locale remettait ce choix au hasard de l'environnement d'une unit.
   (PEP 540 couvre la locale `C` — vérifié —, pas une locale non-UTF-8.)
3. `base.py` : import relatif comme partout ailleurs ; `.gitignore` : un
   commentaire orphelin du vieux schéma `.gitkeep` retiré.
4. **Sémantique unifiée dite tout haut** : le helper fait `mkdir(parents=True)`
   là où le `base.py` d'origine ne le faisait pas. Vérifié site par site : les
   cinq appelants configgen écrivent à côté d'un fichier qu'ils viennent de
   lire ou après leur propre `mkdir` — l'unification est un no-op, pas un pari.

Contre-vérifications rejouées : octets de sortie identiques à la forme
historique (`merge_file` sur un label accentué, comparaison binaire) ; les
neuf sous-commandes de `catalog-query` et `gamecore-provider --dry-run` au
python3 système ; aucun lecteur ne globbe un `.gamecore-tmp` orphelin ;
aucune vieille constante (`_MAX_OVERLAY_BYTES`, `.json.tmp`) épinglée par un
test ; simulation `merge-tree` vers main : zéro conflit. Suite complète :
1707 verts, les 2 échecs = le flake `test_launch_reconcile` reproduit à
l'identique sur la branche de base dans le même environnement (expérience
témoin en worktree : mêmes totaux, mêmes deux échecs, et l'unique skip
divergent tracé à la ligne — `test_electron_cache.py:70`, « no frontend build
on disk », le worktree n'ayant pas de build : environnemental, pas de branche).
