# LinuxFr — dépêche à soumettre

**Où** : https://linuxfr.org/redaction — une dépêche part en **espace de
rédaction collaborative**, elle n'est pas publiée directement. D'autres
contributeurs la relisent, la corrigent et l'amendent avant qu'un modérateur la
publie. C'est une bonne chose : c'est le seul canal de cette phase où le texte
est amélioré par des tiers avant d'être vu.

Ça change deux choses par rapport à Reddit :

1. **Le délai** est de plusieurs jours, parfois plus. Ne pas soumettre la veille
   d'attendre du trafic.
2. **Le format compte.** LinuxFr attend une dépêche structurée avec un chapô, des
   sections, des liens — pas un post. Le texte ci-dessous l'est.

Le public est technique, francophone, et **allergique au marketing**. Il
récompense en revanche la franchise technique : les paragraphes sur ce qui a été
difficile et sur ce qui ne marche pas sont ce qui sera lu et commenté.

> **Si l'ISO est publiée** : dans la section « Installation », remplacer le
> paragraphe par la version ISO indiquée en commentaire à cet endroit.

---

## Titre

```
GameCore, une box de salon sous Arch pour les consoles récentes
```

## Sous-titre / chapô

```
Un frontend d'émulation piloté à la manette, orienté PS3, PS4, Switch, Wii U et
Xbox 360, dont les émulateurs se mettent à jour tout seuls et sous lequel la
machine reste une vraie machine.
```

## Corps de la dépêche

```markdown
Les systèmes d'émulation pour le salon ne manquent pas, mais ils partagent deux
partis pris : ils couvrent surtout des machines anciennes, et ils sont livrés
sous forme d'image système figée. Les deux se tiennent — c'est ce qui rend ces
projets robustes et faciles à installer.

GameCore prend les deux à l'envers, pour un usage précis : émuler les consoles
récentes sur une machine qui reste une machine.

C'est un logiciel libre sous GPL-3.0-or-later, développé pour une box de salon
sous Arch, et il est arrivé à un état où il fait le travail au quotidien.

----

# Ce que c'est

Un lanceur plein écran qui démarre à la place du bureau, se pilote entièrement à
la manette, et ne demande jamais ni clavier ni souris. Derrière, un backend
FastAPI et une interface React dans une coquille Electron.

Treize systèmes, dont le cœur est volontairement du côté récent : PlayStation 3
(RPCS3), PlayStation 4 (shadPS4), Switch (Ryujinx), Wii U (Cemu), Xbox 360
(Xenia Canary sous Wine), plus PS2, PSP, GameCube/Wii, 3DS, DS, GBA, N64 et PS1.

# Les émulateurs sont des Flatpaks, et c'est le point central

Ils viennent de Flathub et se mettent à jour indépendamment du frontend.

Ce choix est le seul qui rende l'objectif tenable. RPCS3 et Ryujinx changent
toutes les quelques semaines, et sur une image système figée, une correction de
compatibilité attend la prochaine version de l'image. Ici elle arrive par
`flatpak update`.

Le prix à payer est réel et il vaut mieux l'annoncer : la première installation
exige un réseau, et le bac à sable Flatpak a demandé du travail. Chaque
émulateur reçoit automatiquement un `--filesystem` sur le répertoire des ROMs et
un `--device=all` pour les manettes, sans quoi il ne voit ni les jeux ni les
pads.

# La configuration des manettes, ou pourquoi c'est là qu'est passé le temps

L'objectif : brancher une manette et qu'elle fonctionne *dans les émulateurs*,
par emplacement de joueur, sans écran de configuration. La première manette
branchée est le joueur un quelle que soit sa marque, la suivante le joueur deux.
Aucun emplacement n'est câblé à une marque.

Ça paraît simple. Ça ne l'est pas, parce que chaque émulateur identifie les
périphériques différemment — et deux d'entre eux échouent *en silence*.

- **PCSX2, DuckStation et gopher64** parlent le vocabulaire de rôles de SDL
  (`SDL-0/FaceEast`). Exporter la base communautaire SDL_GameControllerDB via
  `SDL_GAMECONTROLLERCONFIG_FILE` suffit : n'importe quel pad de la base
  fonctionne sans configuration. À noter, c'est bien cette variable-là que SDL
  lit — `SDL_GAMECONTROLLERDB` n'en est pas une, et tant qu'elle était utilisée
  la base était ignorée sans le moindre message.

- **Dolphin et RPCS3** utilisent aussi des rôles sémantiques, mais choisissent le
  périphérique par un **nom littéral** (`Device = SDL/0/PS4 Controller`). Deux
  pièges. D'abord, tous deux embarquent SDL3, dont les noms diffèrent de ceux de
  la base communautaire d'époque SDL2 : une DualSense s'appelle « DualSense
  Wireless Controller » et non « PS5 Controller ». Le nom est donc résolu en
  interrogeant la libSDL3 du système avec les pads réellement connectés. Ensuite,
  le nombre dans cette chaîne **n'est pas l'emplacement du joueur** : RPCS3 y met
  un compteur commençant à 1 par nom de périphérique, Dolphin un compteur
  commençant à 0 — une DualSense seule est « …Controller 1 » même en joueur deux.

- **Ryujinx** se lie par GUID de périphérique et le résout par égalité de
  chaînes. Pas de correspondance vaut −1, et −1 détruit l'emplacement sans un
  message ni une trace dans l'interface. Ce GUID porte le type de bus et la
  signature du pilote : la même DualShock 4 n'a pas le même GUID en USB et en
  Bluetooth, et il ne se déduit pas d'un couple vendeur:produit. Ryujinx rend les
  16 octets bruts du GUID SDL2 à travers le `System.Guid` de .NET, qui inverse
  les trois premiers champs — la conversion doit être faite exactement.

Pour une manette que rien ne reconnaît, un assistant de mappage prend le relais :
un bouton à la fois, plein écran, une minute environ. Il est piloté uniquement
par la manette en cours de configuration — un appui enregistre, un appui long
saute un bouton absent, deux appuis reviennent en arrière — parce que la manette
qu'on configure est par définition celle dont aucune touche n'est encore
utilisable pour naviguer.

# La machine reste une machine

C'est une Arch complète avec un bureau KDE Plasma en dessous. Rien n'est en
lecture seule, rien n'est verrouillé. Une commande ferme le kiosque et rend un
PC ordinaire :

    sudo gamecore-session-select desktop
    sudo gamecore-session-select gamecore

Les données de joueur (ROMs, sauvegardes, jaquettes, configuration) vivent sur
une partition séparée, ce qui leur permet de survivre à une réinstallation du
système.

# Installation

<!-- Version actuelle. À remplacer si l'ISO est publiée. -->
Sur une machine qui tourne déjà sous Arch ou Manjaro, un installateur graphique
est disponible sur la page des versions. Les mises à jour se font ensuite par
OTA depuis l'écran de réglages.

<!-- Version ISO, quand elle existera :
Une image ISO est disponible : elle installe le système complet sur une machine
nue, sans Linux préalable et sans réseau. Sur une machine qui tourne déjà sous
Arch ou Manjaro, un installateur graphique fait le même travail. Les mises à
jour se font ensuite par OTA depuis l'écran de réglages.
-->

# Limites, annoncées

- **Arch et Manjaro uniquement.** L'installateur leur est spécifique.
- **X11 seulement.** Les overlays, le forçage du plein écran et le pont
  manette→clavier en dépendent tous. Wayland n'est pas un petit chantier.
- **Une seule manette physique** sur la machine de développement. Les
  configurations à deux, trois et quatre manettes sont couvertes par un harnais
  qui rejoue des ensembles synthétiques contre les vrais générateurs et compare
  à des sorties enregistrées — c'est une preuve pour la génération des fichiers
  de configuration, ce n'en est pas une pour quatre joueurs sur du matériel réel.
- **Un seul développeur.** Le facteur d'autobus vaut un.
- Le projet ne distribue ni ROMs, ni BIOS, ni clés, et n'en télécharge aucun.

# Liens

- Le dépôt : https://github.com/p4v1c/GamecoreRenew
- La documentation des manettes, qui détaille tout ce qui est résumé ci-dessus :
  https://github.com/p4v1c/GamecoreRenew/blob/main/docs/CONTROLLER_MODELS.md
```

---

## Notes de soumission

- **Choisir la bonne catégorie** : « Jeu » ou « Logiciel de bureau » selon ce que
  propose le formulaire. En cas de doute, « Jeu » — c'est là que le public visé
  regarde.
- **Ne pas s'agacer des amendements.** L'espace de rédaction va reformuler des
  phrases et peut-être retirer ce qui ressemble trop à de la promotion. C'est le
  fonctionnement normal, et le résultat est en général meilleur.
- **Répondre aux commentaires techniques**, ils sont la valeur du canal. Le
  lectorat de LinuxFr contient des gens qui connaissent SDL et Flatpak mieux que
  nous ; les sections sur les GUID Ryujinx et sur les noms SDL3 sont exactement
  ce qui va attirer une correction utile.
- **Relire les affirmations à la première personne** avant de soumettre, comme
  pour Reddit : la dépêche est rédigée par un tiers, et ce qui relève de
  l'expérience personnelle n'est vérifiable que par le propriétaire.
