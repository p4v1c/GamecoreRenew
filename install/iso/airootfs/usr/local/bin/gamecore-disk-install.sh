#!/usr/bin/env bash
# ================================================================
#  gamecore-disk-install.sh — put GameCore on a bare machine.
#
#  Runs ONLY from the GameCore live ISO. It repartitions a whole disk, and
#  everything on that disk is gone.
#
#      gamecore-disk-install.sh --list-disks
#      gamecore-disk-install.sh --dry-run  /path/to/gamecore-install.conf
#      gamecore-disk-install.sh --yes      /path/to/gamecore-install.conf
#
#  ── What it does NOT do, and why ────────────────────────────────
#
#  It does not run install/arch.sh. arch.sh assumes a running systemd — it does
#  `systemctl enable --now sshd`, `systemctl enable --now cpupower.service` and
#  half a dozen more, none of them guarded, and inside `arch-chroot` there is no
#  systemd to talk to: the first one fails, `set -e` fires, and the install dies
#  two thirds of the way through with a partitioned disk and no bootloader.
#
#  So the disk install stops at "a bootable Arch with the GameCore payload on
#  it", writes the answers to /etc/gamecore-install.conf, and arms
#  gamecore-firstboot.service. arch.sh then runs on the installed machine, on
#  the first boot, with a real systemd and real hardware under it — which is the
#  path it was written for and the only one that is tested.
#
#  ── The layout ──────────────────────────────────────────────────
#
#      p1  1 GiB   ESP, FAT32, mounted /boot   (kernel + initramfs live here)
#      p2  ROOT_SIZE  ext4 or btrfs, mounted /
#      p3  the rest   btrfs, mounted /userdata → GAMECORE_DATA
#
#  UEFI only. See the firmware check below for why that is not laziness.
# ================================================================
set -euo pipefail

RED='\033[1;31m'; GRN='\033[1;32m'; YLW='\033[1;33m'; BLU='\033[1;34m'; RST='\033[0m'
msg()  { echo -e "\n${BLU}──────────────────────────────────────${RST}\n${GRN}  $*${RST}"; }
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YLW}⚠  $*${RST}"; }
die()  { echo -e "\n${RED}[ERROR]${RST} $*" >&2; exit 1; }
info() { echo -e "  ${RST}$*"; }

DRY_RUN=false
ASSUME_YES=false
CONF=""

usage() {
  sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list-disks) LIST_ONLY=true; shift ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --yes|-y)     ASSUME_YES=true; shift ;;
    -h|--help)    usage 0 ;;
    -*)           die "unknown option '$1' (try --help)" ;;
    *)            CONF="$1"; shift ;;
  esac
done

# `run` is what makes --dry-run meaningful rather than decorative: every command
# that changes the machine goes through it, so the dry run prints the exact
# sequence that would be executed. Anything bypassing it is a bug.
run() {
  if $DRY_RUN; then
    printf '    [dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

# ── Guard: this only ever runs on the live ISO ───────────────────
#
# The single most important check in this file. The script lives in a git
# repository that people edit on their own workstations, and it takes a disk
# and erases it. /run/archiso is created by the archiso initramfs hook and
# exists on a booted GameCore ISO and nowhere else — not in a container, not in
# a checkout, not on the box it just installed.
#
# It is checked BEFORE the argument-less paths (--help excepted, above) on
# purpose: `bash gamecore-disk-install.sh` typed by mistake in a terminal must
# refuse on the first line it reaches, not after it has read a config file.
[[ -d /run/archiso ]] || die "not running from the GameCore live ISO — refusing.
  This script repartitions a whole disk and is only ever correct on the ISO.
  (It looks for /run/archiso, which the live medium's initramfs creates.)"

[[ $EUID -eq 0 ]] || die "run me as root."

list_disks() {
  msg "Disks on this machine"
  # -d: whole disks only. A partition cannot be a target here, and offering one
  # in the list is how someone picks /dev/sda1 and loses /dev/sda.
  lsblk -d -o NAME,SIZE,TYPE,MODEL,TRAN | grep -Ev '^loop|^sr' || true
  echo
  info "Put the one you want in TARGET_DISK= in the install conf."
}

if [[ "${LIST_ONLY:-false}" == true ]]; then
  list_disks
  exit 0
fi

[[ -n "$CONF" ]] || { list_disks; die "no conf file given (try --help)."; }
[[ -f "$CONF" ]] || die "conf file '$CONF' does not exist."

# ── The answers ──────────────────────────────────────────────────
# Same file arch.sh --unattended reads, with the disk keys added. One file, so
# there is never a second place where the username is written down and disagrees.
# shellcheck disable=SC1090
source "$CONF"

TARGET_DISK="${TARGET_DISK:-}"
[[ -n "$TARGET_DISK" ]] || { list_disks; die "TARGET_DISK is not set in $CONF."; }

ESP_SIZE="${ESP_SIZE:-1G}"
# 60 GiB of root. The emulators are Flatpaks and Flatpak puts them in
# /var/lib/flatpak, which is on the ROOT partition, not in /userdata — thirteen
# emulators plus a KDE runtime is comfortably over 30 GiB, and a root that fills
# up mid-install is the failure this default exists to avoid.
ROOT_SIZE="${ROOT_SIZE:-60G}"
ROOT_FS="${ROOT_FS:-ext4}"
# btrfs for the data partition, matching what provision_userdata() in arch.sh
# reaches for: it is the filesystem that lets saves be snapshotted separately
# from the system.
USERDATA_FS="${USERDATA_FS:-btrfs}"
TARGET_HOSTNAME="${TARGET_HOSTNAME:-gamecore}"
TIMEZONE="${TIMEZONE:-UTC}"
LOCALE="${LOCALE:-en_US.UTF-8}"
KEYMAP="${KEYMAP:-us}"
ROOT_PASSWORD="${ROOT_PASSWORD:-}"
USER_PASSWORD="${USER_PASSWORD:-}"

[[ -n "${USER_NAME:-}" ]] || die "USER_NAME missing in $CONF — arch.sh needs it too."
case "$ROOT_FS"     in ext4|btrfs) ;; *) die "ROOT_FS must be ext4 or btrfs (got '$ROOT_FS')" ;; esac
case "$USERDATA_FS" in ext4|btrfs) ;; *) die "USERDATA_FS must be ext4 or btrfs (got '$USERDATA_FS')" ;; esac

# ── Firmware ─────────────────────────────────────────────────────
#
# UEFI only, and the ISO still boots on BIOS on purpose — so that someone on old
# hardware gets THIS message rather than a machine that will not boot the
# medium at all and no idea why.
#
# Supporting BIOS as well means a fourth partition (a 1 MiB ef02 for GRUB's core
# image) and a second bootloader to keep working, on hardware nobody here can
# test. A machine with the CPU and GPU to emulate a PS3 has UEFI firmware.
[[ -d /sys/firmware/efi/efivars ]] || die "this machine booted in legacy BIOS mode.
  The guided install writes a UEFI layout (ESP + systemd-boot) and cannot set up
  a BIOS bootloader. Reboot and select the UEFI entry for the USB stick — in most
  firmware the boot menu lists the same stick twice, once with a 'UEFI:' prefix."

# ── The target disk ──────────────────────────────────────────────
[[ -b "$TARGET_DISK" ]] || die "TARGET_DISK '$TARGET_DISK' is not a block device."

# A partition has a ../<disk>/ parent in sysfs; a whole disk does not. Passing
# /dev/sda1 here would have sgdisk write a partition table INSIDE a partition.
[[ -d "/sys/class/block/$(basename "$TARGET_DISK")/device" ]] \
  || die "'$TARGET_DISK' is not a whole disk — give the disk (/dev/sda), not a partition (/dev/sda1)."

# The USB stick we booted from. Erasing it mid-install takes the running system
# with it, and the error that follows is unreadable.
BOOT_SRC="$(findmnt -n -o SOURCE /run/archiso/bootmnt 2>/dev/null || true)"
if [[ -n "$BOOT_SRC" ]]; then
  BOOT_DISK="/dev/$(lsblk -no PKNAME "$BOOT_SRC" 2>/dev/null || true)"
  [[ "$BOOT_DISK" != "$TARGET_DISK" ]] \
    || die "'$TARGET_DISK' is the medium this installer booted from."
fi

# Anything mounted from this disk means it is in use — very often the operator
# mounted their own data to copy something off it a minute ago.
MOUNTED="$(lsblk -no MOUNTPOINT "$TARGET_DISK" | grep -v '^$' || true)"
[[ -z "$MOUNTED" ]] || die "'$TARGET_DISK' has mounted partitions:
$(echo "$MOUNTED" | sed 's/^/    /')
  Unmount them first — refusing to repartition a disk that is in use."

# nvme0n1 → nvme0n1p1, sda → sda1. Getting this wrong writes to a device that
# does not exist, or worse, to one that does.
partof() {  # partof <n>
  if [[ "$TARGET_DISK" =~ [0-9]$ ]]; then echo "${TARGET_DISK}p$1"; else echo "${TARGET_DISK}$1"; fi
}
ESP_PART="$(partof 1)"; ROOT_PART="$(partof 2)"; DATA_PART="$(partof 3)"

# ── Summary and the point of no return ───────────────────────────
DISK_SIZE="$(lsblk -dno SIZE "$TARGET_DISK" | tr -d ' ')"
DISK_MODEL="$(lsblk -dno MODEL "$TARGET_DISK" | sed 's/ *$//')"

msg "GameCore — guided install"
info "Target disk  : $TARGET_DISK  ($DISK_SIZE, ${DISK_MODEL:-unknown model})"
info "  $ESP_PART   $ESP_SIZE   FAT32   → /boot"
info "  $ROOT_PART  $ROOT_SIZE  $ROOT_FS → /"
info "  $DATA_PART  rest        $USERDATA_FS → /userdata"
info "User         : $USER_NAME"
info "Hostname     : $TARGET_HOSTNAME"
info "Locale       : $LOCALE   Keymap: $KEYMAP   Timezone: $TIMEZONE"
echo
warn "EVERYTHING ON $TARGET_DISK WILL BE DESTROYED."
echo

if ! $ASSUME_YES && ! $DRY_RUN; then
  # The disk path typed back, not y/N. A single keystroke is not a decision
  # proportionate to erasing a disk, and the operator has to have READ the line
  # above to answer this one.
  read -rp "  Type the disk path to confirm ($TARGET_DISK): " CONFIRM
  [[ "$CONFIRM" == "$TARGET_DISK" ]] || die "Aborted (got '$CONFIRM')."
fi

# ── Partition ────────────────────────────────────────────────────
msg "Partitioning $TARGET_DISK"
# --zap-all and not just a new table: a disk that already held an ESP keeps its
# old GPT backup header at the end of the device, and sgdisk then "recovers" it
# on the next boot, restoring partitions that no longer exist.
run sgdisk --zap-all "$TARGET_DISK"
run sgdisk \
  -n "1:0:+${ESP_SIZE}"  -t 1:ef00 -c 1:"GAMECORE_ESP" \
  -n "2:0:+${ROOT_SIZE}" -t 2:8304 -c 2:"GAMECORE_ROOT" \
  -n "3:0:0"             -t 3:8300 -c 3:"GAMECORE_USERDATA" \
  "$TARGET_DISK"
# The kernel re-reads the table asynchronously. Without the settle, mkfs below
# runs against device nodes udev has not created yet — intermittently, and more
# often on fast NVMe than on the SATA disk anyone tests with.
run partprobe "$TARGET_DISK"
run udevadm settle
ok "Partition table written."

# ── Filesystems ──────────────────────────────────────────────────
msg "Creating filesystems"
run mkfs.fat -F32 -n GCESP "$ESP_PART"
if [[ "$ROOT_FS" == "btrfs" ]]; then run mkfs.btrfs -f -L GCROOT "$ROOT_PART"
else                                 run mkfs.ext4 -F -L GCROOT "$ROOT_PART"; fi
if [[ "$USERDATA_FS" == "btrfs" ]]; then run mkfs.btrfs -f -L GCDATA "$DATA_PART"
else                                     run mkfs.ext4 -F -L GCDATA "$DATA_PART"; fi
ok "Filesystems created."

# ── Mount ────────────────────────────────────────────────────────
msg "Mounting the target"
run mount "$ROOT_PART" /mnt
run mkdir -p /mnt/boot /mnt/userdata
# The ESP is mounted BEFORE the copy so that /boot's kernel and microcode land
# on it. Mounting it afterwards hides the copied vmlinuz-linux behind an empty
# filesystem, and `mkinitcpio -P` does not put the kernel back — the box then
# boots to "No loader found" with a perfectly good root partition.
run mount "$ESP_PART" /mnt/boot
run mount "$DATA_PART" /mnt/userdata
ok "Mounted at /mnt."

# ── Copy the live root onto the disk ─────────────────────────────
msg "Copying the system (this is the long part)"
# A copy of the running live root, not a pacstrap: there is no mirror to
# pacstrap from. Everything the installed box needs is already in this squashfs
# — that is what packages.x86_64 is for.
#
# /boot is excluded here and copied separately below, because the ESP is FAT:
# rsync -aAX tries to set ownership and xattrs on it, every one of those fails,
# and rsync exits non-zero — which under `set -e` ends the install after it has
# already repartitioned the disk.
run rsync -aHAX --info=progress2 \
  --exclude='/dev/*' --exclude='/proc/*' --exclude='/sys/*' --exclude='/tmp/*' \
  --exclude='/run/*'  --exclude='/mnt/*'  --exclude='/media/*' \
  --exclude='/lost+found' --exclude='/boot/*' \
  / /mnt/
# -rltD, deliberately not -a: no perms, no owner, no ACLs. See above.
run rsync -rltD /boot/ /mnt/boot/
ok "System copied."

# ── Remove everything that only makes sense on the live medium ───
msg "Turning the copy into an installed system"

# Each of these boots the installed box into the INSTALLER if left behind.
for live_only in \
    /mnt/etc/systemd/system/getty@tty1.service.d/autologin.conf \
    /mnt/root/.automated_script.sh \
    /mnt/root/.zlogin \
    /mnt/root/.bash_profile \
    /mnt/root/.xinitrc \
    /mnt/usr/local/bin/gamecore-iso-session.sh \
    /mnt/usr/local/bin/gamecore-iso-installer.sh \
    /mnt/usr/local/bin/gamecore-disk-install.sh ; do
  run rm -f "$live_only"
done

# The archiso initramfs hooks. Left in place, `mkinitcpio -P` below builds an
# initramfs that looks for a squashfs on a removable medium instead of mounting
# the root partition — the box then boots the installer's initramfs off its own
# disk and hangs waiting for a device labelled GAMECORE_*.
run rm -f /mnt/etc/mkinitcpio.conf.d/archiso.conf

# The preset shipped for the ISO builds one image and no fallback. An installed
# machine wants the fallback: it is the image with every module in it, and it is
# what boots when a kernel update autodetects the wrong storage driver.
run tee /mnt/etc/mkinitcpio.d/linux.preset >/dev/null <<'PRESET'
# mkinitcpio preset file for the 'linux' package
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux"

PRESETS=('default' 'fallback')

default_image="/boot/initramfs-linux.img"
fallback_image="/boot/initramfs-linux-fallback.img"
fallback_options="-S autodetect"
PRESET

# The live ISO ships root with an EMPTY password (that is how the autologin
# works). Copied as-is, every machine installed from this ISO would have a
# passwordless root. Locked here, and re-opened below only if the conf asked
# for a password.
run rm -f /mnt/etc/machine-id           # regenerated on first boot; shared ids break DHCP leases
run rm -f /mnt/etc/hostname
run tee /mnt/etc/hostname >/dev/null <<<"$TARGET_HOSTNAME"
run tee /mnt/etc/hosts >/dev/null <<HOSTS
127.0.0.1   localhost
::1         localhost
127.0.1.1   ${TARGET_HOSTNAME}.localdomain ${TARGET_HOSTNAME}
HOSTS

# fstab, from what is actually mounted right now. By UUID: partition ORDER is
# not stable across firmware, and a box that boots from a different SATA port
# than it was installed on must still find its root.
run rm -f /mnt/etc/fstab
if $DRY_RUN; then
  printf '    [dry-run] genfstab -U /mnt >> /mnt/etc/fstab\n'
else
  genfstab -U /mnt >> /mnt/etc/fstab
fi
ok "fstab, hostname and initramfs presets written."

# ── Configure the installed system ───────────────────────────────
msg "Configuring locale, clock and bootloader"

in_target() {  # in_target <command…>
  if $DRY_RUN; then printf '    [dry-run] arch-chroot /mnt %s\n' "$*"
  else arch-chroot /mnt "$@"; fi
}

run ln -sf "/usr/share/zoneinfo/$TIMEZONE" /mnt/etc/localtime
in_target hwclock --systohc

run tee /mnt/etc/locale.gen >/dev/null <<<"$LOCALE UTF-8"
in_target locale-gen
run tee /mnt/etc/locale.conf  >/dev/null <<<"LANG=$LOCALE"
run tee /mnt/etc/vconsole.conf >/dev/null <<<"KEYMAP=$KEYMAP"

if [[ -n "$ROOT_PASSWORD" ]]; then
  if $DRY_RUN; then printf '    [dry-run] chpasswd (root) in target\n'
  else printf 'root:%s\n' "$ROOT_PASSWORD" | arch-chroot /mnt chpasswd; fi
  ok "root password set."
else
  in_target passwd --lock root
  ok "root account locked (no password was given in the conf)."
fi

# arch.sh creates the GameCore user itself on first boot, so there may be no such
# account yet — this only runs when the conf asked for a password AND the copy
# already has the user, which is the re-install case.
if [[ -n "$USER_PASSWORD" ]] && ! $DRY_RUN && arch-chroot /mnt id "$USER_NAME" >/dev/null 2>&1; then
  printf '%s:%s\n' "$USER_NAME" "$USER_PASSWORD" | arch-chroot /mnt chpasswd
  ok "password set for $USER_NAME."
fi

in_target mkinitcpio -P

msg "Bootloader"
in_target bootctl --esp-path=/boot install
ROOT_UUID="$(blkid -s UUID -o value "$ROOT_PART" 2>/dev/null || echo PLACEHOLDER-UUID)"
run mkdir -p /mnt/boot/loader/entries
run tee /mnt/boot/loader/loader.conf >/dev/null <<'LOADER'
# 0 — this machine is a console. A boot menu on a TV, navigated with a gamepad
# that does not work in the firmware, is a five-second pause with no purpose.
# Hold Space during boot to get the menu back when something needs fixing.
timeout 0
default gamecore.conf
console-mode keep
LOADER
run tee /mnt/boot/loader/entries/gamecore.conf >/dev/null <<ENTRY
title   GameCore
linux   /vmlinuz-linux
initrd  /intel-ucode.img
initrd  /amd-ucode.img
initrd  /initramfs-linux.img
options root=UUID=${ROOT_UUID} rw quiet loglevel=3
ENTRY
run tee /mnt/boot/loader/entries/gamecore-fallback.conf >/dev/null <<ENTRY
title   GameCore (fallback initramfs)
linux   /vmlinuz-linux
initrd  /initramfs-linux-fallback.img
options root=UUID=${ROOT_UUID} rw
ENTRY
ok "systemd-boot installed."

# ── Hand the rest to arch.sh, on the first boot ──────────────────
msg "Arming the first-boot install"
# The conf travels with the machine: arch.sh needs it, and it is also the record
# of what this install was asked for. Mode 600 — it carries the web password and
# the scraper credentials, exactly like the GUI's temporary copy does.
if ! $DRY_RUN; then
  install -m 600 -o root -g root "$CONF" /mnt/etc/gamecore-install.conf
  # /userdata is the whole point of the third partition. Written into the conf
  # rather than left to arch.sh's default, which is GAMECORE_PATH — a fresh box
  # that fell back to that default would put saves on the root partition and the
  # data partition would sit empty for ever.
  {
    echo ""
    echo "# --- added by gamecore-disk-install.sh ---"
    echo "GAMECORE_DATA=/userdata"
    # The install runs with no mirror configured and possibly no cable plugged
    # in. See install/arch.sh's offline handling.
    echo "OFFLINE=auto"
  } >> /mnt/etc/gamecore-install.conf
else
  printf '    [dry-run] install -m 600 %s /mnt/etc/gamecore-install.conf (+ GAMECORE_DATA=/userdata, OFFLINE=auto)\n' "$CONF"
fi

# Both come out of the payload that was copied to the target a moment ago, so
# they are the versions that shipped with THIS ISO — not whatever the live
# medium happens to have under /usr/local.
PAYLOAD_SRC="${GAMECORE_ISO_PAYLOAD:-/usr/share/gamecore}/src"
run install -m 644 -o root -g root \
  "$PAYLOAD_SRC/install/system/gamecore-firstboot.service" \
  /mnt/etc/systemd/system/gamecore-firstboot.service
run install -m 755 -o root -g root \
  "$PAYLOAD_SRC/install/bin/gamecore-firstboot" \
  /mnt/usr/local/bin/gamecore-firstboot
run mkdir -p /mnt/etc/systemd/system/multi-user.target.wants
# The symlink by hand rather than `arch-chroot systemctl enable`: systemctl in a
# chroot needs to talk to a systemd that is not running there, and the failure is
# a "Failed to connect to bus" that stops the install one step from the end.
run ln -sf /etc/systemd/system/gamecore-firstboot.service \
           /mnt/etc/systemd/system/multi-user.target.wants/gamecore-firstboot.service
ok "gamecore-firstboot.service armed."

# ── Done ─────────────────────────────────────────────────────────
if ! $DRY_RUN; then
  sync
  umount -R /mnt || warn "could not unmount /mnt cleanly — run 'sync' before pulling the power."
fi

msg "Installed"
info "Remove the USB stick and reboot."
info "The first boot finishes the install (emulators, services, kiosk) and"
info "reboots once more into GameCore. It takes a while and it prints what it"
info "is doing on the screen — it has not hung."
