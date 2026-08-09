# Awesome-lists — la ligne, et le corps de PR

Les awesome-lists sont le canal le plus lent et le plus durable : une ligne
acceptée reste des années et fait un backlink depuis un dépôt très bien classé.
Elles sont aussi les plus faciles à se faire refuser, pour une raison unique et
constante : **une PR qui ne respecte pas le format de la liste est fermée sans
discussion.**

Donc, dans l'ordre, à chaque fois :

1. lire le `CONTRIBUTING.md` de la liste visée ;
2. **copier le format exact d'une ligne voisine** — tiret, gras ou pas, point
   final ou pas, ordre alphabétique ou non ;
3. une PR par liste, jamais une PR groupée.

> **Si l'ISO est publiée** : dans le corps de PR, remplacer la ligne
> « Installs onto an existing Arch/Manjaro system with a graphical installer »
> par « Ships a bootable ISO, or installs onto an existing Arch/Manjaro system ».

---

## Les listes visées, par ordre de pertinence

| Liste | Section probable | Remarque |
|---|---|---|
| [`awesome-emulators`](https://github.com/tomconte/awesome-emulators) | Frontends | La plus directe. |
| [`awesome-linux-gaming`](https://github.com/dgvai/awesome-linux-gaming) | Emulation | Recoupe l'audience de r/linux_gaming. |
| [`awesome-selfhosted`](https://github.com/awesome-selfhosted/awesome-selfhosted) | — | **Ne pas soumettre.** GameCore n'est pas un service auto-hébergé ; la PR sera refusée et c'est justifié. |
| [`awesome-arch`](https://github.com/PandaFoss/Awesome-Arch) | Applications | Angle Arch, plus petite mais très ciblée. |

---

## La ligne

Format le plus courant (`- [Nom](url) - Description.`) :

```markdown
- [GameCore](https://github.com/p4v1c/GamecoreRenew) - Gamepad-driven living-room emulation frontend for Arch Linux, built around the recent consoles (PS3, PS4, Switch, Wii U, Xbox 360) with Flatpak emulators that stay current and controllers that configure themselves.
```

Si la liste impose des descriptions courtes (beaucoup plafonnent autour de 100
caractères) :

```markdown
- [GameCore](https://github.com/p4v1c/GamecoreRenew) - Living-room emulation frontend for Arch Linux, recent consoles first.
```

> Le lien pointe le **dépôt**, pas le site : les awesome-lists attendent un
> projet, et une entrée qui pointe une page marketing plutôt qu'un dépôt se fait
> régulièrement demander de changer. Le site est de toute façon lié depuis le
> About du dépôt.

---

## Corps de la PR

Court. Le mainteneur d'une awesome-list en lit des dizaines et cherche trois
choses : est-ce vivant, est-ce libre, est-ce à sa place.

```markdown
### What it is

GameCore is a gamepad-only emulation frontend for a living-room Arch Linux box.
It boots into a full-screen launcher — no desktop, no keyboard — and covers
thirteen systems, weighted towards the recent consoles: PS3, PS4, Switch, Wii U
and Xbox 360.

### Why it fits this list

- Free software, GPL-3.0-or-later.
- Actively developed, with tagged releases and CI on every merge.
- It is a frontend, not an emulator: it installs and drives existing ones
  (RPCS3, Ryujinx, Cemu, Dolphin, PCSX2, DuckStation and others) rather than
  reimplementing anything.

### What makes it different from the frontends already listed

- Emulators are Flatpaks from Flathub, so they update independently of the
  frontend. RPCS3 and Ryujinx move every few weeks; a frozen system image holds
  them back until its own next release.
- Controllers are configured automatically **inside each emulator**, per player
  slot, from the pads actually connected — not just in the launcher's own menus.
  A built-in wizard handles pads nothing recognises, driven entirely by the pad
  being mapped.
- It stays a normal Arch install with a KDE Plasma desktop underneath; one
  command closes the kiosk and hands the machine back.

Installs onto an existing Arch/Manjaro system with a graphical installer, and
updates over the air.

Docs: https://github.com/p4v1c/GamecoreRenew#readme
```

---

## Ce qu'il ne faut pas mettre dans la PR

- **Aucune comparaison nommée avec Batocera** ou avec une entrée déjà présente
  dans la liste. Un mainteneur lit ça comme « ma soumission mérite plus que la
  vôtre », et c'est le moyen le plus rapide de faire fermer une PR par ailleurs
  correcte. Les différences ci-dessus sont formulées en positif, sans nommer
  personne — c'est délibéré, ne pas le « corriger ».
- **Pas de captures d'écran** : ce sont des listes de texte, les images
  alourdissent la revue sans rien apporter.
- **Pas de mention du nombre d'étoiles**, ni de « nouveau projet ». Plusieurs
  listes exigent une ancienneté ou une popularité minimale ; l'annoncer soi-même
  fait appliquer le critère immédiatement.
