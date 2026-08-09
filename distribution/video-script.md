# Vidéo — 3 minutes

Dans cette niche, la vidéo se classe mieux que n'importe quelle page, et c'est
elle qui crée les recherches sur le nom. Une personne qui cherche « ps3 emulator
living room » n'a aujourd'hui aucun résultat qui lui montre le résultat final en
mouvement.

**La règle qui gouverne tout le script : on ne raconte pas, on montre.** Chaque
seconde de voix off qui décrit ce que l'image montre déjà est une seconde
perdue. Le montage tient les 3 minutes sans une seule diapositive de texte.

---

## ⚠️ À régler avant de tourner

> **Le lien de fin.** Voir [`BLOQUANT-iso.md`](BLOQUANT-iso.md) : l'ISO n'existe
> sur aucune release. Le plan de fin (2:40) dit donc « télécharge
> l'installateur », pas « grave l'ISO ». Si l'ISO est publiée d'ici le tournage,
> la substitution est indiquée sur ce plan — et c'est un meilleur plan de fin.

> **Rien de sous copyright à l'écran.** C'est la contrainte la plus facile à
> oublier au montage et la plus coûteuse : une vidéo d'émulation qui affiche des
> jaquettes commerciales, des titres de jeux et du gameplay se fait démonétiser
> ou retirer, et le lien meurt avec elle. Concrètement :
> - **jamais de gameplay filmé** — on coupe à la seconde où le jeu rend l'image ;
> - **pas de jaquettes** dans la bibliothèque : peupler la démo avec des
>   homebrews et des demos libres, dont les jaquettes sont les leurs ;
> - **aucun nom de fichier de ROM** visible, nulle part, y compris dans un
>   terminal ou une notification qui passe ;
> - **pas de BIOS, pas de clés** à l'écran, même flous.
>
> Ce que la vidéo doit prouver, c'est que **la boîte lance**, pas ce qu'elle
> lance. Le lancement s'arrête au logo de l'émulateur : c'est suffisant, et
> c'est sûr.

---

## Le tournage

**Une seule prise pour l'écran, aucune coupe cachée.** L'argument du projet est
« ça marche tout seul » ; un montage qui saute d'un plan à l'autre au moment
précis où quelque chose se configure détruit exactement ce qu'il essaie de
prouver. Filmer la séquence complète en continu et couper dans la longueur, pas
dans la logique.

- **Écran** : capture HDMI de la boîte, 1080p60. Pas de captation logicielle sur
  la boîte elle-même — elle coûte des images et ça se voit sur les animations.
- **Mains** : une seconde caméra sur la manette, à hauteur de table, pour les
  plans de branchement et le wizard. C'est le plan qui rend le propos physique.
- **Son** : le son de la boîte (les sons d'interface sont un thème, ils
  existent), plus une voix off enregistrée séparément. Pas de musique sous la
  voix — elle sature les 3 minutes et fatigue.

---

## Le script

Les timecodes sont des cibles ; la marge est dans les plans 2 et 6.

### 0:00 — 0:12 · Le démarrage, sans un mot

**Image** — Plan large : une télé, une box, une manette posée. La box est
éteinte. Un doigt appuie sur le bouton d'alimentation.
Coupe sur la capture HDMI : logo de démarrage, splash, **écran d'accueil**.
Le chrono du plan reste visible en bas à gauche pendant toute la séquence.

**Voix off** — *rien.* Pas un mot pendant douze secondes.

> Ce plan est l'argument entier du projet et il n'a pas besoin d'être commenté.
> Le chrono est là parce que « ça démarre vite » est une affirmation, et que le
> chrono est une preuve. **Ne pas le truquer et ne pas accélérer l'image** : si
> le démarrage prend quarante secondes, on montre quarante secondes ou on coupe
> le plan avec un fondu honnête et on annonce la durée réelle à l'oral.

### 0:12 — 0:35 · Ce que c'est

**Image** — Navigation à la manette sur l'accueil, puis la bibliothèque. On
descend la liste des systèmes : PS3, PS4, Switch, Wii U, Xbox 360 défilent en
tête. On s'arrête une seconde sur la liste complète.

**Voix off** —
> « Ça, c'est une machine sous Arch Linux, dans un salon, pilotée uniquement à
> la manette. Treize systèmes — et contrairement à la plupart des boîtes de ce
> genre, ce sont les consoles récentes qui sont en tête de liste : PS3, PS4,
> Switch, Wii U, Xbox 360. »

### 0:35 — 1:05 · La manette, sans rien configurer

**Image** — Plan mains : une **deuxième** manette, d'une autre marque que la
première, sortie de sa boîte. On la branche.
Coupe écran : l'indicateur de manette passe à deux. Le joueur 2 apparaît.
La deuxième manette navigue immédiatement dans le menu.

**Voix off** —
> « Une manette qu'on branche est utilisable tout de suite. Pas d'écran de
> configuration, pas de fichier à éditer — et c'est vrai dans les émulateurs
> aussi, pas seulement dans le menu. La première manette branchée est le joueur
> un, la suivante le joueur deux. Comme sur une console. »

> Utiliser deux marques différentes est le point du plan. Deux manettes
> identiques ne prouvent rien : c'est le cas facile.
>
> **Il n'y a qu'une manette sur la machine de développement** (une DualShock 4).
> Ce plan demande donc du matériel qui n'est pas là au moment où ce script est
> écrit. S'il ne peut pas être tourné avec deux pads réels, **le couper
> entièrement** et garder la démonstration à une manette : le harnais de
> caractérisation prouve le multi-manettes dans les tests, mais une vidéo ne
> peut montrer que ce qui a été branché.

### 1:05 — 1:45 · On lance. Switch, puis PS3.

**Image** — Bibliothèque → système Switch → un jeu (homebrew) → **A**.
L'émulateur s'ouvre, la fenêtre apparaît, le logo s'affiche. **Coupe.**
Retour accueil par le bouton Guide, sans lâcher la manette.
Puis : système PS3 → un jeu → **A**. RPCS3 s'ouvre. **Coupe.**

**Voix off** —
> « On lance depuis le canapé, et on revient au menu avec le bouton Guide sans
> jamais toucher un clavier. Les émulateurs, eux, sont des Flatpaks : ils se
> mettent à jour depuis Flathub, à leur rythme. RPCS3 bouge toutes les semaines
> — sur une image figée, on attend la prochaine version de la distribution. Ici,
> non. »

> Le retour par le bouton Guide est important à montrer : c'est la question
> « et on en sort comment ? » à laquelle toute boîte de ce type doit répondre.

### 1:45 — 2:30 · Le wizard de mappage

**Image** — Plan mains sur une manette générique, sans marque, du genre que
personne ne reconnaît. On la branche : elle ne navigue pas correctement.
Coupe écran : Réglages → Manettes → **Mapper cette manette**.
Le wizard démarre. Un bouton à la fois, plein écran. On voit :
- une **pression** qui enregistre et avance,
- un **maintien** qui saute un bouton que le pad n'a pas,
- une **double pression** qui revient en arrière.

Fin du wizard, écran de revue, sauvegarde. La manette navigue.

**Voix off** —
> « Et pour une manette que personne ne connaît, il y a ce wizard. Un bouton à
> la fois, et il est piloté entièrement par la manette qu'on est en train de
> configurer — parce qu'à ce moment-là, c'est le seul périphérique dont on soit
> sûr. Un appui enregistre. Un appui long saute un bouton que la manette n'a
> pas. Deux appuis reviennent en arrière. Une minute, sans clavier. »

> C'est le plan le plus convaincant de la vidéo pour un public d'émulation :
> tout le monde dans cette communauté a déjà passé une soirée sur un fichier de
> mapping. Ne pas l'accélérer, et **laisser le maintien durer** — c'est
> précisément la gestuelle qu'il faut avoir vue une fois pour la reproduire.

### 2:30 — 2:40 · La vraie machine

**Image** — Réglages → Quitter vers le bureau. Le kiosque se ferme, **un bureau
Plasma complet** apparaît. Un navigateur s'ouvre. Puis, en une commande dans un
terminal, retour au kiosque.

**Voix off** —
> « Et en dessous, c'est une Arch complète. Pas une image en lecture seule : un
> vrai PC, avec un bureau, sur lequel on installe ce qu'on veut. »

> Ce plan répond à la seule objection sérieuse que fait le public technique aux
> boîtes de salon : « je perds ma machine ». Dix secondes suffisent.

### 2:40 — 3:00 · Où le prendre

**Image** — Retour sur l'accueil de GameCore. L'URL du site s'affiche en
surimpression, lisible, immobile, jusqu'à la fin.

**Voix off** —
> « C'est du logiciel libre, en GPL. Si la machine tourne déjà sous Arch ou
> Manjaro, il y a un installateur graphique à télécharger — le lien est en
> description. »

> **Si l'ISO est publiée**, remplacer cette dernière phrase par :
> « Il y a une image ISO à graver sur une clé : tu n'as pas besoin d'installer
> Arch d'abord, ni même d'avoir Linux. Le lien est en description. »
> C'est une bien meilleure fin — elle enlève la seule condition d'entrée.

---

## Le texte de la publication (YouTube)

### Titre

Le titre porte la requête, pas le nom : personne ne cherche « GameCore ».

```
A living-room emulation box for PS3, PS4, Switch and Wii U — on Arch Linux
```

Variante si la chaîne est francophone :

```
Une box salon pour émuler PS3, PS4, Switch et Wii U — sous Arch Linux
```

### Description

Les deux premières lignes sont les seules visibles avant « plus » : elles
portent l'angle, et le lien est haut.

```
GameCore is a gamepad-only frontend for a living-room Arch Linux box, built
around the recent consoles — PS3, PS4, Switch, Wii U, Xbox 360 — with emulators
that stay current because they come from Flathub.

→ https://p4v1c.github.io/GamecoreRenew/
→ Source (GPL-3.0): https://github.com/p4v1c/GamecoreRenew

00:00  Boot, from cold to the home screen
00:12  Thirteen systems, recent consoles first
00:35  Plug a pad in — it just works, in the emulators too
01:05  Launching a Switch game, then a PS3 one
01:45  The mapping wizard: any controller, about a minute, no keyboard
02:30  Exit to the desktop — it is still a real Arch machine
02:40  Where to get it

Controllers are configured automatically in each emulator: GameCore writes the
emulator's own config for the pads actually connected, per player slot. The
first pad plugged in is Player 1, whatever brand it is.

No games, ROMs or BIOS files are shown or provided in this video. Everything on
screen is homebrew or a freely distributable demo.
```

> La dernière ligne n'est pas de la prudence décorative : elle est ce qu'un
> modérateur lit en premier sur un signalement, et c'est elle qui fait la
> différence entre une vidéo examinée et une vidéo retirée.

### Tags

```
emulation, linux gaming, arch linux, ps3 emulator, rpcs3, switch emulator,
wii u emulator, cemu, retrogaming, htpc, couch gaming, emulation frontend,
batocera alternative, flatpak, gamepad
```

`batocera alternative` est ici — dans les tags, où il capte une recherche
existante — et **nulle part dans le titre, la description ou la voix off**. La
comparaison en largeur est perdue d'avance ; la requête, elle, se prend.
