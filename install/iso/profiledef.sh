#!/usr/bin/env bash
# archiso profile for the GameCore installation ISO.
#
# Derived from archiso's `releng` profile. What differs from it, and why:
#
#   · packages.x86_64 carries the WHOLE target package set, not just what a
#     rescue shell needs. The install is offline (see gamecore-disk-install.sh):
#     the target system is a copy of this live root, so anything absent here is
#     absent from the installed box, with no network to fetch it from.
#   · the live session auto-starts the GameCore installer instead of a root
#     shell prompt.
#   · no `bootstrap` buildmode — we ship an ISO to burn, not a tarball.
#
# Build:  sudo bash install/iso/build.sh        (never on a workstation you care
#                                                about — see that script's head)
#
# shellcheck disable=SC2034
# ^ archiso sources this file and reads the variables; nothing here is "unused".

iso_name="gamecore"
# The volume ID, and the ONLY thing the archiso initramfs hook has to find the
# squashfs by (`archisolabel=` on the kernel command line). ISO-9660 allows
# A-Z 0-9 _ and 32 characters — a lowercase letter or a dash here produces an
# image that boots to "Waiting for device /dev/disk/by-label/…" and nothing
# else. The date suffix keeps two ISOs from claiming the same label on the same
# machine, which is how a USB stick boots the image you burned last month.
iso_label="GAMECORE_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="GameCore <https://github.com/p4v1c/GamecoreRenew>"
iso_application="GameCore Installer"
# The release tag when CI builds it, a date otherwise. CI passes the tag so the
# ISO on a release page reports the version of that release rather than the day
# the runner happened to build it.
iso_version="${GAMECORE_ISO_VERSION:-$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)}"
install_dir="arch"
buildmodes=('iso')
# UEFI x64 and legacy BIOS. Deliberately no uefi-ia32: a 32-bit UEFI on a
# machine able to run PS3 emulation does not exist, and each extra bootmode is
# another bootloader to keep working blind.
#
# Secure Boot is NOT supported in this version — nothing here is signed. The
# README says "disable Secure Boot" rather than pretending otherwise.
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito'
           'uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
# zstd rather than releng's xz. The airootfs here is several times the size of a
# rescue image (a whole Plasma desktop plus the GameCore payload), and xz -Xbcj
# on that takes long enough in CI to hit the job timeout. zstd -19 lands within
# a few percent of xz on this content and compresses several times faster.
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '19' '-b' '1M')

file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  # Both login shells are shipped on purpose — see the head of .automated_script.sh.
  ["/root/.zlogin"]="0:0:644"
  ["/root/.bash_profile"]="0:0:644"
  ["/root/.xinitrc"]="0:0:755"
  ["/usr/local/bin/gamecore-iso-session.sh"]="0:0:755"
  ["/usr/local/bin/gamecore-disk-install.sh"]="0:0:755"
  ["/usr/local/bin/gamecore-iso-installer.sh"]="0:0:755"
)
