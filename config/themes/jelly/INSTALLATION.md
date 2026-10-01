# Installer Jelly

Le thème est un dossier `jelly/` de fichiers simples : rien à compiler, rien à
installer avec npm. Il demande une version de
GameCore qui fournit le SDK de thèmes 9 (celle de la branche où il a été
écrit). Sur une version plus ancienne, il apparaît dans Réglages → Thèmes comme
« non sélectionnable », avec la raison, et rien d'autre ne change.

**Photos des consoles.** Elles ne sont plus dans le thème mais dans chaque
pack (`catalog/<id>/art/console.webp`), servies par le backend de cette même
branche. Sur une box qui tourne encore `main`, Jelly marche mais affiche le
logo ou le sigle de chaque console à la place de la photo : mettre la box à jour
avec cette branche les fait apparaître. Pour changer une photo sur la box sans
toucher au dépôt : déposer `assets/art/<id>/console.png` (exemple :
`assets/art/azahar/console.png`), elle passe devant celle du pack et les mises
à jour ne l'écrasent pas.

## Option A : déposer le dossier

1. Copier le dossier `jelly` dans `config/themes/` de la box
   (par défaut `/opt/GameCore/config/themes/jelly`), par SSH ou par l'addon
   rom-manager depuis un navigateur du réseau local.
2. Sur la box : **Options → Réglages → Thèmes → Jelly**, puis ✕.
   L'interface redémarre dans Jelly.

## Option B : l'outil de la box (vérifie avant de copier)

```bash
gamecore-theme verify jelly-theme.zip    # vérifie, n'installe rien
gamecore-theme install jelly-theme.zip   # vérifie puis met en place
gamecore-theme list                      # Jelly doit apparaître
```

Puis **Réglages → Thèmes → Jelly**. Ces trois commandes ont été lancées sur
une copie de test de la box (`GAMECORE_DATA` temporaire) : `verify` répond
« 'jelly' is a valid theme. », `install` le place dans `config/themes/jelly`.

## Revenir en arrière

- **Réglages → Thèmes** : choisir un autre thème (Orbit, Shelf, Summer, ou le
  thème par défaut).
- Si l'écran ne répond plus : **maintenir L1 + R1 pendant 2 secondes**, partout,
  remet le thème par défaut.
- Désinstaller : `gamecore-theme remove jelly` (il est désélectionné avant
  d'être supprimé). Une réinstallation garde la copie précédente dans
  `config/themes/.prev/jelly/`.

## Bon à savoir

- Les cartes de jeux utilisent la box 3D quand GameCore en a une pour le jeu
  (il faut une source média configurée : compte ScreenScraper ou index hors
  ligne). Le bouton « Boîtes 3D / Jaquettes à plat » dans Collection et dans
  chaque console change pour tous les jeux.
- Les favoris (★) sont gardés dans le navigateur de la box, sous la clé
  `jelly-favourites`. Ils ne suivent pas d'une box à l'autre.
- Les réglages, l'alimentation, l'écran manette et le menu de session sont ceux
  de GameCore, habillés en Jelly : leurs textes restent ceux de l'hôte
  (en anglais).
- Si cette branche est un jour fusionnée dans `main`, Jelly sera livré à toutes
  les box avec la mise à jour OTA, comme Orbit et Shelf.
