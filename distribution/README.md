# Distribution — contenus prêts à publier

**Rien dans ce dossier n'a été publié.** Aucun compte créé, aucun post envoyé,
aucun paquet soumis, aucune PR ouverte. Tout est rédigé pour qu'un humain le
relise, décide, et l'envoie lui-même.

C'est volontaire et ça doit le rester : la moitié de ces canaux (AlternativeTo,
awesome-*, r/linux_gaming) ne pardonne pas une deuxième soumission. On n'y va
qu'une fois, et seulement quand la porte d'entrée tient.

---

## ⛔ Avant de publier quoi que ce soit — lire [`BLOQUANT-iso.md`](BLOQUANT-iso.md)

L'argument d'entrée de tous ces textes est « tu n'as pas besoin d'installer Arch
d'abord ». **Aujourd'hui c'est faux dans les faits** : le README pointe vers une
ISO que la page des releases n'a jamais portée, parce que le job `iso` de
`release.yml` échoue à chaque release depuis qu'il existe.

Envoyer du trafic maintenant, c'est envoyer des gens vers un lien de
téléchargement qui n'existe pas. Le détail, la cause exacte et le correctif
proposé sont dans [`BLOQUANT-iso.md`](BLOQUANT-iso.md).

Les textes ci-dessous sont donc écrits **vrais aujourd'hui** : ils mènent par
l'installateur graphique, qui lui est bien publié à chaque release et
fonctionne. Chaque fichier porte un encadré « si l'ISO est publiée » avec la
formulation à substituer, une fois que ce sera le cas.

---

## L'angle, identique partout

> Une box salon pour les consoles récentes — PS3, PS4, Switch, Wii U, Xbox 360 —
> avec des émulateurs toujours à jour, sur une Arch qui reste une vraie machine.

En anglais, pour les canaux internationaux :

> A living-room box for the *recent* consoles — PS3, PS4, Switch, Wii U, Xbox
> 360 — with emulators that stay current, on an Arch that stays a real computer.

**Jamais « alternative à Batocera » comme argument principal.** C'est la
comparaison en largeur : sur le nombre de systèmes supportés, sur l'âge du
projet, sur la taille de la communauté, on perd. Les trois points ci-dessous
sont les seuls terrains où la comparaison est gagnable, et ce sont ceux à tenir :

1. **Les consoles récentes d'abord.** Treize systèmes, orientés PS3/PS4/Switch/
   Wii U/Xbox 360 — pas trente systèmes 8 bits plus trois émulateurs modernes en
   bout de liste.
2. **Des émulateurs toujours à jour.** Ce sont des Flatpaks de Flathub, mis à
   jour par Flatpak. RPCS3 et Ryujinx bougent toutes les semaines ; une image
   figée les gèle jusqu'à la prochaine release de la distribution.
3. **La machine reste une vraie machine.** C'est une Arch complète avec un
   bureau Plasma derrière. `gamecore-session-select desktop` et on est sur un
   PC. Rien n'est en lecture seule, rien n'est verrouillé.

Le quatrième argument, plus discret mais c'est celui qui fait rester : **la
manette est configurée toute seule, dans tous les émulateurs**. C'est le sujet
de la vidéo, et c'est ce qui se démontre le mieux en images.

---

## Ce qu'il y a ici

| Fichier | Ce que c'est | Qui l'envoie |
|---|---|---|
| [`BLOQUANT-iso.md`](BLOQUANT-iso.md) | Le prérequis non tenu, sa cause, le correctif proposé | à traiter avant tout le reste |
| [`github-about.md`](github-about.md) | Description, topics, URL du dépôt | à coller dans les réglages GitHub |
| [`packaging/PKGBUILD`](packaging/PKGBUILD) | Paquet `gamecore-bin` pour l'AUR | **ne pas soumettre** avant lecture de [`packaging/README.md`](packaging/README.md) |
| [`video-script.md`](video-script.md) | Script d'une vidéo de 3 minutes | à tourner |
| [`submissions/alternativeto.md`](submissions/alternativeto.md) | Fiche AlternativeTo | à soumettre |
| [`submissions/awesome-emulators.md`](submissions/awesome-emulators.md) | Ligne + corps de PR pour les awesome-lists | à ouvrir en PR |
| [`submissions/reddit-emulationonlinux.md`](submissions/reddit-emulationonlinux.md) | Post r/EmulationOnLinux | à poster |
| [`submissions/reddit-linux_gaming.md`](submissions/reddit-linux_gaming.md) | Post r/linux_gaming | à poster |
| [`submissions/linuxfr.md`](submissions/linuxfr.md) | Dépêche LinuxFr (français) | à soumettre |

Le site est ailleurs, parce qu'il doit être servi par GitHub Pages :
[`../docs/index.html`](../docs/index.html). Voir [`site.md`](site.md) pour
l'activer.

---

## L'ordre de publication, et pourquoi cet ordre

Ce n'est pas une liste de courses. Chaque étape alimente la suivante, et deux
d'entre elles ne peuvent pas être défaites.

1. **Régler le bloquant ISO.** Rien ne part avant.
2. **Le About et les topics du dépôt.** Cinq minutes, réversible, et c'est ce
   que tous les autres liens vont pointer. Aujourd'hui Google n'a que
   `Contribute to p4v1c/GamecoreRenew development by creating an account on
   GitHub.` — la description par défaut de GitHub, c'est-à-dire rien.
3. **Le site Pages.** Il donne une URL propre à mettre dans le About, et un
   `<title>` et une meta description qu'on contrôle — ce que le dépôt seul ne
   permet pas. GitHub bloque le crawl de `/tree/` et `/blob/` dans son
   `robots.txt`, donc seul le README de la branche par défaut est indexable.
4. **La vidéo.** Elle doit exister avant les posts : dans cette niche elle se
   classe mieux que n'importe quelle page, et c'est elle qui crée les recherches
   sur le nom. Un post sans démo vidéo se fait demander « des captures ? » en
   premier commentaire.
5. **Les posts Reddit et LinuxFr.** Un canal par jour, pas les trois le même
   jour : poster partout en même temps se lit comme du spam, et on n'a qu'un
   seul premier post par communauté.
6. **AlternativeTo et les awesome-lists.** En dernier : ce sont des annuaires,
   ils profitent d'un projet qui a déjà des traces ailleurs, et une soumission
   refusée pour « pas assez établi » ne se retente pas facilement.

**L'AUR n'est pas dans cette liste.** Voir [`packaging/README.md`](packaging/README.md) :
le PKGBUILD est écrit et vérifié syntaxiquement, mais il n'a jamais été
construit, et publier un paquet AUR cassé est la pire première impression
possible sur ce canal précis.

---

## Ce que le nom coûte, et la seule chose à décider

« GameCore » est déjà pris plusieurs fois : un moteur de jeu Java, un IDE 3D, un
moteur Mac sur SourceForge, une chaîne YouTube, et l'utilisateur GitHub
`@GameCore`. Se battre sur ce mot est perdu d'avance — il ne rankera pas, quoi
qu'on écrive.

S'ajoute à ça que le dépôt s'appelle `GamecoreRenew` et le produit `GameCore` :
les deux se diluent, et aucun des deux n'accumule.

**Ce n'est pas à moi de trancher, et il n'y a qu'une décision à prendre :
renommer le dépôt en `GameCore`, ou pas.**

- **Renommer** : GitHub met une redirection permanente, les `git remote`
  existants continuent de fonctionner, et le nom du produit et celui du dépôt
  arrêtent de se diluer. Ça casse en revanche les URL de release déjà
  distribuées et tout ce qui pointe `GamecoreRenew` en dur — à vérifier avant.
- **Ne pas renommer** : rien ne casse, et on continue avec deux noms.

Dans les deux cas, **la stratégie SEO des textes ne change pas**, parce qu'elle
ne mise pas sur le nom : elle mise sur les requêtes longues que les gens tapent
réellement, et qui n'ont aujourd'hui presque pas de bonne réponse :

- `ps3 emulator living room tv frontend`
- `rpcs3 gamepad autoconfig`
- `switch emulator couch setup linux`
- `arch linux emulation frontend flatpak`
- `batocera alternative recent consoles`

C'est pour ça que le `<title>` du site et la description du About portent tous
les deux « living-room emulation frontend for Arch Linux » à côté du nom, et pas
seulement « GameCore ». Le nom seul n'est une requête pour personne ; la
description en est une.
