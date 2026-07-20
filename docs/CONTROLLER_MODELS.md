# Faire reconnaître n'importe quelle manette, sur n'importe quel émulateur

Deux mécanismes distincts, complémentaires. Le principe directeur : **aucun
slot joueur n'est jamais câblé à une marque précise.** La première manette
qui se connecte devient Joueur 1 (quel que soit son type), la suivante
Joueur 2, etc. — comme sur une vraie console.

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

## 2. Dolphin, RPCS3, Cemu, citron, azahar, mgba — profilage live par slot

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
  le format de GUID SDL). Retargeter un slot ne demande donc QUE de
  substituer ces octets, jamais les index déjà validés par l'utilisateur.

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

- `azahar` (3DS) et `mgba` (GBA) : matériel single-player, seul le Joueur 1
  est jamais concerné.
- `ppsspp` et `melonDS` : aucune config existante trouvée sur ce boîtier
  (jamais lancés) → ignorés proprement ; lance-les une fois, configure les
  boutons manuellement, et le profilage les couvrira ensuite.
- Manettes non-Sony (Xbox, 8BitDo, génériques) : la substitution GUID
  suppose des index identiques à la manette de référence (Joueur 1 déjà
  configuré), ce qui n'est garanti qu'au sein d'une même famille de pilote
  (comme DS4/DualSense). Une famille différente nécessite toujours une
  reconfiguration manuelle une fois dans citron/azahar/mgba/Cemu.

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
