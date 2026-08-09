# AlternativeTo — fiche à soumettre

**Où** : https://alternativeto.net/manage/new-app/ (compte requis, création par
l'humain).

AlternativeTo est un annuaire : la fiche n'a d'intérêt que **par les « alternative
to » qu'elle déclare**, parce que le trafic arrive par les pages des concurrents,
jamais par une recherche sur le nom. C'est le seul canal de cette phase où la
comparaison est le mécanisme et pas une faiblesse — mais elle reste dans les
champs de liaison, jamais dans la description.

> **Si l'ISO est publiée** : ajouter « or a bootable ISO if it does not » à la fin
> du deuxième paragraphe de la description longue.

---

## Name

```
GameCore
```

> Il existe déjà plusieurs « GameCore » (un moteur Java, un IDE 3D, un moteur Mac
> sur SourceForge). Si le formulaire refuse le nom pour cause de doublon, utiliser
> `GameCore (emulation frontend)` — et **pas** `GamecoreRenew`, qui n'est le nom
> de rien pour un lecteur.

## URL

```
https://p4v1c.github.io/GamecoreRenew/
```

## Tagline (une ligne)

```
Living-room emulation frontend for Arch Linux, built around the recent consoles.
```

## Description

```
GameCore turns a PC into a console you drive from the couch with a gamepad. It
boots straight into a full-screen launcher: no desktop, no keyboard, no mouse.

Where most living-room emulation systems are built around decades of 8- and
16-bit machines, GameCore is built around the recent consoles first — PS3, PS4,
Switch, Wii U and Xbox 360 — with the classics alongside them, thirteen systems
in all. The emulators are Flatpaks from Flathub, so they update on their own
schedule rather than being frozen until the next release of the distribution.
That matters most exactly where it is hardest: RPCS3 and Ryujinx change every
few weeks.

Controllers configure themselves. GameCore writes each emulator's own
configuration for the pads actually connected, per player slot — the first pad
plugged in is Player 1 whatever brand it is, like a real console. For a
controller nothing recognises, a built-in wizard maps it in about a minute,
driven entirely by the pad being mapped, with no keyboard.

Underneath, it stays an ordinary Arch Linux machine with a KDE Plasma desktop.
One command closes the kiosk and gives you a normal PC back. Nothing is
read-only, nothing is locked down.

It installs onto an existing Arch or Manjaro system with a graphical installer,
updates itself over the air, and is free software under the GPL-3.0.
```

## Licensing model

```
Free / Open Source
```

## License

```
GPL-3.0-or-later
```

## Platforms

```
Linux
Self-Hosted
```

> Cocher **Linux** uniquement côté OS. Ne pas cocher Windows ni macOS : le stack
> est X11-only et l'installateur est spécifique à Arch. Une fiche qui promet une
> plateforme qu'elle ne sert pas récolte des votes négatifs et des commentaires
> « ça ne s'installe pas », qui restent visibles des années.

## Alternative to

Dans cet ordre — c'est l'ordre de pertinence décroissante, et c'est celui qui
détermine d'où vient le trafic :

```
Batocera.linux
RetroBat
EmulationStation
Playnite
```

Pour chacune, la note de comparaison si le formulaire la demande :

- **Batocera.linux** — même usage (une box salon pilotée à la manette), approche
  opposée : Batocera est une image système figée et en lecture seule couvrant un
  très grand nombre de machines anciennes ; GameCore est une Arch complète et
  modifiable, orientée consoles récentes, dont les émulateurs se mettent à jour
  indépendamment.
- **RetroBat** — même idée sur Windows ; GameCore est Linux uniquement.
- **EmulationStation** — EmulationStation est l'interface seule, à intégrer.
  GameCore est le système complet : installation, services, kiosque, mises à
  jour, configuration des manettes.
- **Playnite** — Playnite unifie des bibliothèques de jeux PC sous Windows.
  Recoupement réel sur le lanceur au canapé, aucun sur l'émulation Linux.

> **Ne pas ajouter RetroPie ni Lakka.** Ce sont des cibles ARM / bas de gamme, et
> une fiche qui se déclare alternative à un projet qu'elle ne remplace pas se
> fait corriger par les votes de la communauté — ce qui abîme la fiche entière,
> y compris les liaisons justes.

## Tags

```
emulator
emulation
game-launcher
retrogaming
htpc
kiosk
arch-linux
flatpak
gamepad
living-room
```

## Captures à joindre

Quatre, dans cet ordre. Ce sont des extractions de la vidéo, donc elles ne
coûtent rien de plus une fois celle-ci tournée — **et elles héritent de la même
contrainte : aucune jaquette commerciale, aucun nom de ROM lisible** (voir
[`../video-script.md`](../video-script.md)).

1. l'écran d'accueil ;
2. la bibliothèque, liste des systèmes visible, PS3/PS4/Switch en tête ;
3. le wizard de mappage en cours, un bouton affiché plein écran ;
4. l'écran des réglages.
