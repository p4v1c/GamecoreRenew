# Le About du dépôt — à appliquer à la main

GitHub, aujourd'hui, ne sert aucune description. Google n'a donc que la chaîne
par défaut :

```
Contribute to p4v1c/GamecoreRenew development by creating an account on GitHub.
```

C'est le seul texte que le dépôt émet vers l'extérieur. Le remplacer est le
changement le moins cher et le plus rentable de toute cette phase.

## Où

`https://github.com/p4v1c/GamecoreRenew` → bouton **⚙ (Settings)** à droite de
**About**, en haut de la colonne de droite de la page d'accueil du dépôt. Pas
dans Settings du dépôt : c'est bien la petite roue dentée du bloc About.

---

## 1. Description (une ligne)

Le champ est limité à 350 caractères, mais Google en coupe l'affichage autour de
155–160. **Tout ce qui compte doit tenir dans les 155 premiers.**

```
Living-room emulation frontend for Arch Linux — PS3, PS4, Switch, Wii U, Xbox 360 and 8 more. Always-current Flatpak emulators, auto-configured pads.
```

149 caractères — donc affichée entière par Google, sans troncature. Le découpage
est délibéré :

- **`Living-room emulation frontend for Arch Linux`** en tête — c'est la requête,
  pas le nom. Personne ne cherche « GameCore » ; des gens cherchent ces mots-là.
- **Les consoles nommées** ensuite, parce que `ps3`, `switch`, `wii u` sont ce
  qui est réellement tapé, et parce que c'est l'angle : les consoles récentes
  d'abord.
- **`Always-current Flatpak emulators, auto-configured pads`** en fin : les deux
  différenciateurs. `pads` plutôt que `controllers`, et la phrase coupée en deux
  plutôt qu'une virgule de plus, uniquement pour tenir sous 155.

Si « gamepad-only » doit absolument y être, cette variante fait 170 caractères
et Google la coupera juste avant `auto-configured` — c'est-à-dire qu'elle perd
en affichage le différenciateur qu'elle ajoute :

```
Living-room emulation frontend for Arch Linux — PS3, PS4, Switch, Wii U, Xbox 360 and 8 more, always-current Flatpak emulators, gamepad-only, auto-configured controllers.
```

Le mot est de toute façon dans le topic `gamepad` et dans le `<title>` du site.

---

## 2. Website

```
https://p4v1c.github.io/GamecoreRenew/
```

À mettre **après** avoir activé Pages (voir [`site.md`](site.md)) — un champ
Website qui 404 est pire que vide, il est suivi par les crawlers.

---

## 3. Topics

Les huit demandés, dans cet ordre (GitHub les affiche dans l'ordre de saisie) :

```
emulation-frontend
retrogaming
flatpak
arch-linux
electron
fastapi
gamepad
kiosk
```

À coller un par un dans le champ Topics. GitHub en accepte jusqu'à 20.

### Cinq de plus, à ajouter si on veut

Ils sont là parce que les pages `/topics/<nom>` de GitHub sont indexées et
servent de pages d'atterrissage — un topic est un canal de découverte, pas une
étiquette :

```
emulator
playstation-3
nintendo-switch
htpc
couch-gaming
```

`playstation-3` et `nintendo-switch` sont les deux qui portent l'angle « consoles
récentes ». `htpc` et `couch-gaming` attrapent la recherche par usage plutôt que
par technologie, qui est celle des gens qui construisent une box salon sans
savoir encore ce qu'ils vont y mettre.

---

## 4. Les cases à cocher, sous les topics

- **Releases** — cocher. C'est là qu'est l'installateur, c'est la première
  chose qu'un visiteur doit voir.
- **Packages** — décocher, il n'y en a pas.
- **Deployments** — décocher.

---

## Vérifier que ça a pris

Une fois appliqué, la balise se lit sans attendre le passage de Google :

```bash
curl -s https://github.com/p4v1c/GamecoreRenew | grep -o '<meta name="description"[^>]*>'
```

Elle doit renvoyer la nouvelle description, plus la phrase `Contribute to…`.

Pour l'indexation elle-même, compter quelques jours, et ne pas s'en inquiéter
avant deux semaines. Le site Pages sera de toute façon indexé plus vite que la
page du dépôt, parce que GitHub interdit aux crawlers `/tree/` et `/blob/` mais
pas `github.io`.
