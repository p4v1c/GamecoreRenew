# Sortie vers le bureau — état de l'enquête au 08/09/2026, 08h45

Écrit au moment d'éteindre la boîte. Tout ce qui suit est mesuré sur la
machine de référence, pas déduit.

## Où en est la boîte

- version déployée **v1.2.31**, auto-login **armé sur `gamecore`** ;
- SDDM n'a pas été redémarré depuis, donc la machine tournait encore sous
  Plasma au moment de l'extinction. **Le prochain démarrage ouvre la session
  console** avec le `gamecore-session` v1.2.31 — celui qui porte le
  basculement dans son teardown. C'est exactement l'état voulu pour tester.
- `/var/lib/gamecore/previous-session` = `plasma`, donc « Mode bureau » doit
  rendre Plasma et pas openbox.

## Ce qui est réglé et prouvé

### 1. Précédence SDDM (v1.2.29)
SDDM lit **tous** les fichiers de `/etc/sddm.conf.d` quelle que soit leur
extension, et le dernier `[Autologin]` par ordre de nom gagne. Notre propre
sauvegarde `zz-gamecore-autologin.conf.pre-session` triait après le fichier
qu'elle sauvegardait, et un résidu `zz-gamecore-openbox.conf` (Session=plasma,
10 juillet, pas produit par le dépôt) gagnait sur les deux. Les deux sont
maintenant dans `/var/lib/gamecore/retired-sddm/`, la sauvegarde sort du
dossier, et l'armement vérifie son propre effet avant d'annoncer un succès.

### 2. Écrire n'est pas appliquer (v1.2.30)
SDDM lit sa configuration **au démarrage du démon**. Terminer une session lui
fait seulement construire un nouvel affichage et, avec `Relogin=true`, rouvrir
ce qu'on lui a dit à *son* démarrage. Vérifié : `NRestarts=0`,
`ActiveEnterTimestamp=07:45:02` alors que trois cycles de session avaient eu
lieu depuis. D'où `gamecore-session-select desktop --restart-dm`.

### 3. `systemctl stop` ne stoppait pas l'interface (le correctif en cours)
**C'est la cause de l'erreur vue à l'écran.** Le journal :

    08:34:04  Stopping GameCore — Electron UI…      (fin de la mise à jour)
    08:34:04  gamecore-backend.service: Deactivated successfully
    08:35:35  State 'stop-sigterm' timed out. Killing.
    08:35:35  Killing process 25837 (node-MainThread) with signal SIGKILL

**1 min 45 s** d'interface vivante sur la télévision avec son backend déjà
arrêté dessous. `window-all-closed` ne sait pas distinguer un arrêt d'un
plantage : les fenêtres qui se ferment pendant une extinction qui n'est pas
passée par `before-quit` ressemblent à une panne, donc il en reconstruit une,
et l'application n'a plus aucune raison de partir. Corrigé par un gestionnaire
`SIGTERM`/`SIGINT`/`SIGHUP` explicite dans `main.js` + `TimeoutStopSec=10`.

Ça arrive **à chaque mise à jour**, pas seulement au bouton. C'est très
probablement ce que l'utilisateur a vu comme « erreur javascript ».

## Ce qui n'est PAS résolu

**Le bouton « Mode bureau » appelé depuis l'interface n'écrit pas le fichier.**

Les cinq appels sont dans le journal, tous acceptés par sudo, tous sortis en 0
en ~32 ms :

    02:08:57  gamecore-session-select desktop
    02:09:11  desktop
    02:23:22  desktop
    02:32:48  desktop
    08:09:38  desktop --restart-dm

Et `/etc/sddm.conf.d/zz-gamecore-autologin.conf` n'a pas bougé : mtime
`02:07:55`, `Session=gamecore`. Aucune erreur remontée, aucune ligne dans le
journal de l'unité. Le répertoire de sauvegarde `verif-avant/…` EST créé à
chaque fois, donc le script va au moins jusqu'à `backup_switch`, qui est
quatre lignes avant l'écriture.

La même commande écrit le fichier **à chaque fois** dans :
- un shell SSH ordinaire ;
- `systemd-run --user --wait` (donc même gestionnaire utilisateur, sans tty) ;
- un environnement réduit reproduisant celui du service (`env -i` + les six
  variables de l'unité) ;
- depuis `/opt/GameCore`, le `WorkingDirectory` de l'unité.

Six reproductions, six réussites. Durée d'une exécution réussie : 30–55 ms,
donc les 32 ms des échecs ne prouvent rien dans un sens ou dans l'autre.

**Seul point commun des cinq échecs** : ils tournent dans le cgroup de
`gamecore-ui.service`, que systemd démonte dès qu'Electron sort — la ligne
suivante. Je n'ai pas su prouver cette course depuis un SSH.

### Ce qui a été fait plutôt qu'une sixième théorie (v1.2.31)

Le travail privilégié est sorti de cet endroit. L'interface dépose
`$XDG_RUNTIME_DIR/gamecore/leave-to-desktop` puis quitte ; le teardown de
`gamecore-session` — dans le processus de la session, hors du cgroup démonté,
après l'arrêt des unités — fait le basculement et le redémarrage du
gestionnaire d'affichage, et recopie la sortie ligne par ligne dans le journal.

**C'est ce qu'il reste à valider au prochain démarrage.**

### Et surtout : plus rien n'est invisible

`gamecore-session-select` et `gamecore-session` journalisent sous leur propre
tag. Le `echo` du script de session partait dans le log de session SDDM, qui
fait **zéro octet** sur cette boîte — d'où `journalctl -t gamecore-session`
qui répondait « No entries » pour une session démarrée quatre fois.

Au prochain appui sur le bouton :

    journalctl -t gamecore-session -t gamecore-session-select --since "-10 min"

## Une erreur de diagnostic à ne pas refaire

J'ai annoncé que la majuscule de `XDG_SESSION_DESKTOP` (`GameCore` vs
`gamecore`) était la cause. **C'était faux.** J'avais lu l'environnement du
script bash lancé par SDDM ; celui d'Electron, sous
`gamecore-ui.service`, porte `gamecore` en minuscules — c'est le script de
session qui l'écrit — donc l'ancienne comparaison passait. Le correctif reste
utile (les deux orthographes existent selon qui demande) mais il n'a rien
débloqué.

Leçon : lire l'environnement du **processus concerné**, pas celui de son
ancêtre.

## Dette laissée derrière

- La suite de tests écrit dans le journal de la machine : `test_session_install`
  exécute le vrai `gamecore-session-select`, qui appelle maintenant `logger`.
  Une vingtaine de lignes `gamecore-session-select[…]` datées 08:24:17 en
  viennent. Inoffensif mais sale — il faut neutraliser `logger` sous test
  (variable d'environnement, ou stub dans le PATH de la fixture).
- `gamecore-ui.service:26: Unknown key 'StartLimitIntervalSec' in section
  [Service]` à chaque démarrage : la clé appartient à `[Unit]`, pas à
  `[Service]`. Donc `StartLimitBurst` ne borne rien aujourd'hui.
