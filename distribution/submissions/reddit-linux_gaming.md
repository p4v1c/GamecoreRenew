# r/linux_gaming — post à publier

**Public beaucoup plus large que r/EmulationOnLinux, et beaucoup plus méfiant
envers l'autopromotion.** Le sub a plus d'un million d'abonnés ; un post qui
sent le communiqué se fait enterrer en downvotes dans l'heure.

Ce qui passe ici, c'est un projet personnel raconté par la personne qui l'a fait,
avec ses limites annoncées. Le post ci-dessous est donc plus court que celui de
r/EmulationOnLinux, moins technique, et il **dit ce qui ne marche pas** — ce
n'est pas de la modestie, c'est ce qui fait la différence entre un fil qui vit et
un fil qui meurt.

**Avant de poster :**

- lire les règles du sub, en particulier celles sur l'autopromotion — certaines
  exigent un ratio de participation ou une ancienneté de compte ;
- mettre le flair. Ici c'est probablement **`Software`** ou **`Emulation`** ;
- poster en semaine, en matinée européenne. Un dimanche soir, le fil est enterré
  avant que qui que ce soit le voie ;
- **ne pas poster le même jour que r/EmulationOnLinux.** Les deux audiences se
  recoupent, et le crosspost simultané se lit comme du spam ;
- **relire les affirmations à la première personne.** Ce texte est écrit pour
  être signé par le propriétaire, mais il est rédigé par quelqu'un d'autre :
  « c'est ce qui tourne sous ma télé », « ça m'a pris un moment », « j'ai
  exactement une manette » sont des affirmations biographiques. Elles collent à
  ce que le dépôt laisse voir, mais **seul le propriétaire sait si elles sont
  vraies** — et sur un sub qui sanctionne le survendu, une seule qui ne l'est
  pas coûte plus que tout ce que le post rapporte. À corriger sans état d'âme,
  le ton compte moins que l'exactitude.

> **Si l'ISO est publiée** : remplacer la puce « It only installs on Arch or
> Manjaro » par « It ships an ISO if you're starting from a bare machine, and an
> installer if you already run Arch or Manjaro » — et **déplacer cette puce hors
> de la section des limites**, puisque ce n'en est plus une.

---

## Titre

```
I spent a while turning an old PC into a console for the living room — PS3, PS4, Switch and Wii U, driven entirely with a gamepad
```

> Le titre raconte un projet, pas un produit. « J'ai passé un moment à » est ce
> qui fait la différence entre un post accueilli et un post signalé — et c'est
> vrai, donc ce n'est pas une posture.

## Corps

```markdown
I wanted the machine under my TV to behave like a console: turn it on, it's
there, drive everything with the pad, never see a desktop or a keyboard. What
existed either targeted mostly older systems, or handed me a frozen system image
where I couldn't just update an emulator when it needed it. So I built my own,
and it's what runs under my TV.

It's called GameCore. It's a full-screen launcher on top of a normal Arch
install — thirteen systems, weighted towards the recent consoles (PS3, PS4,
Switch, Wii U, Xbox 360) rather than the usual long tail of 8-bit machines.

**The parts I'm actually happy with:**

- **The emulators are Flatpaks from Flathub.** They update independently of my
  frontend, which matters enormously for the recent stuff — RPCS3 and Ryujinx
  change every few weeks, and I didn't want a release of mine to be what gates a
  compatibility fix reaching my TV.
- **Controllers configure themselves, inside the emulators.** Plug a pad in and
  it works in RPCS3, Dolphin, Cemu, Ryujinx and the rest, per player slot, with
  no config screen. The first pad plugged in is Player 1 whatever brand it is.
  This was by far the hardest part — every emulator identifies devices
  differently, and two of them fail *silently* when you get it wrong, which is
  a wonderful way to lose an evening.
- **It's still a real computer.** Plain Arch with KDE Plasma underneath, nothing
  read-only. One command closes the kiosk and I have my desktop back. I didn't
  want to give up a machine to gain a console.
- **There's a mapping wizard** for pads nothing recognises — one button at a
  time, about a minute, driven entirely by the pad you're mapping, no keyboard.

**The parts that are honestly limitations:**

- **It only installs on Arch or Manjaro.** There's a graphical installer, but if
  you run something else, this isn't for you today.
- **X11 only.** The overlay system, the fullscreen enforcer and the
  gamepad-to-keyboard bridge all depend on it. Wayland is not a small change.
- **I have exactly one controller.** Two-, three- and four-pad setups are
  covered by a test harness that replays synthetic controller sets against the
  real config generators and compares against recorded output — so I'm
  reasonably confident in the generated configs, but I have not sat four people
  down in front of it. If you try it with a pile of pads I'd genuinely like to
  know what happens.
- **First install needs a network**, because the emulators come from Flathub.
- It's one person's project. The bus factor is one.

GPL-3.0, source is here: https://github.com/p4v1c/GamecoreRenew

Happy to answer questions, and happy to be told what I got wrong.
```

---

## Notes pour la réponse aux commentaires

- **« Pourquoi pas Bazzite / ChimeraOS / Batocera ? »** — Elle viendra en premier
  et probablement plusieurs fois. Répondre par ce qu'on voulait, pas par ce
  qu'ils n'ont pas : consoles récentes en priorité, émulateurs à jour
  indépendamment, machine qui reste utilisable normalement. **Ne dénigrer aucun
  des trois** — beaucoup de lecteurs les utilisent, et les critiquer transforme
  le fil en défense.
- **« Pourquoi Arch et pas Debian/Fedora ? »** — Parce que les émulateurs récents
  ont besoin de paquets système récents, et parce que c'est ce qui tourne sur la
  boîte. C'est une réponse suffisante ; ne pas tenter d'en faire un argument
  technique universel.
- **« Wayland ? »** — Non, et dire pourquoi précisément (overlays, plein écran
  forcé, pont manette→clavier). Ne pas promettre de date. Une promesse de
  roadmap dans un commentaire Reddit est citée six mois plus tard.
- **Un rapport de bug dans les commentaires** — demander une issue GitHub, mais
  **répondre quand même sur le fond dans le fil**. « Ouvre une issue » tout court
  se lit comme une esquive.

Et le réflexe à ne pas avoir : **ne pas répondre aux downvotes ni aux
commentaires hostiles.** Sur ce sub, un auteur qui se défend fait toujours pire
que le commentaire qu'il combat.
