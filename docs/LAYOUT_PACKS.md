# Packs Azahar et melonDS avec daemon

Base : GamecoreRenew `de53579f6802a229dbea3d5edcf3ca4eaab3a300`.

Chaque pack contient son daemon, son unité systemd utilisateur et ses réglages
initiaux. L'installation depuis GameCore (`gamecore-emu install`) et depuis
l'installateur général déploie le daemon avec l'émulateur. Les fichiers vont
dans le home du joueur, même si l'installation s'exécute avec sudo. Les services
sont activés puis démarrés après les configurations ; sans session ouverte,
ils démarrent à la connexion suivante.

Les noms de services restent `azahar-layout-toggle.service` et
`melonds-layout-toggle.service`, comme dans les projets autonomes. Installer le
pack remplace l'unité de même nom plutôt que créer un deuxième daemon.

## Contenu

- `catalog/azahar/` : L3 → F10, layouts 0/1, écran supérieur étiré.
- `catalog/melonds/` : L3 → réglages mémoire → F12, raccourci joystick désactivé,
  sans installation de cheats ni activation automatique des cheats.
- `backend/services/installer/host_access.py` et schéma : prérequis déclaratifs
  `hostAccess.uinput` et `hostAccess.ptrace`, réservés aux packs de confiance.
- Installation commune : bon home, bons chemins des seeds, services des
  émulateurs collectés et démarrés, échecs remontés au parcours GameCore.
- Désinstallation : arrêt des unités installées par les packs, retrait des
  scripts embarqués et restauration des prérequis dont l'installation a gardé
  la trace, en préservant les fichiers système modifiés ensuite par l'opérateur.

L'archive livrée contient les deux répertoires de packs complets et les fichiers
communs modifiés. Il faut intégrer les deux : les manifests utilisent le nouveau
champ `hostAccess`. Copier seulement les deux dossiers dans une ancienne version
ne suffit pas. Le patch représente les mêmes changements par rapport au commit
de base. Utiliser soit l'archive, soit le patch, après vérification des éventuelles
modifications locales ; ne pas appliquer les deux successivement.

## Installation sur un GameCore existant

Après intégration de ces changements dans GameCore, fermer les émulateurs puis
installer les packs depuis l'interface ou avec :

```bash
sudo gamecore-emu install azahar melonds
```

Cette commande conserve le comportement existant de redéploiement des seeds
(sauvegarde `.bak-preinstall`) : elle n'est pas une migration ciblée des seules
clés de layout. Une simple mise à jour du dépôt ne copie pas les daemons dans
le home. `reconfigure` seul ne les installe pas.

## Validation effectuée

263 tests réussis, 5 tests ignorés par la suite existante. Couverture ciblée :
installation de packs, exécution simulée des deux parcours, services utilisateur,
permissions et restauration, catalogue et restriction OTA, configuration Azahar,
chemin melonDS natif/Flatpak, profils manette et fixtures existantes.

Catalogue : 17 packs valides. Ruff, syntaxe Bash des scripts modifiés et
`git diff --check` : OK.

Aucun daemon ni émulateur exécuté sur la machine ; commandes système simulées
dans les tests et fichiers écrits dans des répertoires temporaires. Aucun push,
aucune installation système effectuée lors de la préparation de ces livrables.

## À vérifier sur le boîtier

- Premier lancement, deux appuis L3, arrêt du jeu et nouvelle partie.
- Déconnexion/reconnexion Bluetooth et changement de manette.
- Retour à l'interface : les daemons détectent les processus, pas le focus.
- Cadres décoratifs : leur synchronisation n'est pas incluse. Désactiver le
  cadre DS/3DS pour afficher tout le jeu en mode écran seul.

melonDS utilise un accès mémoire interne et demande `ptrace_scope=0` sur l'hôte.
La recherche dynamique ne garantit pas toutes les futures versions de melonDS.
Voir aussi les README de chacun des deux packs.
