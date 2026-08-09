#!/usr/bin/env bash
# ================================================================
#  build.sh — build the GameCore installation ISO.
#
#      sudo bash install/iso/build.sh                 # → out/gamecore-<ver>.iso
#      sudo bash install/iso/build.sh --out /tmp/iso  # somewhere else
#      sudo bash install/iso/build.sh --no-payload    # profile only, fast
#
#  ── Where to run this ───────────────────────────────────────────
#
#  On Arch or in an `archlinux` container, as root, on a machine you do not
#  mind. mkarchiso needs root because it pacstraps a root filesystem and mounts
#  loop devices; it also writes several GB and pulls the whole package set.
#  It is NOT a thing to run on the box that plays the games, and it is not a
#  thing to run on a development laptop by accident — hence the guards below.
#
#  ── Why the profile is copied before building ───────────────────
#
#  mkarchiso wants the payload inside the profile's airootfs/, and the payload
#  is ~2 GB of node_modules, Python wheels and a copy of the GameCore tree.
#  Staging that into install/iso/airootfs/ would put two gigabytes of build
#  output inside the git working tree, where the next `git status` is unusable
#  and the next `git clean -fdx` is a surprise. So the profile is copied to a
#  scratch directory, the payload is staged into the COPY, and the repository is
#  never written to.
# ================================================================
set -euo pipefail

RED='\033[1;31m'; GRN='\033[1;32m'; YLW='\033[1;33m'; BLU='\033[1;34m'; RST='\033[0m'
msg()  { echo -e "\n${BLU}──────────────────────────────────────${RST}\n${GRN}  $*${RST}"; }
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YLW}⚠  $*${RST}"; }
die()  { echo -e "\n${RED}[ERROR]${RST} $*" >&2; exit 1; }
info() { echo -e "  ${RST}$*"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/out"
WITH_PAYLOAD=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)        OUT="${2:?--out needs a directory}"; shift 2 ;;
    --no-payload) WITH_PAYLOAD=false; shift ;;
    -h|--help)    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            die "unknown option '$1' (try --help)" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "mkarchiso needs root (it pacstraps and mounts loop devices).
  Re-run with:  sudo bash install/iso/build.sh"

command -v mkarchiso >/dev/null \
  || die "mkarchiso not found — install the 'archiso' package (Arch only).
  In a container:  docker run --rm --privileged -v \"\$PWD\":/repo archlinux:latest \\
                     bash -c 'pacman -Sy --noconfirm archiso git npm && bash /repo/install/iso/build.sh'"

# The ISO version, and the same string the release workflow passes. Read here as
# well as in profiledef.sh so the filename and the volume metadata agree.
GAMECORE_ISO_VERSION="${GAMECORE_ISO_VERSION:-$(cat "$REPO/VERSION" 2>/dev/null || date +%Y.%m.%d)}"
GAMECORE_ISO_VERSION="${GAMECORE_ISO_VERSION#v}"
export GAMECORE_ISO_VERSION

# Where the uncompressed root filesystem is assembled. It is BIG — the whole
# package set unpacked, plus the squashfs being written next to it, comfortably
# past 20 GB. /var/tmp by default; overridable because a CI runner keeps its
# space on a different mount than the one / lives on, and mkarchiso failing
# halfway through for lack of room looks nothing like a disk-space problem.
SCRATCH="${GAMECORE_ISO_SCRATCH:-/var/tmp}"
mkdir -p "$SCRATCH"
# `-BG` and not `-P --output=avail`: coreutils refuses those two together, and
# the failure is a usage error on stderr with an empty capture — so the check
# would compare "" against 25 and abort the build under `set -e`.
AVAIL_GB=$(df -BG "$SCRATCH" | awk 'NR==2 {gsub(/G/,"",$4); print $4+0}')
[[ "$AVAIL_GB" -ge 25 ]] \
  || warn "only ${AVAIL_GB} GB free in $SCRATCH — mkarchiso needs about 25 GB."
WORKROOT="$(mktemp -d "$SCRATCH/gamecore-iso.XXXXXX")"
PROFILE="$WORKROOT/profile"
# mkarchiso's work dir holds a mounted root filesystem. Leaving it behind on a
# failure leaves loop mounts and several GB; cleaning it up unconditionally is
# what keeps a second attempt from starting on top of the first.
cleanup() { rm -rf "$WORKROOT"; }
trap cleanup EXIT

msg "GameCore ISO $GAMECORE_ISO_VERSION"
info "Repository : $REPO"
info "Scratch    : $WORKROOT"
info "Output     : $OUT"

cp -a "$HERE" "$PROFILE"
# A previous --out inside the repo, or someone's manual experiment. The profile
# copy must be exactly what is committed.
rm -rf "$PROFILE/work" "$PROFILE/out"

# ── Stage the offline payload ────────────────────────────────────
PAYLOAD="$PROFILE/airootfs/usr/share/gamecore"
SRC="$PAYLOAD/src"

if $WITH_PAYLOAD; then
  msg "Staging the GameCore payload"
  mkdir -p "$SRC"

  # The same exclusions the release workflow uses for gamecore-full.tar.gz, plus
  # the build outputs we are about to regenerate. node_modules is excluded HERE
  # and rebuilt below on purpose: whatever is in the developer's checkout was
  # built against their Node, and the ISO's Node is the one in packages.x86_64.
  tar -C "$REPO" \
    --exclude='./.git' \
    --exclude='./.venv' \
    --exclude='./out' \
    --exclude='./node_modules' \
    --exclude='./frontend/node_modules' \
    --exclude='./electron/node_modules' \
    --exclude='./__pycache__' \
    --exclude='*.pyc' \
    -cf - . | tar -C "$SRC" -xf -
  ok "GameCore tree → /usr/share/gamecore/src"

  # ── The three things an offline install cannot download ────────
  #
  # Everything else the target needs is a pacman package and is already in the
  # squashfs (see packages.x86_64). These three are not, and each one of them is
  # a hard stop for `arch.sh` on a machine with no cable in it.

  # 1. Python dependencies, as wheels.
  #
  # ABI WARNING, and it is the sharpest edge in this file: evdev, argon2-cffi,
  # cryptography and uvicorn's httptools/uvloop are C extensions, so these
  # wheels are only usable by the exact CPython minor version that built them.
  # That is safe here for one reason — mkarchiso pacstraps the ISO's `python`
  # from the same repositories, at the same moment, as the interpreter running
  # this line. Build the ISO on Arch (or in an archlinux container) and they
  # match. Build it anywhere else and mkarchiso refuses long before this.
  msg "Python wheels for the offline install"
  mkdir -p "$PAYLOAD/wheels"
  command -v pip >/dev/null || pacman -S --noconfirm --needed python-pip
  pip wheel --no-cache-dir -r "$REPO/backend/requirements.txt" -w "$PAYLOAD/wheels" \
    || die "could not build the Python wheelhouse — an offline install would have no backend."
  ok "$(find "$PAYLOAD/wheels" -name '*.whl' | wc -l) wheels → /usr/share/gamecore/wheels"

  # 2 & 3. node_modules for the frontend and for Electron, prebuilt, plus the
  # frontend's dist/. `npm ci` needs the registry and `electron` downloads a
  # ~100 MB binary from GitHub in its postinstall — neither is available on the
  # machine being installed.
  msg "Node modules and the frontend build"
  command -v npm >/dev/null || die "npm not found — install 'npm' (nodejs) on the build host."

  # Checked HERE, before ~40 minutes of pacstrap and squashfs, because the
  # symptom otherwise arrives at the Electron guard below and is indistinguishable
  # from the npm-policy failure that guard was written for.
  #
  # Electron 31's postinstall unpacks with extract-zip 2.0.1 / yauzl 2.10, and on
  # Node 26 that unpack stalls without ever settling its promise: node exits 0
  # having written dist/locales and nothing else. Silent, and it looks like a
  # successful install right up to the guard.
  #
  # Measured: Node 22.21 unpacks the 260 MB tree, Node 26.4 writes 352 KB and no
  # binary. 23/24/25 were NOT tested — the ceiling below is the last version
  # known to work, not the first known to break. Raise it with a measurement.
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [[ "$NODE_MAJOR" -ge 18 && "$NODE_MAJOR" -le 22 ]] \
    || die "this build host runs Node $NODE_MAJOR; the payload must be staged with Node 18-22.
  Electron 31's postinstall silently extracts nothing on Node 26, and the ISO
  would be built with no Electron binary in it.
  On Arch:  pacman -S nodejs-lts-jod   (the release workflow does the same)"
  info "node $(node --version), npm $(npm --version)"
  ( cd "$SRC/frontend" && npm ci && npm run build ) \
    || die "the frontend build failed — the ISO would install a box with no UI."
  ok "frontend/node_modules + frontend/dist staged"

  ( cd "$SRC/electron" && npm install ) \
    || die "electron npm install failed — the ISO would install a box with no shell."
  # The postinstall that fetches the binary is skipped by hardened npm setups,
  # and arch.sh's fallback for that is a download. On the target there is no
  # download, so a missing binary has to be caught HERE, where the network
  # still exists.
  #
  # Two distinct causes reach this line, and they read identically — which is
  # why they are both named. The first one kept the `iso` job red from the day
  # it was added (v1.0.150 through v1.0.152) until it was traced:
  #   1. npm >= 11.6 blocks a dependency's install scripts unless package.json
  #      declares it under `allowScripts`. electron/package.json declares it;
  #      if that entry is dropped, npm warns and moves on and the binary never
  #      downloads. Grep the log for "install-scripts" to confirm.
  #   2. Node 26 extracts nothing (see the version check above).
  [[ -x "$SRC/electron/node_modules/electron/dist/electron" ]] \
    || die "the Electron binary was not provisioned into node_modules — an offline
  install cannot fetch it. Two things produce this:
    - npm blocked electron's postinstall  → check for 'install-scripts' warnings
      in the log above, and for the allowScripts entry in electron/package.json;
    - the postinstall ran but extracted nothing → check the Node version."
  ok "electron/node_modules staged (binary present)"

  # The marker arch.sh looks for. A directory that merely exists is not proof of
  # anything; this file is written last, after every step above succeeded, so
  # its presence means the payload is complete rather than half-staged.
  cat > "$PAYLOAD/OFFLINE_READY" <<MARK
# Written by install/iso/build.sh once every offline artefact was staged.
# install/arch.sh reads this to decide it may install without a network.
version=$GAMECORE_ISO_VERSION
MARK
  ok "payload marked complete"
else
  warn "--no-payload: the ISO will boot and partition, but the installer will"
  warn "  refuse at the first step with 'no GameCore payload'. Profile testing only."
fi

# ── Build ────────────────────────────────────────────────────────
msg "mkarchiso (this takes a while and needs several GB)"
mkdir -p "$OUT"
mkarchiso -v -w "$WORKROOT/work" -o "$OUT" "$PROFILE"

# ── Checksum ─────────────────────────────────────────────────────
# Beside the image and with a bare filename inside it, so that
# `sha256sum -c gamecore-*.iso.sha256` works in the directory someone downloaded
# both files into — an absolute path from the build machine would make the
# check fail for every user.
msg "Checksums"
shopt -s nullglob
for iso in "$OUT"/*.iso; do
  ( cd "$OUT" && sha256sum "$(basename "$iso")" > "$(basename "$iso").sha256" )
  ok "$(basename "$iso") ($(du -h "$iso" | cut -f1))"
  ok "$(basename "$iso").sha256"
done

msg "Done"
info "Write it to a USB stick with:"
info "  sudo dd if=$OUT/gamecore-*.iso of=/dev/sdX bs=4M status=progress oflag=sync"
info "Then boot the target machine from it — UEFI, with Secure Boot disabled."
