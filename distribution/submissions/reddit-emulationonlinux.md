# r/EmulationOnLinux — post à publier

**Le public le plus proche du projet, et le plus exigeant sur les détails.** Ici
on ne vend pas une expérience salon : on parle configuration de manettes,
Flatpak, et RPCS3. C'est la seule communauté de cette phase qui vérifiera les
affirmations techniques — donc la seule où il faut être précis, et où être
précis suffit.

**Avant de poster** : lire les règles du subreddit dans la barre latérale.
Beaucoup de subs d'émulation interdisent tout lien vers des ROMs ou des BIOS —
le post ci-dessous n'en contient aucun et n'y fait aucune allusion, et ça doit
le rester.

**Flair** : `Project` ou `Discussion` selon ce qui existe. Sans flair, le post
est retiré automatiquement sur la plupart de ces subs.

> **Si l'ISO est publiée** : remplacer le paragraphe « Getting it » par
> « There's a bootable ISO if the machine has no Linux on it yet, or a graphical
> installer if it already runs Arch or Manjaro. »

---

## Titre

```
I built a couch emulation frontend for Arch that auto-configures controllers inside each emulator (RPCS3, Ryujinx, Dolphin, Cemu…)
```

> Le titre porte le **détail technique**, pas l'ambition. « J'ai fait un frontend
> d'émulation » ne se distingue de rien ; « il configure les manettes dans RPCS3
> et Ryujinx » est un problème que ce public a eu personnellement.

## Corps

```markdown
I've been building a living-room emulation frontend for Arch for a while and it
has reached the point where it's genuinely usable, so here it is.

The short version: it boots straight into a full-screen, gamepad-only launcher
on a normal Arch install, and it's weighted towards the recent consoles — PS3,
PS4, Switch, Wii U, Xbox 360 — with the classics alongside. Thirteen systems.

Two things in it are worth this sub's time specifically.

**Emulators are Flatpaks from Flathub, not bundled builds.**

They update on their own, independently of the frontend. This is the part I care
most about: RPCS3 and Ryujinx change every few weeks, and on a frozen system
image you wait for the image. Here `flatpak update` is the whole story. The
trade-off is that first install needs a network, and Flatpak sandboxing needed
real work — each emulator gets `--filesystem` for the ROM directory and
`--device=all` for controllers, granted automatically at install.

**Controllers are configured inside each emulator, per player slot.**

Not just in the launcher's menus — the actual emulator config files. This turned
out to be much less uniform than I expected, and the details might save someone
else the reverse-engineering:

- PCSX2, DuckStation and gopher64 speak SDL's role vocabulary (`SDL-0/FaceEast`),
  so exporting the community SDL_GameControllerDB through
  `SDL_GAMECONTROLLERCONFIG_FILE` covers any pad in the database with zero
  config. Worth noting that's *the* variable SDL actually reads —
  `SDL_GAMECONTROLLERDB` is not one, and I shipped that for a while before
  noticing the database was being silently ignored.
- Dolphin and RPCS3 also use semantic roles, but pick the *device* by literal
  name (`Device = SDL/0/PS4 Controller`). Both bundle SDL3, whose device names
  differ from the SDL2-era community database — a DualSense is "DualSense
  Wireless Controller", not "PS5 Controller". So the name gets resolved by
  asking the system's libSDL3 with the pads actually connected. And the number
  in that string is *not* the player slot: RPCS3 appends a 1-based counter per
  name, Dolphin a 0-based one, so a lone DualSense is "…Controller 1" even as
  Player 2.
- Ryujinx binds by device GUID and resolves it by string equality. No match is
  −1, and −1 disposes the slot silently — no log line, nothing in Input
  Settings. The GUID carries bus type and driver signature, so the same DS4 has
  different GUIDs over USB and Bluetooth; it can't be derived from vendor:product.
  Ryujinx renders SDL2's 16 raw GUID bytes through .NET's `System.Guid`, which
  reverses the first three fields, so the conversion has to be done exactly.

The first pad plugged in is Player 1 whatever brand it is, the next is Player 2,
like a real console. No slot is ever tied to a brand.

For a pad nothing recognises there's a mapping wizard: one button at a time,
full screen, about a minute. It's driven entirely by the pad being mapped —
press to record, hold to skip a button the pad doesn't have, double-press to go
back — because a controller the box can't understand is exactly the one you
can't use normal navigation with.

**Everything else stays a normal machine.** It's plain Arch with KDE Plasma
underneath, nothing read-only. `sudo gamecore-session-select desktop` closes the
kiosk and gives you a PC back.

**Getting it.** If the machine already runs Arch or Manjaro there's a graphical
installer on the releases page. Updates are over the air from the settings
screen.

GPL-3.0. Source: https://github.com/p4v1c/GamecoreRenew

Happy to answer anything about the controller side in particular — that's where
almost all the time went, and where I'd most like to be told I got something
wrong.
```

---

## Notes pour la réponse aux commentaires

Trois questions vont tomber, et il vaut mieux avoir la réponse prête que
d'improviser.

- **« Pourquoi pas Batocera / EmuDeck ? »** — Répondre par l'usage, jamais par la
  comparaison : consoles récentes en priorité, émulateurs qui se mettent à jour
  seuls, machine qui reste une machine. **Ne pas dire que Batocera est moins
  bien.** C'est un projet respecté ici, et l'attaquer coûte le fil entier.
- **« Ça marche sur autre chose qu'Arch ? »** — Non, et le dire franchement.
  L'installateur est spécifique à Arch/Manjaro et le stack est X11 uniquement.
  Une réponse évasive se paie en tickets d'installation.
- **« Et les ROMs / BIOS ? »** — Le projet n'en distribue aucun, n'en télécharge
  aucun, et n'a pas de scraper qui en cherche. Réponse courte, pas de débat.

Et une quatrième, qui viendra forcément parce que le post insiste sur le
multi-manettes :

- **« Tu l'as testé avec combien de manettes ? »** — La réponse honnête, et il
  faut la donner telle quelle : **une seule manette physique** sur la machine de
  développement, une DualShock 4. Deux, trois et quatre manettes sont couvertes
  par un harnais de caractérisation qui rejoue des ensembles synthétiques contre
  les vrais générateurs et compare aux sorties enregistrées — c'est une vraie
  preuve pour la génération des configs, et ce n'est **pas** une preuve que
  quatre pads jouent ensemble sur du matériel réel.
>
> Dire ça coûte moins que de se faire prendre : ce sub compte des gens qui ont
> quatre manettes et qui essaieront. Se faire contredire par un commentaire
> après avoir affirmé le contraire tue le fil ; l'avoir annoncé d'avance
> transforme le même commentaire en rapport de test.

Le principe général : ce sub sanctionne le survendu. Ce qui n'a pas été branché
se dit. Ici c'est un signal de sérieux, pas une faiblesse.
