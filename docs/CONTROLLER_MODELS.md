# Faire reconnaître n'importe quelle manette, sur n'importe quel émulateur

Deux mécanismes distincts, complémentaires.

## 1. GameCore lui-même (menu TV) et les émulateurs "SDL-natif"

`backend/data/gamecontrollerdb.txt` (le community database
[SDL_GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB)) est
exporté aux émulateurs via `SDL_GAMECONTROLLERDB` (`process_manager.py`).
SDL2 le fusionne à son propre init : tout émulateur qui parle le "rôle"
SDL_GameController plutôt que des index bruts fonctionne alors avec
**n'importe quelle manette listée dans la base**, sans aucune config
manuelle. C'est le cas de **PCSX2, DuckStation et gopher64** — vérifié en
lisant leurs bindings live : `SDL-0/FaceEast`, `SDL-0/A`, etc. — des noms de
rôle, jamais un index de bouton. Rien à faire, pour toujours, quelle que
soit la manette (si elle est dans la base).

## 2. Dolphin, RPCS3, Cemu, citron, azahar, mgba

Trouvé en lisant leurs configs réelles sur le boîtier :

- **Dolphin et RPCS3** utilisent aussi des rôles SDL sémantiques
  (`Button S/E/W/N`, `West/South/East/North`...) — mais ils sélectionnent
  QUEL périphérique physique alimente ce rôle par un **nom** littéral
  (`Device = SDL/0/PS4 Controller`, `Device: PS4 Controller 1`). Une
  manette différente (ex. DualSense) rapporte un nom SDL différent
  ("PS5 Controller") → l'émulateur ne la reconnaît plus, alors que les
  rôles de boutons eux-mêmes n'ont pas besoin de changer.
- **citron, azahar, mgba, Cemu** utilisent des **index bruts** liés à un
  GUID/UUID de périphérique précis (`button:1,guid:0500...cc09...`). Fait
  vérifié en clair sur ce boîtier : DualShock 4 et DualSense partagent le
  **même pilote noyau** et rapportent des **index identiques** — seul le
  GUID diffère (octets vendor/product à une position fixe, quel que soit
  le format de GUID SDL). Migrer Player 1 vers une nouvelle manette Sony ne
  demande donc QUE de substituer ces octets, jamais les index déjà validés
  par l'utilisateur.

## L'outil : `install/apply-controller-model.sh`

```
install/apply-controller-model.sh                  # auto-détecte la manette branchée
install/apply-controller-model.sh 054c:0ce6         # VID:PID explicite
install/apply-controller-model.sh 054c:0ce6 "PS5 Controller"
```

- Retargete Player 1 dans les 6 émulateurs "Tier 1/2" ci-dessus, en
  préservant exactement les assignations de boutons déjà en place.
- Le nom canonique ("PS5 Controller"...) est résolu depuis
  `gamecontrollerdb.txt` (n'importe quelle entrée plateforme porte le nom).
- Sauvegarde chaque fichier touché en `<fichier>.bak-ctrlmodel` (une seule
  fois, idempotent).
- `ppsspp` et `melonDS` : aucune config existante trouvée sur ce boîtier
  (jamais lancés) → ignorés proprement ; lance-les une fois, configure les
  boutons manuellement, puis l'outil pourra cloner vers d'autres manettes.
- Manettes non-Sony (Xbox, 8BitDo, génériques) : la substitution GUID
  suppose des index identiques à la manette de référence, ce qui n'est
  vrai qu'au sein d'une même famille de pilote (comme DS4/DualSense). Une
  manette d'une famille différente nécessite toujours une reconfiguration
  manuelle une fois dans citron/azahar/mgba/Cemu — l'outil ne devine pas
  de nouveaux rôles, il ne fait que recopier une configuration déjà
  fonctionnelle vers un GUID différent.

Complémentaire à `apply-multi-ds4.sh` (clone Player 1 vers 2-4 pour
plusieurs manettes du MÊME modèle) : celui-ci change plutôt QUEL modèle
Player 1 pointe.
