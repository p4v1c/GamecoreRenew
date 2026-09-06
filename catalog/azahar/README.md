# Azahar — bascule L3 intégrée au pack

L'installation de ce pack installe Azahar, puis le daemon Python et le service
utilisateur `azahar-layout-toggle.service`. Cela fonctionne depuis l'écran
Systèmes de GameCore et depuis l'installateur général.

- L3 envoie F10 : deux écrans → écran supérieur seul → deux écrans.
- La configuration initiale sélectionne les layouts `0, 1` et l'étirement de
  l'écran supérieur. Le script de configuration complète les clés manquantes,
  garde une sauvegarde et n'écrit que lorsque l'émulateur est fermé.
- Le pack déclare `hostAccess.uinput` : le moteur commun prépare le module,
  les permissions udev et l'appartenance au groupe input si nécessaire.
- Python 3 standard uniquement ; aucun paquet pip propre au daemon.

Les fichiers sont installés sous
`~/.local/share/gamecore/layout-toggle/azahar/`. Le service garde le même nom
que le projet autonome pour remplacer cette unité lors d'une installation,
plutôt que lancer deux traducteurs L3 en parallèle.

Après déploiement de cette version de GameCore, un pack déjà installé peut
recevoir son daemon avec `sudo gamecore-emu install azahar`. L'installation
réapplique la configuration initiale selon le comportement habituel de cette
commande (sauvegarde `.bak-preinstall`). Fermer l'émulateur avant installation
ou reconfiguration. Une simple mise à jour du code ne déploie pas les services.

Diagnostic : `systemctl --user status azahar-layout-toggle` et
`journalctl --user -u azahar-layout-toggle -f`.

Le daemon teste la présence d'Azahar, pas le focus de sa fenêtre. Il reste
autonome : il ne commande pas les cadres décoratifs de GameCore. Désactiver le
cadre DS/3DS pour afficher le jeu entier en mode écran seul. La validation sur
le boîtier doit couvrir L3, le Bluetooth et le retour à l'interface.
