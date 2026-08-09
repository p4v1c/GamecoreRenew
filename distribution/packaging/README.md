# `gamecore-bin` — écrit, vérifié syntaxiquement, **pas soumis**

## Ce qui a été fait

- `PKGBUILD` et `gamecore-bin.install` rédigés.
- Syntaxe validée : `bash -n`, plus un sourcing dans un sous-shell qui vérifie
  que les variables obligatoires sont peuplées et que `package()` est définie.
  La commande exacte est en bas de ce fichier, elle est rejouable.
- `sha256sums` calculé sur l'asset réel de `v1.0.155`.

## Ce qui n'a pas été fait, et ne doit pas l'être à la légère

**`makepkg` n'a jamais été lancé.** C'était une consigne de la phase, et elle
est justifiée : `makepkg` sur cette machine télécharge, extrait et construit
sous l'utilisateur courant, et cette machine fait tourner une installation
GameCore vivante dans `/opt/GameCore`. Un `makepkg -i` y écrirait par-dessus.

Donc : **la syntaxe est vérifiée, le paquet n'est pas prouvé.** Ce sont deux
choses très différentes et il ne faut pas confondre l'une pour l'autre en
lisant ce dossier.

---

## Les deux questions ouvertes, à trancher avant l'AUR

### 1. Le paquet installe des fichiers, pas une box

L'archive `gamecore-full.tar.gz` contient le frontend **déjà construit**
(`frontend/dist/`), mais **pas** `node_modules`, et pas de venv Python — la CI
les retire (`find dist_full -name node_modules -exec rm -rf`).

Conséquence : après `pacman -U`, `/opt/GameCore` existe mais rien ne tourne. Il
faut `sudo gamecore-setup`, qui construit le venv, installe les modules Node,
et câble la machine.

C'est un choix défendable — l'installation de GameCore *est* une transformation
de la machine (auto-login SDDM, session Plasma, unités systemd, sudoers, règles
udev), et un paquet AUR n'a pas à faire ça tout seul dans un `post_install`.
Mais ça veut dire que `gamecore-bin` n'est pas un paquet « installe et joue »,
et **la description AUR devra le dire**, sinon le premier commentaire sur la
page du paquet sera « ça installe rien ».

L'alternative serait un paquet qui dépend des modules Python d'Arch
(`python-fastapi`, `python-uvicorn`, `python-evdev`…) au lieu d'un venv, et
d'`electron` au lieu d'un `npm install`. C'est plus propre du point de vue
d'Arch, et ça diverge de la façon dont le projet s'installe partout ailleurs —
donc ça crée un deuxième chemin d'installation à maintenir. **Pas tranché.**

### 2. `/usr/local/bin` contre `/usr/bin` — la collision est réelle

`install/arch.sh` copie ses outils dans `/usr/local/bin` :

```
install -m755 …/gamecore-xsetup         /usr/local/bin/gamecore-xsetup
install -m755 …/gamecore-session-select /usr/local/bin/gamecore-session-select
install -m 755 …/gamecore-addon         /usr/local/bin/gamecore-addon
```

Un paquet pacman **ne doit jamais écrire dans `/usr/local`** — c'est le
territoire de l'administrateur, et Arch l'interdit explicitement.

Le PKGBUILD ne livre donc qu'**un seul** exécutable, `/usr/bin/gamecore-setup`,
et laisse les sept autres à `arch.sh`. Si on avait livré les sept aussi, la
boîte se retrouverait avec deux copies de chacun, celle de `/usr/local/bin`
masquant celle du paquet dans le `PATH` — et une mise à jour du paquet
laisserait tourner les anciennes.

Le sudoers écrit par `arch.sh` référence en dur `/usr/local/bin/gamecore-session-select`
(ligne 1374), donc déplacer ces outils vers `/usr/bin` n'est pas une
modification d'une ligne : il faut aussi le sudoers, l'unité SDDM
(`DisplayCommand=`) et le `.desktop`. **Pas tranché non plus, et c'est le vrai
travail avant une soumission AUR.**

---

## Le versionnage, et le piège de l'asset

Chaque release s'appelle `gamecore-full.tar.gz`. **Toujours le même nom.**

Le cache de `makepkg` est indexé par nom de fichier. Sans renommage, une
construction de `1.0.155` réutiliserait le tarball de `1.0.154` déjà en cache,
sans rien retélécharger et sans rien signaler — un paquet estampillé d'une
version, contenant une autre. D'où le `::` dans `source=` :

```bash
source=("${pkgname}-${pkgver}.tar.gz::${url}/releases/download/v${pkgver}/gamecore-full.tar.gz")
```

À chaque montée de version : changer `pkgver`, remettre `pkgrel=1`, puis
`updpkgsums`. Jamais de somme recopiée à la main.

Et surtout : **le dépôt publie une release par merge sur `main`** — plus de 150
en quelques jours. Un paquet AUR ne peut pas suivre ce rythme, et un
`gamecore-bin` figé trois semaines en arrière est un paquet réputé cassé.
Si l'AUR est fait un jour, il faut d'abord une notion de release *stable*,
distincte du flux continu que la boîte consomme en OTA.

C'est la troisième raison pour laquelle rien n'est soumis.

---

## Rejouer la vérification syntaxique

Sans `makepkg`, sans réseau, sans rien construire :

```bash
cd distribution/packaging

# 1. Le fichier est-il du bash valide ?
bash -n PKGBUILD
bash -n gamecore-bin.install

# 2. Les champs obligatoires sont-ils peuplés, et package() définie ?
#    Le `bash -c` n'est pas décoratif : le shell de cette machine est zsh, et
#    sous zsh ce bloc échoue deux fois sans rien dire du PKGBUILD —
#    `options` y est un paramètre réservé (« invalid value: !debug ») et
#    `${!v}` n'est pas une indirection mais une expansion invalide.
#    Un PKGBUILD est du bash par définition : il se lit avec bash.
bash -c '
set -e
source ./PKGBUILD
for v in pkgname pkgver pkgrel pkgdesc url license arch source sha256sums; do
  [ -n "${!v}" ] || { echo "champ vide : $v"; exit 1; }
done
declare -f package >/dev/null || { echo "package() manquante"; exit 1; }
[ "${#source[@]}" -eq "${#sha256sums[@]}" ] \
  || { echo "source[] et sha256sums[] de tailles différentes"; exit 1; }
echo "PKGBUILD: champs OK — $pkgname $pkgver-$pkgrel"
'
```

Sortie obtenue au moment de la rédaction :

```
bash -n PKGBUILD: OK
bash -n .install: OK
PKGBUILD: champs OK — gamecore-bin 1.0.155-1
```

Ce que ça ne dit pas : que la construction aboutit, que l'arborescence est celle
attendue, que le paquet s'installe, ou que la boîte fonctionne après. Aucune de
ces quatre choses n'a été vérifiée.
