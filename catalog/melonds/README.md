# melonDS — bascule L3 intégrée au pack

L'installation de ce pack installe melonDS, puis le daemon Python et le service
utilisateur `melonds-layout-toggle.service`, depuis GameCore comme depuis
l'installateur général. Le service démarre après la configuration ; sans
session utilisateur ouverte, il démarre à la prochaine connexion.

L3 alterne deux écrans et écran supérieur seul en 16:9. Le daemon modifie les
réglages de disposition en mémoire, puis injecte F12 pour demander à melonDS
de recalculer l'affichage. La configuration initiale lie F12 à
`HK_SwapScreenEmphasis` et désactive la liaison joystick correspondante. La
restauration d'un ancien profil manette conserve cette désactivation lorsque
F12 est sélectionné. Le daemon répare aussi la liaison lorsque melonDS ferme.

Le pack déclare deux prérequis appliqués par le moteur d'installation :

- `hostAccess.uinput` : module, permissions du clavier virtuel et groupe input.
- `hostAccess.ptrace` : `kernel.yama.ptrace_scope=0`, nécessaire au daemon
  autonome pour accéder à un autre processus du même utilisateur. Ce réglage
  concerne l'hôte entier. L'ancien réglage et les fichiers remplacés sont
  conservés dans `/var/lib/gamecore/layout-access.json` pour la désinstallation.

Le daemon utilise uniquement Python 3 standard. Il est installé sous
`~/.local/share/gamecore/layout-toggle/melonds/`. Le nom du service est celui du
projet autonome afin d'éviter deux daemons simultanés.

Adaptations de la copie embarquée :

- service lancé avec `--recalc uinput --no-widescreen` : aucun code de triche
  installé ni activation automatique de `EnableCheats` ; le 16:9 est un étirement ;
- aucune écriture de bascule tant que le clavier virtuel n'est pas disponible ;
- sortie en échec si les entrées sont inaccessibles, pour permettre à systemd
  de réessayer ;
- choix de la configuration selon le lanceur GameCore, prise en charge du
  binaire natif optionnel `lib/melon` ; `MELONDS_CONFIG` peut imposer un chemin ;
- offsets et caches restent propres au daemon et à la version de melonDS.

Après déploiement de cette version de GameCore :
`sudo gamecore-emu install melonds` installe aussi le daemon sur une installation
existante. Cette commande réapplique la configuration initiale avec sauvegarde,
comme auparavant ; fermer l'émulateur d'abord. Une mise à jour du code seule ne
déploie pas les fichiers du daemon dans le home.

Diagnostic : `systemctl --user status melonds-layout-toggle` et
`journalctl --user -u melonds-layout-toggle -f`.

L'accès aux structures internes reste dépendant des versions de melonDS ; la
recherche dynamique ne garantit pas la compatibilité avec toutes les futures
versions. Le daemon teste le processus, pas le focus, et ne pilote pas les
cadres décoratifs GameCore. Désactiver le cadre pour profiter du plein écran.
Les tests automatisés ne remplacent pas une validation L3/Bluetooth sur le boîtier.
