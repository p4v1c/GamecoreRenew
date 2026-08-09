# `gamecore-bin` — written, syntax-checked, **not submitted**

## What was done

- `PKGBUILD` and `gamecore-bin.install` written.
- Syntax validated: `bash -n`, plus a sourcing in a subshell that checks the
  mandatory variables are populated and that `package()` is defined. The exact
  command is at the bottom of this file; it is replayable.
- `sha256sums` computed against the real asset of `v1.0.155`.

## What was not done, and must not be done lightly

**`makepkg` has never been run.** That was a phase instruction, and it is
justified: `makepkg` on this machine downloads, extracts and builds as the current
user, and this machine runs a live GameCore installation in `/opt/GameCore`. A
`makepkg -i` would write over it.

So: **the syntax is checked, the package is not proven.** Those are two very
different things and one must not be mistaken for the other when reading this
folder.

---

## The two open questions, to settle before the AUR

### 1. The package installs files, not a box

The `gamecore-full.tar.gz` archive contains the frontend **already built**
(`frontend/dist/`), but **not** `node_modules`, and no Python venv — CI strips
them (`find dist_full -name node_modules -exec rm -rf`).

Consequence: after `pacman -U`, `/opt/GameCore` exists but nothing runs. You need
`sudo gamecore-setup`, which builds the venv, installs the Node modules, and
wires the machine up.

That is a defensible choice — installing GameCore *is* a transformation of the
machine (SDDM auto-login, Plasma session, systemd units, sudoers, udev rules),
and an AUR package has no business doing that on its own in a `post_install`. But
it means `gamecore-bin` is not an "install and play" package, and **the AUR
description will have to say so**, otherwise the first comment on the package page
will be "this installs nothing".

The alternative would be a package depending on Arch's Python modules
(`python-fastapi`, `python-uvicorn`, `python-evdev`…) instead of a venv, and on
`electron` instead of an `npm install`. That is cleaner from Arch's point of
view, and it diverges from how the project installs everywhere else — so it
creates a second installation path to maintain. **Not settled.**

### 2. `/usr/local/bin` versus `/usr/bin` — the collision is real

`install/arch.sh` copies its tools into `/usr/local/bin`:

```
install -m755 …/gamecore-xsetup         /usr/local/bin/gamecore-xsetup
install -m755 …/gamecore-session-select /usr/local/bin/gamecore-session-select
install -m 755 …/gamecore-addon         /usr/local/bin/gamecore-addon
```

A pacman package **must never write into `/usr/local`** — that is the
administrator's territory, and Arch forbids it explicitly.

So the PKGBUILD ships exactly **one** executable, `/usr/bin/gamecore-setup`, and
leaves the other seven to `arch.sh`. Had we shipped all seven too, the box would
end up with two copies of each, the `/usr/local/bin` one shadowing the package's
one in `PATH` — and a package upgrade would leave the old ones running.

The sudoers file written by `arch.sh` hardcodes
`/usr/local/bin/gamecore-session-select` (line 1374), so moving these tools to
`/usr/bin` is not a one-line change: the sudoers, the SDDM unit
(`DisplayCommand=`) and the `.desktop` all have to follow. **Not settled either,
and this is the real work before an AUR submission.**

---

## Versioning, and the asset trap

Every release is called `gamecore-full.tar.gz`. **Always the same name.**

`makepkg`'s cache is indexed by file name. Without a rename, a build of `1.0.155`
would reuse the already-cached `1.0.154` tarball, downloading nothing and
reporting nothing — a package stamped with one version, containing another. Hence
the `::` in `source=`:

```bash
source=("${pkgname}-${pkgver}.tar.gz::${url}/releases/download/v${pkgver}/gamecore-full.tar.gz")
```

On every version bump: change `pkgver`, reset `pkgrel=1`, then `updpkgsums`.
Never a sum copied by hand.

And above all: **the repo publishes one release per merge to `main`** — more than
150 in a few days. An AUR package cannot follow that pace, and a `gamecore-bin`
frozen three weeks back is a package with a reputation for being broken. If the
AUR ever happens, it needs a notion of a *stable* release first, distinct from
the continuous stream the box consumes over OTA.

That is the third reason nothing has been submitted.

---

## Replaying the syntax check

No `makepkg`, no network, nothing built:

```bash
cd distribution/packaging

# 1. Is the file valid bash?
bash -n PKGBUILD
bash -n gamecore-bin.install

# 2. Are the mandatory fields populated, and package() defined?
#    The `bash -c` is not decorative: this machine's shell is zsh, and under zsh
#    this block fails twice without saying anything about the PKGBUILD —
#    `options` is a reserved parameter there ("invalid value: !debug") and
#    `${!v}` is not an indirection but an invalid expansion.
#    A PKGBUILD is bash by definition: read it with bash.
bash -c '
set -e
source ./PKGBUILD
for v in pkgname pkgver pkgrel pkgdesc url license arch source sha256sums; do
  [ -n "${!v}" ] || { echo "empty field: $v"; exit 1; }
done
declare -f package >/dev/null || { echo "package() missing"; exit 1; }
[ "${#source[@]}" -eq "${#sha256sums[@]}" ] \
  || { echo "source[] and sha256sums[] have different sizes"; exit 1; }
echo "PKGBUILD: fields OK — $pkgname $pkgver-$pkgrel"
'
```

Output obtained at the time of writing:

```
bash -n PKGBUILD: OK
bash -n .install: OK
PKGBUILD: fields OK — gamecore-bin 1.0.155-1
```

What that does not say: that the build succeeds, that the tree is the expected
one, that the package installs, or that the box works afterwards. None of those
four has been verified.

## Running `shellcheck` on this file means nothing

The PKGBUILD is not in the repo's baseline, which only analyses
`git ls-files '*.sh'` and `install/bin/*`. That is correct, and it must not be
added: pointed at a PKGBUILD, `shellcheck` produces guaranteed noise, because it
does not know `makepkg`'s contract.

```
SC2148  Tips depend on target shell and yours is unknown  (a PKGBUILD has no shebang)
SC2034  pkgrel appears unused                             (makepkg reads it, not the script)
SC2034  pkgdesc appears unused                            (same)
SC2034  arch appears unused                               (same)
```

Those four are expected and repeat on any valid PKGBUILD. Silencing them with
`# shellcheck disable=` directives would only make the file less readable in order
to suppress a warning nobody asked for. `bash -n` plus the field check above is
the right granularity here.
