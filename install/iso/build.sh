#!/usr/bin/env bash
# ================================================================
#  build.sh — build the GameCore installation ISO.
#
#      sudo bash install/iso/build.sh                 # → out/gamecore-<ver>.iso
#      sudo bash install/iso/build.sh --out /tmp/iso  # somewhere else
#      sudo bash install/iso/build.sh --no-payload    # profile only, fast
#      sudo bash install/iso/build.sh --verify-only out/gamecore-*.iso
#                                                     # re-check an image
#      bash install/iso/build.sh --esp-offset <image>  # where the ESP starts
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

# ── Where the EFI system partition starts, in bytes ──────────────
#
# By OFFSET IN THE FILE, and never by a partition device node. That distinction
# is the whole of why the first version of this check could not pass on any
# image ever built.
#
# xorriso appends efiboot.img as a partition and describes it in BOTH tables:
# the GPT entry carries the EFI type GUID C12A7328-…, the MBR entry carries type
# 0xEF. But the MBR an isohybrid writes is not a PROTECTIVE MBR — there is no
# 0xEE entry, only syslinux's boot entry and the ESP — so the kernel's scanner
# takes the DOS parser, never looks at the GPT, and the partition it exposes is
# typed 0xef. Asking lsblk for the GUID therefore matched nothing, while the
# GUID sits right there in the GPT that the firmware, which does not care what
# Linux decided, reads.
#
# So: accept EITHER spelling of "this is the ESP", and read the table out of the
# file. That needs no loop device and no /dev/loopNpM, which only exists if udev
# ran — in a container it may not.
esp_offset() {  # esp_offset <image> → byte offset on stdout, or 1
  local img="$1" dump line start secsz
  # Fatal rather than "return 1": a missing tool would otherwise be reported as
  # a missing partition, which is the one sentence that sends the reader to look
  # at the profile instead of at their machine.
  command -v sfdisk >/dev/null \
    || die "sfdisk (util-linux) is not installed, so no partition table can be read."
  dump="$(sfdisk --dump "$img" 2>/dev/null)" || return 1
  # sfdisk reports in 512-byte units unless it says otherwise, and an ISO's
  # 2048-byte logical block is NOT that unit — reading the line it prints is the
  # only way not to be wrong by a factor of four.
  secsz="$(sed -n 's/^sector-size:[[:space:]]*\([0-9]\+\).*/\1/p' <<<"$dump" | head -1)"
  : "${secsz:=512}"
  line="$(grep -iE 'type=(ef|c12a7328-f81f-11d2-ba4b-00a0c93ec93b)([,[:space:]]|$)' \
          <<<"$dump" | head -1)"
  [[ -n "$line" ]] || return 1
  start="$(sed -n 's/.*start=[[:space:]]*\([0-9]\+\).*/\1/p' <<<"$line")"
  [[ -n "$start" ]] || return 1
  echo $(( start * secsz ))
}

VERIFY_ONLY=""
ESP_OFFSET_ONLY=""
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/out"
WITH_PAYLOAD=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)        OUT="${2:?--out needs a directory}"; shift 2 ;;
    --no-payload) WITH_PAYLOAD=false; shift ;;
    # Re-run the post-build check against an image that already exists. The
    # check is the kind of guard that is worth nothing until it has been seen to
    # fail, and proving that by breaking the profile and rebuilding costs eighty
    # minutes; this makes it cost seconds. It is also what to reach for when an
    # ISO someone else built will not boot.
    --verify-only) VERIFY_ONLY="${2:?--verify-only needs an .iso}"; shift 2 ;;
    # The partition-table half of that check, on its own: no root, no mounting,
    # no build. It is the one piece here that has to read a partition table, it
    # is the piece that was wrong, and this is what lets a test exercise it
    # against a fixture image in milliseconds. Also the first thing to run by
    # hand when an image will not boot a UEFI machine.
    --esp-offset) ESP_OFFSET_ONLY="${2:?--esp-offset needs an image}"; shift 2 ;;
    -h|--help)    sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            die "unknown option '$1' (try --help)" ;;
  esac
done

if [[ -n "$ESP_OFFSET_ONLY" ]]; then
  [[ -f "$ESP_OFFSET_ONLY" ]] || die "no such image: $ESP_OFFSET_ONLY"
  esp_offset "$ESP_OFFSET_ONLY" \
    || die "no EFI system partition in $(basename "$ESP_OFFSET_ONLY")."
  exit 0
fi

[[ $EUID -eq 0 ]] || die "mkarchiso needs root (it pacstraps and mounts loop devices).
  Re-run with:  sudo bash install/iso/build.sh"

# mkarchiso's work dir holds a mounted root filesystem. Leaving it behind on a
# failure leaves loop mounts and several GB; cleaning it up unconditionally is
# what keeps a second attempt from starting on top of the first.
#
# VERIFY_MNT / VERIFY_LOOP are set by verify_boot_paths. They are released here
# rather than by a nested trap because there is only one EXIT trap to have, and a
# `die` inside the verification must not leave the finished ISO attached to a
# loop device — the next build then fails on "device busy" for a reason that has
# nothing to do with the next build. The trap is armed HERE, before anything can
# claim either resource, and every variable it touches may still be empty.
WORKROOT=""; VERIFY_MNT=""; VERIFY_LOOP=""
cleanup() {
  if [[ -n "$VERIFY_MNT" ]] && mountpoint -q "$VERIFY_MNT"; then umount "$VERIFY_MNT" || true; fi
  if [[ -n "$VERIFY_LOOP" ]]; then losetup -d "$VERIFY_LOOP" 2>/dev/null || true; fi
  if [[ -n "$VERIFY_MNT" ]]; then rmdir "$VERIFY_MNT" 2>/dev/null || true; fi
  if [[ -n "$WORKROOT" ]]; then rm -rf "$WORKROOT"; fi
}
trap cleanup EXIT

# ── Prove the image can boot, before anyone burns it ─────────────
#
# This exists because an ISO that booted on NOTHING — no machine, neither
# firmware, both bootloaders — came out of a green build. Every boot entry
# named /%INSTALL_DIR%/boot/intel-ucode.img and /%INSTALL_DIR%/boot/amd-ucode.img,
# and those two files were not in the image. mkarchiso stages them only when the
# initramfs does not already carry microcode (`_check_if_initramfs_has_ucode`),
# it had decided correctly that this one did, and it says nothing about a path a
# configuration asks for and it did not produce. Nothing else does either:
# systemd-boot reports `Error preparing initrd: Not found` on the machine, and
# syslinux does not report at all — it abandons the boot and redraws its menu,
# so the countdown restarts for ever.
#
# So: resolve every path the shipped boot configurations name, against the image
# that was actually produced. A single missing one is fatal. Not a warning — a
# warning here is a release, and the failure it precedes costs someone a USB
# stick, a reboot cycle and an evening.
#
# BOTH copies are checked, and the second is the one that matters most. The
# UEFI files exist twice: in the ISO 9660 tree (read after `dd` to a stick) and
# inside efiboot.img, the FAT image xorriso appends as a second GPT partition
# (`-append_partition 2`) and which El Torito hands to the firmware — that is
# what any VM with an ISO attached reads, and it is exactly the path that failed
# here. mtools reads it without mounting anything; it is a hard dependency of
# archiso, so it is present wherever mkarchiso is.
verify_boot_paths() {  # verify_boot_paths <iso>
  local iso="$1" mnt loop esp_at conf cfg key value part
  local -a paths=() fat=() missing=()

  command -v mdir >/dev/null \
    || die "mtools is not installed, so efiboot.img cannot be inspected.
  It is a dependency of archiso, so this means something removed it:  pacman -S mtools"

  loop="$(losetup --find --show --partscan --read-only -- "$iso")" \
    || die "could not attach $iso to a loop device."
  VERIFY_LOOP="$loop"
  VERIFY_MNT="$(mktemp -d)"
  mnt="$VERIFY_MNT"
  mount -o ro "$loop" "$mnt" || die "could not mount $iso (loop $loop)."

  # ── what the configurations ask for ────────────────────────────
  #
  # systemd-boot: one path per `linux`/`initrd` line.
  # syslinux:     `LINUX`/`INITRD`, and INITRD is a COMMA-SEPARATED list — which
  #               is precisely where the two ucode images hid, inside one line.
  #
  # Both directory globs, not one file: mkarchiso stages the profile's
  # syslinux/*.cfg into /boot/syslinux/ and may generate more beside them, and a
  # config reached through INCLUDE is another .cfg in the same directory.
  shopt -s nullglob
  for conf in "$mnt"/loader/entries/*.conf; do
    while read -r key value _; do
      case "$key" in
        linux|initrd) paths+=("${conf##*/}|$value") ;;
      esac
    done < <(grep -vE '^[[:space:]]*#' "$conf")
  done
  for cfg in "$mnt"/boot/syslinux/*.cfg "$mnt"/isolinux/*.cfg "$mnt"/syslinux/*.cfg; do
    while read -r key value _; do
      case "$key" in
        LINUX|INITRD)
          local -a split=()
          IFS=, read -ra split <<<"$value"
          for part in "${split[@]}"; do paths+=("${cfg##*/}|$part"); done ;;
      esac
    done < <(grep -vE '^[[:space:]]*#' "$cfg")
  done

  (( ${#paths[@]} )) \
    || die "no boot configuration in $(basename "$iso") names a kernel or an initrd.
  Either the profile lost its loader entries and syslinux.cfg, or mkarchiso
  staged them somewhere this check does not look — both produce an unbootable
  image, so this is not something to skip past."

  # ── the FAT image the firmware actually reads ──────────────────
  esp_at="$(esp_offset "$iso")" \
    || die "no EFI system partition in $(basename "$iso").
  xorriso appends efiboot.img as a partition of its own; without it the image
  cannot be booted by any UEFI machine, VM included.
  What the tables actually say:

$(sfdisk --dump "$iso" 2>&1 | sed 's/^/    /')"
  # -b prints one full path per line ("::/EFI/BOOT/BOOTx64.EFI"), -/ recurses.
  mapfile -t fat < <(mdir -i "${iso}@@${esp_at}" -b -/ ::/ 2>/dev/null | sed 's|^::||; s|/$||')
  # A listing that came back empty is a tool problem, not a missing file, and
  # reporting it as "everything is missing" would send the next reader hunting
  # in the profile. /EFI is always at the root of efiboot.img.
  printf '%s\n' "${fat[@]}" | grep -qixF '/EFI' \
    || die "could not read the ESP at byte $esp_at (${#fat[@]} entries came back).
  This is mtools failing to list the FAT image, not the profile — check that
  'mdir -i ${iso}@@${esp_at} -b -/ ::/' works before believing anything below it."

  # ── resolve ────────────────────────────────────────────────────
  local ref name path
  for ref in "${paths[@]}"; do
    name="${ref%%|*}"; path="${ref#*|}"
    [[ -e "$mnt$path" ]] || missing+=("$name asks for $path — not in the ISO 9660 tree")
    # syslinux runs before any of this exists; only the UEFI side is in the FAT.
    if [[ "$name" == *.conf ]]; then
      printf '%s\n' "${fat[@]}" | grep -qixF -- "$path" \
        || missing+=("$name asks for $path — not in efiboot.img")
    fi
  done

  if (( ${#missing[@]} )); then
    die "the ISO references files it does not contain:

$(printf '  · %s\n' "${missing[@]}")

  Nothing will boot this image, and neither bootloader will say why: systemd-boot
  stops with 'Error preparing initrd: Not found', syslinux silently returns to
  its own menu and counts down again.

  If these are the microcode images: they are not staged separately any more.
  mkarchiso only copies intel-ucode.img/amd-ucode.img beside the kernel when the
  initramfs does NOT already contain microcode, and the profile puts it inside
  via mkinitcpio's 'microcode' hook. The fix is to remove the ucode lines from
  the boot configuration, not to put the files back."
  fi

  ok "${#paths[@]} referenced boot paths resolve, in the ISO 9660 tree and in efiboot.img"

  # Released here rather than left to the EXIT trap, so a second image in $OUT
  # starts from a clean slate. Tolerant on purpose: a mount that will not release
  # must not turn a verification that PASSED into a failed build, and the trap
  # still holds both references if anything below does not take.
  if umount "$mnt" && losetup -d "$loop"; then
    rmdir "$mnt" 2>/dev/null || true
    VERIFY_MNT=""; VERIFY_LOOP=""
  else
    warn "could not release $loop / $mnt here — the EXIT trap will retry."
  fi
}

if [[ -n "$VERIFY_ONLY" ]]; then
  [[ -f "$VERIFY_ONLY" ]] || die "no such image: $VERIFY_ONLY"
  msg "Verifying $(basename "$VERIFY_ONLY")"
  verify_boot_paths "$VERIFY_ONLY"
  exit 0
fi

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


msg "Verifying the boot paths"
shopt -s nullglob
for iso in "$OUT"/*.iso; do verify_boot_paths "$iso"; done

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
