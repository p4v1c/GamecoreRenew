# Installer Jelly

Le thème est un dossier `jelly/` de fichiers simples : rien à compiler, rien à
installer avec npm, aucun changement du backend. Il demande une version de
GameCore qui fournit le SDK de thèmes 9 (celle de la branche où il a été
écrit). Sur une version plus ancienne, il apparaît dans Réglages → Thèmes comme
« non sélectionnable », avec la raison, et rien d'autre ne change.

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

- Les favoris (★) sont gardés dans le navigateur de la box, sous la clé
  `jelly-favourites`. Ils ne suivent pas d'une box à l'autre.
- Les réglages, l'alimentation, l'écran manette et le menu de session sont ceux
  de GameCore, habillés en Jelly : leurs textes restent ceux de l'hôte
  (en anglais).
- Si cette branche est un jour fusionnée dans `main`, Jelly sera livré à toutes
  les box avec la mise à jour OTA, comme Orbit et Shelf.
