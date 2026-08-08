# Les quatre fixtures modifiées par P1 — justification une par une

P1 (`fix/autoconfig-stale-slots`, mergée en `49fc777`, publiée en `v1.0.144`) a
modifié **quatre** fichiers de caractérisation déjà existants. Le point 4 de la
porte exige que `git diff main..HEAD -- 'catalog/*/tests/fixtures/*'` soit vide ;
il ne l'était pas, et le merge est parti sur accord verbal.

Ce document répond à une seule question, fixture par fixture : **changement de
comportement légitime, ou test rendu vert ?**

La liste exacte des fichiers modifiés (les 25 autres du diff sont des créations,
pour les trois scénarios que P1 ajoute — `four-then-one-ds4`,
`rpcs3-player-2-null`, `unknown-pad`) :

```
$ git diff --name-status 3021921..49fc777 -- 'catalog/*/tests/fixtures/*' \
      'catalog/_characterisation/*' | grep -v '^A'
M	catalog/_characterisation/unplug-player-2.messages
M	catalog/_characterisation/unplug-then-replug.messages
M	catalog/rpcs3/tests/fixtures/unplug-player-2/Default.yml
M	catalog/ryujinx/tests/fixtures/unplug-player-2/Config.json
```

## Le test d'inversion, et pourquoi c'est lui qui compte

Raisonner sur le diff ne prouve rien — c'est le raccourci qui a produit les trois
tests vacants déjà trouvés dans ce dépôt. Pour chaque fixture : remettre la
version `3021921`, relancer le scénario, citer le rouge.

Une fixture qui **repasse au vert** avec son ancien contenu n'avait aucune raison
de changer. C'est le constat grave, et il n'est arrivé sur aucune des quatre.

Restauration par `command cp -f` vers un répertoire tiers avant chaque essai :
`git checkout -- <fichier>` détruit le travail non commité.

---

## Fiche 1 — `catalog/rpcs3/tests/fixtures/unplug-player-2/Default.yml`

**Scénario** `unplug-player-2` : DS4 en P1, pad Xbox en P2, puis départ du P2 avec
`occupied=(1,)`. **Pack** rpcs3, stratégie `rewrite-player-block`.

**Diff — une ligne.**

```diff
@@ -93,7 +93,7 @@
 Player 2 Input:
   Handler: SDL
-  Device: Xbox One Controller 1
+  Device: ""
```

**Commit et mécanisme.** `ab6f8ea` — *« libérer les slots que plus aucune manette
ne tient »*. Avant lui, `release_profile()` ne traversait que les générateurs
exposant `release()`, et il y en avait **un sur dix** (Dolphin). Le commit ajoute
`release()` à `catalog/rpcs3/generator.py`, et `configgen.release_profile()`
(`backend/services/configgen/__init__.py:240`) le traverse maintenant via
`profilable_packs()`. Le générateur RPCS3 remet `Device: ""` sur le slot libéré ;
`Handler` et les bindings restent, pour que le slot suivant soit un simple
retarget et reste utilisable comme donneur.

**Test d'inversion — exécuté.**

```
$ git show 3021921:catalog/rpcs3/tests/fixtures/unplug-player-2/Default.yml \
      > catalog/rpcs3/tests/fixtures/unplug-player-2/Default.yml
$ pytest "…::test_scenario_matches_its_fixtures[unplug-player-2]" -q
E   AssertionError: rpcs3/Default.yml diverged:
E     --- fixture/rpcs3/Default.yml
E     +++ produced
E     @@ -93,7 +93,7 @@
E      Player 2 Input:
E        Handler: SDL
E     -  Device: Xbox One Controller 1
E     +  Device: ""
1 failed
```

**Sens du changement.** Un périphérique nommé en moins dans un slot inoccupé :
exactement l'intention déclarée de P1. Et le point qui tranche — l'état d'arrivée
est **l'octet exact que le seed livre** pour un slot inutilisé :

```
$ grep -A2 "^Player [234] Input:" catalog/rpcs3/seed/…/Default.yml
Player 2 Input:
  Handler: SDL
  Device: ""
```

Un slot libéré redevient indiscernable d'un slot jamais servi. Ce n'est pas une
valeur inventée pour faire passer un test, c'est l'inverse à l'octet de ce que
`generate()` avait écrit.

**Verdict : légitime.** La ligne retirée nommait un pad Xbox absent dans un slot
que personne ne tenait.

---

## Fiche 2 — `catalog/ryujinx/tests/fixtures/unplug-player-2/Config.json`

**Scénario** `unplug-player-2`. **Pack** ryujinx, stratégie `guid-rebind`.

**Diff — deux lignes.**

```diff
@@ -248,8 +248,8 @@
       "backend": "GamepadSDL2",
-      "id": "0-00000005-045e-0000-fd02-000003090000",
-      "name": "Xbox One Controller (0)",
+      "id": "",
+      "name": "",
       "controller_type": "ProController",
       "player_index": "Player2"
```

**Commit et mécanisme — et l'histoire compte ici.** Deux commits touchent cette
fixture, et le second corrige le premier :

| commit | `release()` ryujinx | fixture `unplug-player-2` |
|---|---|---|
| `3021921` (base) | *aucune* | 4 entrées, Player2 nommé |
| `ab6f8ea` | `ic.remove(e)` — entrée **retirée** | **3 entrées**, Player2 disparu |
| `045d7fc` | `e["id"], e["name"] = "", ""` | 4 entrées, Player2 **vidé** |

Le message de `ab6f8ea` décrit donc un état que la branche a quitté avant d'être
mergée (« l'entrée est RETIRÉE, pas vidée »). Ce n'est pas ce qui a été livré, et
le docstring de `release()` dans l'arbre actuel dit pourquoi le retrait a été
abandonné :

> `generate()` construit un slot manquant en CLONANT la première entrée
> GamepadSDL2 qu'il trouve, donc une fois la dernière partie il n'y a plus de
> modèle : `model is None`, `Skip("no gamepad slot to clone from")`, et Ryujinx
> ne peut plus jamais être configuré par aucun nombre de reconnexions.
> Mesuré, sur la boîte de ce développeur et pas en théorie : une exécution a
> laissé `input_config` liste vide.

**Test d'inversion — exécuté.**

```
$ git show 3021921:catalog/ryujinx/tests/fixtures/unplug-player-2/Config.json > …
$ pytest "…::test_scenario_matches_its_fixtures[unplug-player-2]" -q
E   AssertionError: ryujinx/Config.json diverged:
E     -      "id": "0-00000005-045e-0000-fd02-000003090000",
E     -      "name": "Xbox One Controller (0)",
E     +      "id": "",
E     +      "name": "",
1 failed
```

**Sens du changement.** Un id vidé dans un slot inoccupé, dans le sens voulu. Et
comme pour RPCS3, l'état d'arrivée **est celui du seed** — `catalog/ryujinx/seed/Config.json`
livre quatre entrées `GamepadSDL2` avec `id: ""` et `name: ""` :

```
GamepadSDL2 Player1 '' ''      GamepadSDL2 Player3 '' ''
GamepadSDL2 Player2 '' ''      GamepadSDL2 Player4 '' ''
```

**Verdict : légitime.** Réserve nommée : le corps de commit de `ab6f8ea` décrit
un comportement qui n'est pas celui de la release. Le code livré et son docstring
sont cohérents ; c'est le message de commit intermédiaire qui est périmé. Un
relecteur qui partirait du `git log` sans lire `release()` serait induit en
erreur — d'où ce tableau.

---

## Fiche 3 — `catalog/_characterisation/unplug-player-2.messages`

**Diff — la troisième ligne du transcript.**

```diff
-release(2): dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound
+release(2): ryujinx: Player 2 unbound; dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound; rpcs3: Player 2 unbound
```

**Commit et mécanisme.** `ab6f8ea` puis `045d7fc`, les mêmes que les fiches 1 et
2 : ce sont les comptes rendus des deux `release()` nouvellement traversés. Aucun
message existant n'est modifié ni supprimé — deux sont **ajoutés**.

**Test d'inversion — exécuté.**

```
$ pytest "…::test_scenario_messages_match[unplug-player-2]" -q
E   AssertionError
E   - lease(2): ryujinx: Player 2 unbound; dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound; rpcs3: Player 2 unbound
E   + lease(2): dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound
1 failed
```

**Sens du changement — et l'ordre, qui méritait d'être vérifié.** L'ordre
`ryujinx, dolphin, dolphin, rpcs3` n'est pas arbitraire : `release_profile()`
itère `profilable_packs()`, qui trie sur `controllers.order` **déclaré dans les
pack.json** — ryujinx 0, dolphin 5, rpcs3 6. C'est l'ordre du toast à l'écran, et
il appartient au pack.

À noter, sans que ce soit un défaut : la ligne `apply(...)` du harnais est écrite
`"; ".join(sorted(result))` — alphabétique — tandis que la ligne `release(...)`
n'est **pas** triée et conserve l'ordre déclaré. Les deux sont déterministes, mais
seule la seconde est sensible à un changement de `controllers.order`. Repéré,
laissé en place : trier la ligne de release effacerait une propriété observable.

**Verdict : légitime.** Deux gestes de plus sont accomplis, donc deux comptes
rendus de plus sont émis. Un `release()` qui agit sans le dire serait le défaut.

---

## Fiche 4 — `catalog/_characterisation/unplug-then-replug.messages`

**Diff — deux lignes sur quatre.**

```diff
-release(2): dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound
-apply(ds4, P2, dup1): dolphin: GCPad2 rebuilt from GCPad1, Wiimote2 set (SDL/1/PS4 Controller)
+release(2): ryujinx: Player 2 unbound; dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound; rpcs3: Player 2 unbound
+apply(ds4, P2, dup1): dolphin: GCPad2 rebuilt from GCPad1, Wiimote2 set (SDL/1/PS4 Controller); rpcs3: Player 2 retargeted (PS4 Controller 2); ryujinx: Player 2 retargeted (dup 1, 00000003-054c-0000-cc09-000000006800)
```

La seconde ligne est la conséquence mécanique de la première : le slot ayant
réellement été libéré, le rebranchement a de nouveau quelque chose à écrire chez
RPCS3 et Ryujinx. Avant P1 il n'écrivait rien — non par idempotence vertueuse,
mais parce que le slot n'avait jamais été relâché.

**Test d'inversion — exécuté.**

```
$ pytest "…::test_scenario_messages_match[unplug-then-replug]" -q
E   AssertionError
E   - lease(2): ryujinx: Player 2 unbound; …; rpcs3: Player 2 unbound
E   - apply(ds4, P2, dup1): …; rpcs3: Player 2 retargeted (PS4 Controller 2); ryujinx: Player 2 retargeted (dup 1, …)
E   + lease(2): dolphin: Wiimote2 released (inactive); dolphin: GCPad2 unbound
E   + apply(ds4, P2, dup1): dolphin: GCPad2 rebuilt from GCPad1, Wiimote2 set (SDL/1/PS4 Controller)
1 failed
```

**La piste annoncée, vérifiée.** Le rapport de P1 affirme que `unplug-then-replug`
« redevient identique à `main` » après le correctif Ryujinx. **C'est exact, et il
faut être précis sur ce que ça couvre :**

```
$ git diff --stat 3021921..49fc777 -- 'catalog/*/tests/fixtures/unplug-then-replug/*'
(vide)
```

Les **six fixtures de configuration** du scénario — dolphin ×2, duckstation,
melonds, pcsx2, rpcs3, ryujinx — sont inchangées à l'octet. L'état final des
émulateurs après débranchement puis rebranchement est bien identique à `3021921` :
un aller-retour, pas une dérive. C'est ce qui rend l'affaire simple.

Ce qui a changé est le **transcript**, et lui seul : il enregistre les états
intermédiaires que l'état final ne montre pas. Dire « la fixture redevient
identique » sans distinguer les deux serait faux ; dire « quelque chose a dérivé »
le serait aussi.

**Verdict : légitime.** Aller-retour vérifié sur les six fixtures de config ;
seules les transitions intermédiaires apparaissent, et elles apparaissent parce
qu'elles ont réellement lieu.

---

## Conclusion

| fixture | inversion | verdict |
|---|---|---|
| `rpcs3/…/unplug-player-2/Default.yml` | rouge | **légitime** |
| `ryujinx/…/unplug-player-2/Config.json` | rouge | **légitime** |
| `_characterisation/unplug-player-2.messages` | rouge | **légitime** |
| `_characterisation/unplug-then-replug.messages` | rouge | **légitime** |

**Les quatre sont légitimes.** Aucune n'a été régénérée pour accommoder du code
neuf : chacune, remise dans sa version `3021921`, fait échouer son scénario en
montrant que le générateur produit désormais autre chose — et cet autre chose est,
dans les deux cas de configuration, **l'octet exact que le seed livre pour un slot
inutilisé**.

Rien à corriger. Les fixtures se gardent telles quelles ; les remettre à leur
version d'avant serait la régression.

**Ce dont je ne suis pas certain, et que ce document ne prouve pas :**

- Que `Device: ""` / `id: ""` soit ce que RPCS3 et Ryujinx *interprètent*
  réellement comme « slot vide » sur la vraie boîte. L'argument est solide — c'est
  ce que les seeds livrent, et le docstring de `release()` cite
  `_gamepadsIds.IndexOf("")` → `-1` — mais il repose sur le seed et sur la lecture
  du code des émulateurs, pas sur une observation en jeu. Les vérifier
  demanderait de brancher deux manettes, et il n'y en a qu'une sur cette machine.
- Que les trois scénarios ajoutés par P1 couvrent ce qu'ils prétendent. Ils sont
  hors du périmètre de cette session, qui portait sur les fixtures **modifiées**.
