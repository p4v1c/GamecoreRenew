# Bloquant — l'ISO annoncée n'existe sur aucune release

**Constaté le 2026-08-09, sur `main` = `7a5d62d`, release la plus récente
`v1.0.155`.**

Ce document n'est pas dans le périmètre de la phase distribution. Il y est parce
que la phase distribution repose entièrement dessus, et qu'aucun des textes du
dossier ne peut être publié tant qu'il tient.

---

## Le fait

Le README dit, en tête de la section installation, et c'est l'argument d'entrée
du projet :

> Download `gamecore-<version>.iso` and `gamecore-<version>.iso.sha256` from the
> [latest release](https://github.com/p4v1c/GamecoreRenew/releases/latest).

La release `v1.0.155` porte trois fichiers :

```
gamecore-full.tar.gz    14 574 509
gamecore-installer      75 585 784
gamecore-ota.tar.gz      2 693 204
```

Pas d'ISO. Pas de `.sha256`. Pas de `.part`. **Aucune release n'en a jamais
porté** : les six dernières exécutions de `release.yml` sont toutes rouges, et
elles le sont toutes sur le job `iso`.

```
31314149020  X  Merge branch 'feat/theme-sdk-v2'      ✓ build   X iso
31311446334  X  Merge branch 'feat/per-game-config'   ✓ build   X iso
31308928950  X  Merge branch 'feat/auto-bezels'       ✓ build   X iso
31306035186  X  Merge branch 'feat/usb-devices'       ✓ build   X iso
31304637259  X  Merge branch 'build/archiso-split'    ✓ build   X iso
31304514047  X  Merge branch 'build/archiso'          ✓ build   X iso
31303042814  ✓  Merge branch 'feat/catalog-fallback'  (avant le job iso)
```

Le job `build` passe, donc la release **est publiée** avec ses trois assets, et
la boîte de production continue de se mettre à jour normalement. C'est ce qui
rend la panne discrète : rien n'est cassé sur les boîtes installées, seule la
porte d'entrée manque. Le commentaire de `release.yml` l'avait anticipé —
« la fenêtre où la dernière release n'a pas d'ISO est réelle, et visible » —
sauf que cette fenêtre est ouverte depuis la toute première tentative.

## La cause, exacte

`install/iso/build.sh:158`, la garde qui refuse de fabriquer une image dont le
shell Electron serait absent :

```
[ERROR] the Electron binary was not provisioned into node_modules — an offline
  install cannot fetch it. Re-run with npm's postinstall scripts enabled.
```

Et juste au-dessus, dans le même log :

```
npm warn install-scripts 1 package had install scripts blocked because they are
npm warn install-scripts   electron@31.7.7 (postinstall: node install.js)
```

**npm 11 ne lance plus les scripts de cycle de vie des dépendances par défaut.**
Il faut les déclarer dans `allowScripts`. Le conteneur `archlinux:latest` du job
`iso` installe npm par `pacman -Syu`, donc il a toujours le npm le plus récent —
c'est-à-dire un npm qui bloque. Le `postinstall` d'`electron` est précisément
celui qui télécharge le binaire de ~100 Mo, et sans lui `node_modules/electron/
dist/electron` n'existe pas.

La garde fait donc exactement son travail : elle refuse de produire une ISO qui
installerait une boîte sans interface. Le défaut n'est pas la garde, il est en
amont.

**Ce n'est pas une régression d'environnement passagère.** La même chose est
visible localement sur cette machine, sur le frontend, sans conséquence parce
que le build de Vite n'a pas besoin de son postinstall :

```
npm warn install-scripts   esbuild@0.21.5 (postinstall: node install.js)
```

## Le correctif proposé — non appliqué

Déclarer le script autorisé dans `electron/package.json` :

```json
{
  "name": "gamecore-electron",
  "dependencies": { "electron": "^31.0.0" },
  "allowScripts": { "electron": true }
}
```

C'est le mécanisme prévu par npm 11 pour ce cas, et il est explicite : il nomme
le seul paquet dont on veut le postinstall, plutôt que de rouvrir la vanne pour
tout l'arbre.

> **Le piège, et il rejouerait la même panne en silence.** Ne pas générer cette
> entrée avec `npm install-scripts approve electron`. Par défaut cette commande
> écrit une entrée **épinglée à la version installée** — `"electron@31.7.7":
> true`. Or `electron/package.json` dépend de `^31.0.0` : à la première montée
> de version d'Electron, l'épingle ne correspond plus, le postinstall est de
> nouveau bloqué, et l'ISO recasse exactement comme aujourd'hui — un mois plus
> tard, sans que rien n'ait été touché.
>
> Écrire l'entrée **par nom**, à la main comme ci-dessus, ou avec
> `npm install-scripts approve electron --no-allow-scripts-pin`.
>
> C'est un arbitrage assumé : une approbation par nom vaut pour toute version
> future d'`electron`, donc on fait confiance à l'amont pour ce paquet-là. Vu
> qu'il s'agit du paquet dont on installe déjà le binaire de 100 Mo comme shell
> de la boîte, la confiance est de toute façon déjà accordée.

Alternative, sans toucher `package.json` — passer le drapeau dans `build.sh` :

```bash
( cd "$SRC/electron" && npm install --allow-scripts=electron )
```

Moins bien : ça vit dans le script de build de l'ISO, donc `arch.sh` et
n'importe quel `npm install` fait à la main sur une boîte retombent dans le cas
bloqué. La déclaration dans `package.json` suit le paquet partout.

**Ce n'est pas `--foreground-scripts`** — ce drapeau-là ne change que l'affichage
des scripts qui tournent, pas l'autorisation de les lancer.

## Pourquoi je ne l'ai pas appliqué

Trois raisons, dans l'ordre d'importance.

1. **Je ne peux pas le vérifier ici.** `mkarchiso` demande Arch, root, des
   montages loop et ~25 Go de scratch. Sur cette machine, ni root ni la place.
   Le seul endroit où ce correctif se teste est le job CI lui-même — donc en
   poussant sur `main`, donc en publiant.
2. **Toucher `electron/` déclenche une release.** `release.yml` se déclenche sur
   `electron/**`. Le correctif est d'une ligne, mais il part immédiatement en
   OTA vers la boîte de production, et un `allowScripts` mal formé fait échouer
   le `npm install` du job `build` — celui qui marche aujourd'hui. On
   échangerait une ISO manquante contre une chaîne d'OTA cassée.
3. **Ce n'est pas cette phase.** C'est la livraison de P5. La phase distribution
   avait « P5 livrée » comme prérequis absolu ; le rôle de ce document est de
   dire qu'il ne l'est pas, pas de le livrer à sa place.

## Ce que ça change pour les textes du dossier

Rien n'est écrit autour de l'ISO. Tous les textes de `submissions/` et le site
mènent par **l'installateur graphique** (`gamecore-installer`), qui lui est
publié à chaque release, fait 75 Mo, et fonctionne — c'est un vrai chemin
d'installation, il demande juste une Arch déjà en place.

Chaque texte porte un encadré `> **Si l'ISO est publiée**` avec la phrase à
substituer. C'est une substitution de deux lignes par fichier, pas une
réécriture.

**Tant que le bloquant tient, deux choses sont vraies et il faut choisir en les
sachant :**

- publier maintenant fonctionne, mais l'audience est réduite aux gens qui ont
  déjà une Arch ou une Manjaro — c'est-à-dire qu'on dépense la première
  impression de r/linux_gaming sur un public dix fois plus petit ;
- ne pas publier ne coûte rien d'autre que du temps.

**Recommandation : régler le bloquant d'abord.** Il est d'une ligne, et il vaut
la différence entre « une box salon » et « une box salon si tu sais installer
Arch ».

## Et une fois l'ISO publiée — à vérifier avant de s'appuyer dessus

Le job `iso` n'a jamais réussi, donc **rien** de ce qui vient après l'étape
Electron n'a jamais tourné. Une fois le correctif passé, s'attendre à devoir en
corriger d'autres derrière, et vérifier au minimum :

- que `out/` contient bien une image et son `.sha256` ;
- que le découpage en `.part` se déclenche (l'image est annoncée au-dessus de
  2 GiB, donc c'est le chemin nominal, pas le cas rare) et que le `cat` des
  parties redonne bien une image dont le `sha256sum -c` passe ;
- que l'image démarre en UEFI avec Secure Boot désactivé.

Le README décrit tout ce parcours avec l'aplomb d'une chose observée. Elle ne
l'a jamais été.
