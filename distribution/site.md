# Le site — activer GitHub Pages depuis `docs/`

Le site est [`../docs/index.html`](../docs/index.html), avec
[`../docs/robots.txt`](../docs/robots.txt),
[`../docs/sitemap.xml`](../docs/sitemap.xml) et
[`../docs/.nojekyll`](../docs/.nojekyll).

**Il n'est pas encore servi.** Activer Pages est une action côté GitHub, donc
elle revient à l'humain.

---

## Pourquoi un site alors qu'il y a un README

Trois choses que le dépôt seul ne permet pas, et elles sont toute la raison
d'être de cette page :

1. **Le `<title>`.** Celui de la page GitHub est imposé : `GitHub -
   p4v1c/GamecoreRenew`. C'est le texte bleu cliquable dans les résultats de
   recherche, et c'est le facteur le plus lourd de tout le référencement d'une
   page. Ici il vaut :
   `GameCore — living-room emulation frontend for Arch Linux (PS3, PS4, Switch, Wii U)`.
2. **La meta description.** Sur GitHub c'est `Contribute to p4v1c/GamecoreRenew
   development by creating an account on GitHub.` tant qu'aucun About n'est
   renseigné — et même une fois le About rempli, c'est GitHub qui décide de sa
   mise en forme.
3. **L'indexation elle-même.** Le `robots.txt` de GitHub interdit aux crawlers
   `/tree/` et `/blob/`. Seul le README de la branche par défaut est indexable :
   toute la documentation du dépôt est invisible pour un moteur de recherche.
   `github.io` n'a pas cette restriction.

## Activer

1. `https://github.com/p4v1c/GamecoreRenew` → **Settings** → **Pages**
   (barre latérale gauche).
2. **Source** : `Deploy from a branch`.
3. **Branch** : `main`, dossier **`/docs`**. Save.
4. Attendre une à deux minutes, puis vérifier
   `https://p4v1c.github.io/GamecoreRenew/`.
5. **Ensuite seulement**, coller cette URL dans le champ Website du About
   (voir [`github-about.md`](github-about.md)). Un champ Website qui renvoie 404
   est suivi par les crawlers, donc pire que vide.

## Vérifier que les balises sont bien celles-là

```bash
curl -s https://p4v1c.github.io/GamecoreRenew/ | grep -E '<title>|name="description"'
```

## Accélérer l'indexation

Optionnel, et c'est le seul levier qui fait passer de « quelques semaines » à
« quelques jours » : déclarer le site dans
[Google Search Console](https://search.google.com/search-console) (propriété par
préfixe d'URL, validation par balise HTML ou par DNS), puis y soumettre
`sitemap.xml`.

**À faire par l'humain** : ça demande un compte Google et ça publie une
propriété.

---

## Ce que ça expose, et ce que ça n'expose pas

Activer Pages sur `/docs` sert **tout** le contenu de `docs/` sur le web, pas
seulement `index.html` : `SECURITY.md`, `TESTING.md`, `CONTROLLER_MODELS.md`,
`architecture/`, `themes/`.

Ces fichiers sont déjà publics — le dépôt l'est — donc ça n'expose rien de
nouveau. La différence est qu'ils deviennent **indexables**, ce qu'ils n'étaient
pas derrière le `robots.txt` de GitHub.

Deux conséquences, et une seule mérite une action :

- `sitemap.xml` ne déclare que `index.html`. Les `.md` ne sont pas soumis à
  l'indexation : servis en texte brut, ils s'affichent comme un fichier
  téléchargé, et quelqu'un qui atterrirait dessus depuis Google verrait du
  Markdown nu plutôt qu'une page. Ils restent atteignables par leur URL directe,
  ce qui est le comportement voulu.
- **`docs/SECURITY.md` devient une page indexable décrivant le modèle de sécurité
  du produit.** Ce n'est pas un secret et publier son modèle de sécurité est une
  bonne pratique — mais c'est le seul fichier du lot qui vaut une relecture
  volontaire avant d'appuyer sur Save, parce que c'est le seul dont l'audience
  changerait de nature. **À relire par le propriétaire.** Je ne l'ai pas fait :
  juger ce qui est publiable dans le modèle de sécurité de sa propre machine
  n'est pas une décision qui se délègue.

## Si l'ISO est publiée

Deux endroits dans `docs/index.html`, et c'est tout :

- la section **Installing it** : ajouter l'ISO comme premier chemin, avant
  l'installateur graphique ;
- le bouton principal de l'en-tête : `Download the installer` devient
  `Download the ISO`, en gardant l'installateur en bouton secondaire.

C'est le meilleur moment pour ajouter aussi la capture `og:image` — le
commentaire dans `<head>` indique où et sous quelles contraintes.
