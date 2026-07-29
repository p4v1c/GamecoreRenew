# Faire reconnaître n'importe quelle manette, sur n'importe quel émulateur

Deux mécanismes distincts, complémentaires. Le principe directeur : **aucun
slot joueur n'est jamais câblé à une marque précise.** La première manette
qui se connecte devient Joueur 1 (quel que soit son type), la suivante
Joueur 2, etc. — comme sur une vraie console.

## 1. GameCore lui-même (menu TV) et les émulateurs "SDL-natif"

`backend/data/gamecontrollerdb.txt` (le community database
[SDL_GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB)) est
exporté aux émulateurs via `SDL_GAMECONTROLLERCONFIG_FILE`
(`process_manager.py`) — c'est LA variable que SDL (2.0.10+ et SDL3) lit
réellement ; une première version exportait `SDL_GAMECONTROLLERDB`, qui
n'existe pas, et la base était silencieusement ignorée.
SDL le fusionne à son propre init : tout émulateur qui parle le "rôle"
SDL_GameController plutôt que des index bruts fonctionne alors avec
**n'importe quelle manette listée dans la base**, sans aucune config
manuelle. C'est le cas de **PCSX2, DuckStation et gopher64** — vérifié en
lisant leurs bindings live : `SDL-0/FaceEast`, `SDL-0/A`, etc. — des noms de
rôle, jamais un index de bouton. Rien à faire, pour toujours, quelle que
soit la manette (si elle est dans la base).

## 2. Dolphin, RPCS3, Cemu, Ryujinx, azahar, mgba — profilage live par slot

Trouvé en lisant leurs configs réelles sur le boîtier :

- **Dolphin et RPCS3** utilisent aussi des rôles SDL sémantiques
  (`Button S/E/W/N`, `West/South/East/North`...) — mais ils sélectionnent
  QUEL périphérique physique alimente ce rôle par un **nom** littéral
  (`Device = SDL/0/PS4 Controller`, `Device: PS4 Controller 1`). Deux
  pièges découverts en live (log RPCS3 : `SDL: Adding empty device` =
  manette morte en jeu) :
  1. Les deux embarquent **SDL3**, dont les noms diffèrent de la base
     communautaire SDL2 : une DualSense s'appelle « DualSense Wireless
     Controller », pas « PS5 Controller ». Le nom est donc résolu en
     interrogeant la **libSDL3 du système** avec les manettes réellement
     branchées (`controller_profiles.resolve_name`), la base ne servant
     que de dernier recours.
  2. Le numéro n'est PAS le slot joueur : RPCS3 suffixe un compteur
     1-based **par nom** (`sdl_pad_handler.cpp`), Dolphin un compteur
     0-based **par nom** (`SDL/<k>/<nom>`, ciface DeviceContainer). Une
     DualSense seule est « DualSense Wireless Controller 1 » /
     `SDL/0/...` même en Joueur 2.
- **Ryujinx** utilise un **GUID** de périphérique précis
  (`button:1,guid:0500...cc09...`). Fait vérifié en clair sur ce boîtier :
  DualShock 4 et DualSense partagent le **même pilote noyau** et rapportent
  des **index identiques** — seul le GUID diffère (octets vendor/product à
  une position fixe, quel que soit le format de GUID SDL). Retargeter un slot
  ne demande donc QUE de substituer ces octets, jamais les index déjà validés
  par l'utilisateur. Mais l'index d'accompagnement compte **par GUID**, pas
  par joueur : le préfixe `<dup>-<GUID>` de l'`id` dans `Config.json` vaut 0
  pour une manette seule de son modèle, quel que soit son slot (un dup
  inexistant lie un périphérique fantôme → entrée morte). Les slots Ryujinx
  sont des objets de la liste `input_config`, clés par `player_index`
  (`Player1`..).

- **azahar, mgba, Cemu** : **restauration d'un instantané**, PAS de
  substitution de GUID. Leurs liaisons ne peuvent pas être fabriquées à partir
  d'un simple VID:PID. Le modèle réel est celui-ci :

  1. l'utilisateur mappe la manette une fois, dans l'émulateur, via
     « Scan mapping » ;
  2. `snapshot_save()` enregistre ce bloc de config, indexé par
     `vendor:product` ;
  3. `snapshot_restore()` le remet en place quand une manette du même modèle
     se reconnecte.

  Des versions « substitution de GUID » de `_mgba()` et `_cemu()` ont existé
  dans `controller_profiles.py` — elles n'ont jamais été appelées par
  `apply_profile()` et ont été supprimées. La docstring du module fait foi.

Le compteur commun aux schémas par nom et par GUID est `dup_index` : le nombre
de manettes du même vendor:product déjà connectées dans un slot inférieur.
`gamepad_monitor.py` le calcule depuis son roster et le passe à
`apply_profile()` ; 0 est toujours correct pour la première manette d'un
modèle donné.

### Le mécanisme live : `backend/services/controller_profiles.py`

C'est `gamepad_monitor.py` qui pilote tout, en continu, dans le backend déjà
en cours d'exécution — **ce n'est pas un script à relancer à la main**.
Chaque fois qu'une manette prend un NOUVEAU slot joueur (y compris les
manettes déjà branchées au démarrage du backend), le module :

1. lit son vendor:product USB (evdev),
2. résout son nom canonique SDL depuis `gamecontrollerdb.txt`,
3. écrit/retargete la config native de chaque émulateur pour CE slot,
   avec la bonne manette — en direct, sans redémarrer ni relancer quoi
   que ce soit.

Le slot lui-même est attribué par `controller_registry.py` (déjà en place
pour les batteries/labels TV) — première manette connectée = Joueur 1,
suivante = Joueur 2, etc., jusqu'à 4. Le TYPE de manette qui occupe un slot
peut donc changer d'une session à l'autre sans jamais rien casser.

- `azahar` (3DS), `mgba` (GBA), `Cemu` (Wii U) : matériel single-player ici,
  seul le Joueur 1 est jamais concerné — et par restauration d'instantané
  (voir plus haut), pas par substitution de GUID.
- `melonDS` (DS) : **profilé**, contrairement à ce que disait cette page.
  Un instantané sauvegardé gagne ; sinon `_melonds()` synthétise la config à
  partir de la manette connectée. Les boutons de façade sont constants d'une
  manette à l'autre — seule la croix directionnelle diffère (hat ou boutons),
  et c'est la seule chose adaptée (`_pad_has_hat`). Single-player, slot 1.
- `ppsspp` : aucune config existante trouvée sur ce boîtier (jamais lancé) →
  ignoré proprement ; lance-le une fois, configure les boutons manuellement,
  et le profilage le couvrira ensuite.
- Manettes non-Sony (Xbox, 8BitDo, génériques) : la substitution GUID
  (Ryujinx) suppose des index identiques à la manette de référence (Joueur 1
  déjà configuré), ce qui n'est garanti qu'au sein d'une même famille de
  pilote (comme DS4/DualSense). Une famille différente demande un
  « Scan mapping » une fois, qui devient l'instantané réutilisé ensuite.

⚠️ **Un émulateur déjà lancé au moment où sa config change ne relit pas le
fichier tout seul** — il faut quitter/relancer le jeu pour que le nouveau
mapping s'applique à cette session-là. Les lancements suivants sont
transparents.

## `install/apply-controller-model.sh` — outil de secours uniquement

```
install/apply-controller-model.sh                  # auto-détecte, jusqu'à 4
install/apply-controller-model.sh 054c:0ce6         # VID:PID forcé (Joueur 1)
install/apply-controller-model.sh 054c:0ce6 "PS5 Controller"
```

Appelle directement `controller_profiles.py` — utile uniquement pour
retargeter des manettes DÉJÀ branchées sans les débrancher/rebrancher (ex.
juste après avoir installé cette fonctionnalité). Le mécanisme normal, au
quotidien, est 100 % automatique via `gamepad_monitor.py`.

Complémentaire à `apply-multi-ds4.sh` (clone Joueur 1 vers 2-4 pour
plusieurs manettes du MÊME modèle, en une seule fois à l'installation).
