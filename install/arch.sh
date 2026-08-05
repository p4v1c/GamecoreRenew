#!/usr/bin/env bash
# ================================================================
#  GameCore — Installation Script
#  Manjaro / Arch Linux · AMD GPU · Flatpak
#  Idempotent: safe to run multiple times
# ================================================================
set -euo pipefail

RED='\033[1;31m'; GRN='\033[1;32m'; YLW='\033[1;33m'
BLU='\033[1;34m'; RST='\033[0m'

msg()  { echo -e "\n${BLU}──────────────────────────────────────${RST}\n${GRN}  $*${RST}"; }
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YLW}⚠  $*${RST}"; }
die()  { echo -e "\n${RED}[ERROR]${RST} $*" >&2; exit 1; }
info() { echo -e "  ${RST}$*"; }

pacman_optional() {
  record_new_pkgs "$1"
  pacman -S --noconfirm --needed "$1" 2>/dev/null && ok "$1" || warn "$1 not in repos — skipping"
}

# Machine-readable progress for the graphical installer: "@GC-PROGRESS@ <pct> <label>".
# Only emitted when the GUI sets GAMECORE_PROGRESS=1 — a plain CLI install
# stays clean. Percentages are hand-assigned milestones (minimal mode jumps).
progress() {  # progress <pct> <label…>
  if [[ "${GAMECORE_PROGRESS:-0}" == "1" ]]; then
    echo "@GC-PROGRESS@ $1 ${*:2}"
  fi
}

# Bounded git clone: a connection that stalls mid-transfer otherwise hangs
# git (and the whole install) forever — abort under 1 KB/s for 30 s, hard
# cap at 5 min, and never leave a half-written checkout behind.
git_clone() {  # git_clone <url> <dir>
  timeout 300 git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 \
    clone -q "$1" "$2" && return 0
  rm -rf "$2"
  return 1
}

git_sync() {  # git_sync <dir> <label> — bring an EXISTING satellite checkout up to date
  # Cloning only when the directory is absent left every satellite pinned to
  # whatever commit it was first installed at, for ever: re-running the
  # installer printed "already present" and moved on, and OTA never touches
  # /opt outside GAMECORE_PATH. A fix shipped upstream reached nothing.
  #
  # Fast-forward only, and never over local changes — an installer that
  # stashes or resets behind the owner's back is exactly how a hand-applied
  # fix disappears. It says what it did not do instead.
  local dir="$1" label="$2" head
  [[ -d "$dir/.git" ]] || { warn "$label: $dir is not a git checkout — left untouched."; return 0; }
  if [[ -n "$(sudo -u "$USER_NAME" git -C "$dir" status --porcelain 2>/dev/null)" ]]; then
    warn "$label: local changes in $dir — NOT updated."
    info "  Keep them, then update:  git -C $dir stash && git -C $dir pull --ff-only"
    return 0
  fi
  if sudo -u "$USER_NAME" timeout 120 git -C "$dir" pull -q --ff-only 2>/dev/null; then
    head="$(sudo -u "$USER_NAME" git -C "$dir" log --oneline -1 2>/dev/null | cut -c1-60)"
    ok "$label up to date (${head:-unknown})."
  else
    warn "$label: could not fast-forward $dir — left at its current commit."
  fi
}

# ── Install manifest ─────────────────────────────────────────────
# install/uninstall.sh reads these to know what THIS install actually
# changed, so it can put the machine back without guessing. Without them
# an uninstaller cannot tell "we installed caddy" from "caddy was already
# here", and the only safe answer is then to remove nothing.
MANIFEST_DIR="/var/lib/gamecore"
MANIFEST="${MANIFEST_DIR}/manifest.env"
PKG_MANIFEST="${MANIFEST_DIR}/pacman-installed"
FLATPAK_MANIFEST="${MANIFEST_DIR}/flatpak-installed"
OVERRIDE_MANIFEST="${MANIFEST_DIR}/flatpak-overrides"

manifest_set() {  # manifest_set <KEY> <value>
  mkdir -p "$MANIFEST_DIR"; touch "$MANIFEST"
  sed -i "/^$1=/d" "$MANIFEST"
  printf '%s=%q\n' "$1" "$2" >> "$MANIFEST"
}

# Record only what pacman/flatpak did NOT already have. Called before the
# install so "already present" never ends up on the removal list.
record_new_pkgs() {  # record_new_pkgs <pkg...>
  local p
  mkdir -p "$MANIFEST_DIR"; touch "$PKG_MANIFEST"
  for p in "$@"; do
    pacman -Qq "$p" >/dev/null 2>&1 && continue
    grep -qxF "$p" "$PKG_MANIFEST" 2>/dev/null || echo "$p" >> "$PKG_MANIFEST"
  done
}

# Apps we changed the sandbox permissions of — a superset of the ones we
# installed, and the list the uninstaller must reset.
record_flatpak_override() {  # record_flatpak_override <app-id>
  mkdir -p "$MANIFEST_DIR"; touch "$OVERRIDE_MANIFEST"
  grep -qxF "$1" "$OVERRIDE_MANIFEST" 2>/dev/null || echo "$1" >> "$OVERRIDE_MANIFEST"
}

record_new_flatpak() {  # record_new_flatpak <app-id>
  mkdir -p "$MANIFEST_DIR"; touch "$FLATPAK_MANIFEST"
  grep -qxF "$1" "$FLATPAK_MANIFEST" 2>/dev/null || echo "$1" >> "$FLATPAK_MANIFEST"
}

# Is a Flatpak app installed? `flatpak list | grep -q <id>` matches
# substrings (org.DolphinEmu.dolphin-emu also matches a hypothetical
# …dolphin-emu-beta) — compare the application column exactly instead.
flatpak_installed() {  # flatpak_installed <app-id>
  flatpak list --app --columns=application 2>/dev/null | grep -qxF "$1"
}

[[ $EUID -eq 0 ]] || die "Run with sudo: sudo bash install/arch.sh [--full|--minimal]"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Install mode ─────────────────────────────────────────────────
#   --full           : GameCore + all emulators/apps (Flatpak) + curated configs
#   --minimal        : GameCore only — no emulator, no application
#   --unattended <f> : zero prompt — read everything from conf file <f>
#                      (written by the graphical wizard install/install.sh,
#                      also the entry point for the GameCore OS ISO)
MODE="${1:-}"
UNATTENDED=false
CONF=""
case "$MODE" in
  --full)    MODE="full" ;;
  --minimal) MODE="minimal" ;;
  --unattended)
    UNATTENDED=true; MODE=""
    CONF="${2:-}"
    [[ -n "$CONF" && -f "$CONF" ]] || die "usage: arch.sh --unattended <conf-file>"
    ;;
  "")        ;;  # asked interactively after the summary
  *)         die "Unknown option '$MODE' (use --full, --minimal or --unattended <conf>)" ;;
esac

# ── Detect distro ────────────────────────────────────────────────
IS_MANJARO=false
grep -qi "manjaro" /etc/os-release 2>/dev/null && IS_MANJARO=true

# ── Banner ───────────────────────────────────────────────────────
echo -e "\n${BLU}╔══════════════════════════════════════╗${RST}"
echo -e "${BLU}║     GameCore — Installer          ║${RST}"
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"

# ── Configuration — conf file (unattended) or prompts ────────────
# EMULATORS: "all" or space-separated ids among:
#   azahar rpcs3 pcsx2 dolphin melonds gopher64 mgba ppsspp cemu ryujinx
#   shadps4 duckstation xenia
# APPS: "all" or space-separated ids among: twitch stremio steam youtube
# ADDONS: space-separated gamecore-addons names installed at the end.
EMULATORS="all"
APPS="all"
ADDONS="rom-manager"
TWITCH_CLIENT_ID=""; TWITCH_CLIENT_SECRET=""; TGDB_API_KEY=""
# ScreenScraper — two credential levels, both required, see the prompt below.
SS_DEV_ID=""; SS_DEV_PASSWORD=""; SS_USER=""; SS_PASSWORD=""

LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1); exit}')

if $UNATTENDED; then
  # shellcheck disable=SC1090
  source "$CONF"
  [[ -n "${USER_NAME:-}" ]] || die "USER_NAME missing in $CONF"
  GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
  WEB_PORT="${WEB_PORT:-8765}"
  MODE="${MODE:-full}"
  [[ "$MODE" == "full" || "$MODE" == "minimal" ]] || die "MODE must be full or minimal"
  # Older confs predate APPS and listed steam among the emulators — keep both
  # working: no APPS line means "all apps", steam-as-emulator becomes an app.
  APPS="${APPS-all}"
  if [[ "$APPS" != "all" && " $EMULATORS " == *" steam "* && " $APPS " != *" steam "* ]]; then
    APPS="$APPS steam"
  fi
else
  read -rp "  System username (e.g. pavic)         : " USER_NAME
  [[ -n "$USER_NAME" ]] || die "Username cannot be empty."
  read -rp "  Install path [default: /opt/GameCore] : " GAMECORE_PATH
  GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
  read -rp "  Web ROM port [default: 8765]          : " WEB_PORT
  WEB_PORT="${WEB_PORT:-8765}"

  if [[ -z "$MODE" ]]; then
    echo
    read -rp "  Install emulators & applications too? Full install / GameCore only (F/m) : " ANSWER
    [[ "$ANSWER" =~ ^[mM]$ ]] && MODE="minimal" || MODE="full"
  fi

  if [[ "$MODE" == "full" ]]; then
    echo
    info "EmberTV (Twitch on the TV) — leave empty to run in demo mode."
    info "Create the app at https://dev.twitch.tv/console/apps (redirect: http://localhost:8097)."
    read -rp  "  Twitch Client ID                      : " TWITCH_CLIENT_ID
    read -rsp "  Twitch Client Secret (hidden)         : " TWITCH_CLIENT_SECRET; echo
    read -rsp "  TheGamesDB API key (covers, optional) : " TGDB_API_KEY; echo

    echo
    info "ScreenScraper (box art, 3D boxes, screenshots, videos, synopses)."
    info "TWO accounts are needed and they are not the same thing:"
    info "  · developer  — asked for on the ScreenScraper forum, per software."
    info "                 The dev id is the PSEUDONYM, not the number in the"
    info "                 devinfos.php URL. Without it: 403."
    info "  · member     — your own account on screenscraper.fr. It carries the"
    info "                 daily quota and the thread count."
    info "Leave empty to skip: covers then resolve exactly as before."
    read -rp  "  ScreenScraper dev id                  : " SS_DEV_ID
    read -rsp "  ScreenScraper dev password (hidden)   : " SS_DEV_PASSWORD; echo
    read -rp  "  ScreenScraper member login            : " SS_USER
    read -rsp "  ScreenScraper member password (hidden): " SS_PASSWORD; echo
  fi
fi

want_emu() { [[ "$EMULATORS" == "all" || " $EMULATORS " == *" $1 "* ]]; }
want_app() { [[ "$MODE" == "full" ]] && [[ "$APPS" == "all" || " $APPS " == *" $1 "* ]]; }

echo
msg "Summary"
info "User         : $USER_NAME"
info "Install path : $GAMECORE_PATH"
info "API port     : $WEB_PORT"
info "Detected IP  : $LOCAL_IP"
info "Mode         : $MODE $([ "$MODE" = minimal ] && echo '(no emulators, no apps)' || echo '(emulators + apps + configs)')"
[[ "$MODE" == "full" ]] && info "Emulators    : ${EMULATORS:-none}"
[[ "$MODE" == "full" ]] && info "Apps         : ${APPS:-none}"
info "Addons       : ${ADDONS:-none}"
[[ "$MODE" == "full" ]] && info "EmberTV      : $([ -n "$TWITCH_CLIENT_ID" ] && echo 'live Twitch (credentials set)' || echo 'demo mode (no credentials)')"
[[ "$MODE" == "full" ]] && info "ScreenScraper: $([ -n "$SS_DEV_ID" ] && echo 'configured (hash matching + every media type)' || echo 'absent (covers by name only)')"
echo
if ! $UNATTENDED; then
  read -rp "  Continue? (y/N) " CONFIRM
  [[ "$CONFIRM" =~ ^[yY]$ ]] || die "Aborted."
fi

# ── User check ───────────────────────────────────────────────────
progress 2 "Checking user"
msg "Checking user"
USER_CREATED=0
if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$USER_NAME"
  USER_CREATED=1
  ok "User $USER_NAME created."
fi
ok "User $USER_NAME OK"
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)

# The uninstaller must never delete an account that predates GameCore.
manifest_set USER_NAME      "$USER_NAME"
manifest_set GAMECORE_PATH  "$GAMECORE_PATH"
manifest_set WEB_PORT       "$WEB_PORT"
manifest_set MODE           "$MODE"
manifest_set USER_CREATED   "$USER_CREATED"
manifest_set INSTALLED_AT   "$(date -Iseconds)"
# Create the list files up front, even empty. "We installed no Flatpaks" and
# "there is no record of what we installed" must not look the same to the
# uninstaller: the first means remove nothing, the second means it is blind.
touch "$PKG_MANIFEST" "$FLATPAK_MANIFEST" "$OVERRIDE_MANIFEST"

# ── Copy files ───────────────────────────────────────────────────
progress 4 "Copying GameCore files"
msg "Setting up $GAMECORE_PATH"
# The destination itself, not just its parent. `cp -r "$SRC/." "$GAMECORE_PATH"`
# used to create it on the way; the tar pipeline below cannot — `tar -C <dir>`
# needs <dir> to exist and exits before reading a single byte. Every FRESH
# install died here, at 4 %, with "tar: /opt/GameCore: Cannot open". Only an
# install onto an existing directory — i.e. a re-run — got past it, which is
# exactly the case anyone testing the change would have been in.
mkdir -p "$GAMECORE_PATH"
if [ "$PROJECT_ROOT" != "$GAMECORE_PATH" ]; then
  # Copy with the same exclusions update/linux.sh uses, not a bare `cp -r`.
  #
  # Re-running the installer from a checkout is a path this script recommends at
  # the end, and `cp -r "$PROJECT_ROOT/."` had no exclusions at all: a bezel
  # uploaded from the ROM manager (assets/overlays/pcsx2.png) was overwritten by
  # the repo's copy, with no backup and nothing said. Same for the 18
  # assets/logos/*.png, config/overlays.json and the installed themes.
  # uninstall.sh already preserves assets/ for exactly this reason.
  #
  # tar rather than rsync: this runs at 4 %, before `pacman -Syu`, and rsync is
  # not part of Arch's `base` — tar is. Same semantics as the old `cp -r "$SRC/."`
  # (merge into the destination, delete nothing), only with exclusions.
  tar -C "$PROJECT_ROOT" \
    --exclude='./.git' \
    --exclude='./.venv' \
    --exclude='./emu' \
    --exclude='./config' \
    --exclude='./assets/overlays' \
    --exclude='./assets/logos' \
    -cf - . \
    | tar -C "$GAMECORE_PATH" -xf - \
    || die "could not copy $PROJECT_ROOT → $GAMECORE_PATH"

  # First run: those directories have to arrive from somewhere. Copy each only
  # when it is absent at the destination, so an existing install keeps its own.
  # config/systems.json and config/apps.json are regenerated from install/*.dist
  # further down either way, so excluding config/ above costs nothing.
  for _keep in emu config assets/overlays assets/logos; do
    if [ -d "$PROJECT_ROOT/$_keep" ] && [ ! -e "$GAMECORE_PATH/$_keep" ]; then
      mkdir -p "$(dirname "$GAMECORE_PATH/$_keep")"
      cp -a "$PROJECT_ROOT/$_keep" "$GAMECORE_PATH/$_keep"
    fi
  done
  ok "Copied $PROJECT_ROOT → $GAMECORE_PATH (user content preserved)"
else
  ok "Already in place."
fi
chown -R "${USER_NAME}:${USER_NAME}" "$GAMECORE_PATH"

# ── System packages ──────────────────────────────────────────────
# pacman is by far the longest phase of the install (a rolling-release
# upgrade plus ~25 packages). Without markers inside it the GUI's progress
# bar sits at 6 % for up to 40 minutes and looks hung.
progress 6 "Refreshing and upgrading system packages (this can take a while)"
msg "System packages"
pacman -Syu --noconfirm

progress 14 "Installing base packages (desktop, drivers, node, caddy)"
PKGS=(
  mesa
  base-devel git flatpak openssh
  python python-pip
  nodejs npm
  # ffmpeg: general media tooling. Stremio no longer needs it — its desktop
  # client plays through mpv and never transcodes (see docs/STREMIO.md) — but
  # nothing else replaces it on a media box, so it stays.
  ffmpeg
  plasma-desktop sddm xorg-xdpyinfo xorg-xrandr xorg-xset unclutter
  bluez bluez-utils
  caddy
  # update/linux.sh does all of its file installation with rsync, and rsync is
  # not in Arch's `base` — an OTA on a box without it failed at the first step.
  rsync
)

# Kernel series — needed by both the headers and the Manjaro NVIDIA module,
# so it is computed before the GPU branch. `uname -r` is the RUNNING kernel;
# on a box that was upgraded but not rebooted the matching package may not
# exist any more, hence the availability check below.
KERNEL=$(uname -r)
KSHORT=""
if $IS_MANJARO; then
  KSHORT=$(echo "$KERNEL" | grep -oP '^\d+\.\d+' | tr -d '.')
  KRT=""; [[ $KERNEL == *-rt* ]] && KRT="-rt"
  if pacman -Si "linux${KSHORT}${KRT}-headers" >/dev/null 2>&1; then
    PKGS+=("linux${KSHORT}${KRT}-headers")
  else
    warn "linux${KSHORT}${KRT}-headers not in the repos — kernel headers skipped."
    warn "  (running kernel: $KERNEL — reboot into the installed kernel and re-run if you need DKMS.)"
  fi
else
  [[ $KERNEL == *zen* ]] && PKGS+=("linux-zen-headers") || PKGS+=("linux-headers")
fi

# The lib32-* drivers live in [multilib], which Manjaro enables and Arch does
# not. Asking pacman for a package from a disabled repo is a "target not found"
# error, and under `set -euo pipefail` that ended the whole install mid-way —
# after the system upgrade and after the user account was created, before any
# service was configured. The box was left in a state that was neither a working
# install nor a clean machine.
#
# Not enabled automatically on purpose: /var/lib/gamecore is the record of what
# this install changed, and quietly editing /etc/pacman.conf would not be in it.
HAS_MULTILIB=false
if pacman-conf --repo-list 2>/dev/null | grep -qx multilib; then
  HAS_MULTILIB=true
fi

# `|| true` so a false HAS_MULTILIB is not the function's exit status — that
# alone would abort the install under `set -e`.
add_lib32() { $HAS_MULTILIB && PKGS+=("$@") || true; }

if ! $HAS_MULTILIB; then
  warn "[multilib] is not enabled — skipping the 32-bit Vulkan drivers."
  warn "  32-bit games (mostly under Steam/Proton) may not render."
  warn "  To enable it, uncomment the [multilib] section in /etc/pacman.conf,"
  warn "  run 'sudo pacman -Sy', then re-run this installer."
fi

# GPU drivers — detect the vendor instead of assuming AMD
GPU_INFO=$(lspci -nn 2>/dev/null | grep -Ei 'vga|3d|display' || true)
NVIDIA_REBOOT_NEEDED=false
if echo "$GPU_INFO" | grep -qiE 'amd|radeon'; then
  PKGS+=(xf86-video-amdgpu vulkan-radeon)
  add_lib32 lib32-vulkan-radeon
  info "GPU detected: AMD (vulkan-radeon)"
elif echo "$GPU_INFO" | grep -qi 'intel'; then
  PKGS+=(vulkan-intel)
  add_lib32 lib32-vulkan-intel
  info "GPU detected: Intel (vulkan-intel)"
elif echo "$GPU_INFO" | grep -qi 'nvidia'; then
  # NEVER pass the bare name `nvidia` on Manjaro: no package is called that.
  # ~20 packages merely *provide* it, and `--noconfirm` suppresses the
  # "N providers available" prompt, so pacman silently picks the first —
  # linux61-nvidia — which drags in the whole 6.1 LTS kernel and builds the
  # module for a kernel this box is not running. X then loads nvidia_drv.so,
  # finds no matching module, and the kiosk session never comes up.
  NV_PKG=""
  if $IS_MANJARO && [[ -n "$KSHORT" ]]; then
    for cand in "linux${KSHORT}${KRT}-nvidia" "nvidia-dkms"; do
      if pacman -Si "$cand" >/dev/null 2>&1; then NV_PKG="$cand"; break; fi
    done
  else
    NV_PKG="nvidia"
  fi
  if [[ -n "$NV_PKG" ]]; then
    PKGS+=("$NV_PKG" nvidia-utils)
    add_lib32 lib32-nvidia-utils
    # nvidia-dkms builds against the installed kernel and therefore needs dkms
    # plus the headers added above.
    [[ "$NV_PKG" == "nvidia-dkms" ]] && PKGS+=(dkms)
    NVIDIA_REBOOT_NEEDED=true
    info "GPU detected: NVIDIA ($NV_PKG)"
  else
    warn "GPU detected: NVIDIA, but no driver package matches this kernel."
    warn "  Install it yourself before rebooting:  sudo mhwd -a pci nonfree 0300"
  fi
elif echo "$GPU_INFO" | grep -qiE 'vmware|virtualbox|virtio|qxl|bochs'; then
  # VM GPU — no hardware Vulkan; llvmpipe lets Vulkan apps at least start.
  PKGS+=(vulkan-swrast)
  info "GPU detected: virtual machine (software Vulkan via llvmpipe)"
else
  warn "GPU not identified — installing mesa only (add your Vulkan driver manually)."
fi

# The whole GameCore stack is X11-only (overlays, fullscreen enforcer, the
# gamepad→keyboard bridge, the 1080p pin), so the kiosk needs a real X session.
#
# That used to mean Plasma's X11 session, from the plasma-x11-session package.
# It no longer does. KDE is retiring the X11 session, so an installer built on
# it is built on something the distributions are in the process of removing —
# and the failure mode is the worst kind: the package simply stops existing and
# the box lands on Wayland at the next fresh install.
#
# Openbox is what the stack actually needs: a window manager, and nothing else.
# No desktop, no session manager, no compositor competing with the emulators
# for the screen. The kiosk is started by gamecore-ui.service off
# graphical.target rather than by the window manager, so openbox carries no
# configuration of its own — its defaults are the whole setup.
#
# The desktop escape hatch (`gamecore-session-select desktop`) switches
# auto-login to whatever full session the machine already has. Nothing is
# installed for it here: a box with no desktop simply has none to fall back to,
# which is a living-room appliance working as intended, not a failure.
PKGS+=(openbox)

record_new_pkgs "${PKGS[@]}"
pacman -S --noconfirm --needed "${PKGS[@]}"
ok "System packages installed."

progress 20 "Optional packages"
pacman_optional cpupower
pacman_optional amd-ucode
pacman_optional feh

# ── CPU governor ─────────────────────────────────────────────────
progress 22 "CPU governor"
msg "CPU governor"
if systemctl enable --now cpupower.service 2>/dev/null \
   && cpupower frequency-set -g performance 2>/dev/null; then
  ok "Performance mode set."
elif [ ! -d /sys/devices/system/cpu/cpu0/cpufreq ]; then
  warn "no cpufreq driver (VM or fixed-frequency CPU) — governor skipped."
else
  warn "cpupower not available."
fi

# ── Flatpak ──────────────────────────────────────────────────────
progress 24 "Flatpak / Flathub"
msg "Flatpak / Flathub"
flatpak remote-list 2>/dev/null | grep -q flathub \
  || flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
ok "Flathub ready."

# ── Emulators (full mode only) ───────────────────────────────────
# Declared outside the branch: the final recap reads them in minimal mode too.
DUCK_MISSING=false
XENIA_MISSING=false
if [[ "$MODE" == "full" ]]; then
  msg "Installing emulators (Flatpak)"
  # id → Flatpak app id, FROM THE CATALOGUE (catalog/<id>/pack.json).
  #
  # This was a hand-written map, and it was the ONE copy the N64 migration
  # updated — install-emu-configs.sh, uninstall.sh, flatpakify-systems.sh and
  # verify_emulators.py kept pointing at io.github.gopher64.gopher64 for
  # months. The key stays `gopher64` on purpose even though it launches
  # Rosalie's Mupen GUI: gopher64 sets no WM_CLASS on its window, so
  # overlay_monitor could never find it and the bezel never drew.
  declare -A EMU_FLATPAK=()
  while IFS=$'\t' read -r id app_id; do
    [[ -n "$id" ]] && EMU_FLATPAK[$id]="$app_id"
  done < <(python3 "$GAMECORE_PATH/scripts/catalog-query.py" flatpaks --kind emulator)
  [[ ${#EMU_FLATPAK[@]} -gt 0 ]] || die "catalog/ declares no Flatpak emulator — is the checkout complete?"

  FLATPAKS=()
  for id in "${!EMU_FLATPAK[@]}"; do
    want_emu "$id" && FLATPAKS+=("${EMU_FLATPAK[$id]}")
  done
  # Steam is not here any more: it is an app, and the app pass below installs it
  # from its pack — install_flatpak does the install, the sandbox override and
  # both uninstall manifests, which is exactly what this loop does by hand.
  EMU_I=0
  EMU_TOTAL=${#FLATPAKS[@]}
  # Unticking every emulator AND every app leaves the array empty; the
  # progress interpolation below would then divide by zero, which under
  # `set -e` kills the install outright.
  for pkg in ${FLATPAKS[@]+"${FLATPAKS[@]}"}; do
    EMU_I=$((EMU_I + 1))
    # interpolate 25 → 50 % across the selected emulators/apps
    progress $((25 + EMU_I * 25 / EMU_TOTAL)) "Installing $pkg"
    if flatpak_installed "$pkg"; then
      info "$pkg — already installed (left out of the uninstall manifest)."
    elif flatpak install -y flathub "$pkg"; then
      record_new_flatpak "$pkg"
      ok "$pkg installed."
    else
      warn "$pkg failed."
    fi
  done

  # Sandbox permissions, per pack. The emulator policy — ROM directory,
  # gamepad, X11 — is the default a pack gets by saying nothing; a pack that
  # needs a different one declares a `sandbox` block (Stremio wants
  # --filesystem=host and no X11 socket). It was hardcoded here, so the two
  # policies lived in two unrelated places in this file.
  #
  # Recorded separately from what we installed: an emulator the user already
  # had still gets a GameCore override, and the uninstaller has to reset it.
  declare -A SANDBOX=()
  while IFS=$'\t' read -r app_id flags; do
    [[ -n "$app_id" ]] && SANDBOX[$app_id]="$flags"
  done < <(python3 "$GAMECORE_PATH/scripts/catalog-query.py" sandbox \
             --gamecore-path "$GAMECORE_PATH")
  for pkg in ${FLATPAKS[@]+"${FLATPAKS[@]}"}; do
    # Unquoted on purpose: the flags are a space-separated list to expand.
    # shellcheck disable=SC2086
    flatpak override ${SANDBOX[$pkg]:-"--filesystem=$GAMECORE_PATH --device=all --socket=x11"} \
      "$pkg" 2>/dev/null || true
    record_flatpak_override "$pkg"
  done
  [[ $EMU_TOTAL -gt 0 ]] && ok "Flatpak overrides applied (ROMs dir + controller access)." \
                         || info "No emulator or Steam selected — nothing to install."

  # ── Non-Flatpak emulators: providers ──────────────────────────
  # DuckStation (an AppImage — not published on Flathub) and Xenia Canary (a
  # Windows zip run through Wine) each had a bespoke ~65-line block here, with
  # its own fetch function. The two were already almost identical: same
  # timeouts, same --speed-limit, same magic-byte check, same fall back to the
  # GitHub API. They are now DATA in catalog/<id>/pack.json, and one helper —
  # backend/services/installer/ — carries every protection they earned:
  #
  #   · the fixed release URL FIRST, the API only as a fallback. The API allows
  #     60 requests per hour per IP unauthenticated, and exhausting it is why
  #     fresh installs kept ending up with no PlayStation emulator at all: the
  #     step gave up without ever attempting a download.
  #   · a .part temp file, so an aborted transfer never lands at the final name
  #     and gets read as "already installed" on the next run.
  #   · magic bytes, because a 200 carrying an HTML error page is still a
  #     failed download and `curl -f` cannot see it.
  #   · extraction failure warns and carries on. It used to abort the WHOLE
  #     install at 52 %, before a single systemd unit or sudoers rule existed.
  #
  # New, and the reason it is worth having in one place: an optional sha256 per
  # pack, and a pinnable version. There was no integrity check anywhere before.
  #
  # `|| true`: a provider that fails costs one tile. The recap at the end says
  # which, and how to retry.
  for _id in duckstation xenia; do
    want_emu "$_id" || continue
    case "$_id" in
      duckstation) progress 50 "DuckStation AppImage"; msg "DuckStation AppImage" ;;
      xenia)       progress 52 "Xenia Canary (Wine)";  msg "Xenia Canary (Wine)" ;;
    esac
    # Provider-level dependencies (wine, unzip, p7zip for Xenia) are declared in
    # the pack under install.requires and installed by the provider itself.
    _out=$(python3 "$GAMECORE_PATH/scripts/gamecore-provider.py" install "$_id" \
             --user "$USER_NAME" --gamecore-path "$GAMECORE_PATH" 2>&1) || true
    while IFS= read -r _line; do
      case "$_line" in
        OK*)   ok   "${_line#OK }" ;;
        SAME*) info "${_line#SAME }" ;;
        *)     warn "${_line#FAIL }"
               [[ "$_id" == duckstation ]] && DUCK_MISSING=true
               [[ "$_id" == xenia ]]       && XENIA_MISSING=true ;;
      esac
    done <<< "$_out"

    # Extra system packages the pack declares (fuse2: a type-2 AppImage mounts
    # itself through libfuse2, and without it DuckStation exits with
    # "dlopen(): error loading libfuse.so.2" and the PS1 tile is dead).
    for _pkg in $(python3 "$GAMECORE_PATH/scripts/catalog-query.py" packages --select "$_id"); do
      pacman_optional "$_pkg"
    done
  done


  # ── Curated emulator configs (incl. controller bindings) ───────
  # -H so $HOME inside the script is the gaming user's, not root's: every
  # destination path in install-emu-configs.sh is derived from it.
  progress 56 "Emulator configs"
  msg "Emulator configs"
  if [ -d "$GAMECORE_PATH/catalog" ]; then
    sudo -u "$USER_NAME" -H env GAMECORE_PATH="$GAMECORE_PATH" \
      bash "$GAMECORE_PATH/install/install-emu-configs.sh" \
      && ok "Curated configs deployed." || warn "Config deployment failed."
  else
    warn "catalog/ not found — skipping."
  fi

  # ── Living-room applications ────────────────────────────────────
  # Every app selected in APPS, installed from its own pack. Unchecked means
  # nothing is cloned, written or enabled for it.
  progress 58 "Living-room applications"
  msg "Living-room applications"
  # One directory per app. catalog/<app>/ carries what the app needs — the
  # git checkouts beside it, its config, its user unit, its post-install
  # ceremonies — and the applier honours the declarations. This block used to
  # be ~230 lines of EmberTV, Firefox profiles, certutil and Stremio written
  # out by hand, next to packs that already declared all of it and that nothing
  # read: that gap is how install/firefox-profiles/ could be deleted by a
  # refactor and only surface on a fresh box, months later, at 66 %.
  #
  # Steam and Stremio ride this too — install_flatpak does the install, the
  # sandbox override and both uninstall manifests — so they are no longer part
  # of the emulator Flatpak loop above.
  UNIT_DIR="$USER_HOME/.config/systemd/user"
  # As the user, not as root. This was the one place in the script that created
  # something under $USER_HOME as root, and it created the whole chain — so on a
  # distribution whose /etc/skel has no .config (Arch vanilla) with an account
  # the installer had just made with `useradd -m`, ~/.config itself ended up
  # root:root 0755. The Electron shell keeps its profile in
  # ~/.config/gamecore-electron and gamecore-ui.service runs as the user, so it
  # could not write it: the service failed and looped on Restart=on-failure, and
  # the kiosk never started at all — while the installer printed "Installation
  # complete!". The chown further down deliberately covers only .config/systemd
  # (see the comment there), so it never repaired this.
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 755 "$UNIT_DIR/default.target.wants"
  # user services to (re)start once the user bus is up, filled from UNIT lines
  RESTART_UNITS=()

  APP_SEL=""
  for _app in $(python3 "$GAMECORE_PATH/scripts/catalog-query.py" ids --kind app); do
    want_app "$_app" && APP_SEL="$APP_SEL $_app"
  done
  if [[ -n "${APP_SEL// /}" ]]; then
    # Exported, never passed as arguments: /proc/<pid>/cmdline is world-readable
    # and one of these is a Twitch client secret. The pack names the keys it
    # wants under `secrets`; the applier reads only those.
    export TWITCH_CLIENT_ID TWITCH_CLIENT_SECRET TGDB_API_KEY \
           SS_DEV_ID SS_DEV_PASSWORD SS_USER SS_PASSWORD
    while IFS= read -r _line; do
      case "$_line" in
        OK*)   ok   "${_line#OK }" ;;
        SAME*) info "${_line#SAME }" ;;
        UNIT*) RESTART_UNITS+=("${_line#UNIT }") ;;
        FAIL*) warn "${_line#FAIL }" ;;
        *)     [[ -n "$_line" ]] && info "$_line" ;;
      esac
    done < <(python3 "$GAMECORE_PATH/scripts/gamecore-provider.py" install \
               --kind app --select "$APP_SEL" \
               --user "$USER_NAME" --user-home "$USER_HOME" \
               --gamecore-path "$GAMECORE_PATH" 2>&1 || true)
    unset TWITCH_CLIENT_ID TWITCH_CLIENT_SECRET
  else
    info "No living-room application selected."
  fi


  # Stremio is deliberately absent here: its interface reads the gamepad itself,
  # and its window is Wayland-native, which the bridge's X11 title detection
  # cannot see anyway. Only the Firefox kiosks need the translation.
  if want_app twitch || want_app youtube; then
  progress 64 "Gamepad TV bridge"
  # gamepad-tv-bridge — gamepad → keyboard for kiosk web apps
  if [ ! -d /opt/gamepad-tv-bridge ]; then
    git_clone https://github.com/p4v1c/gamepad-tv-bridge.git /opt/gamepad-tv-bridge \
      && ok "gamepad-tv-bridge cloned → /opt/gamepad-tv-bridge" || warn "gamepad-tv-bridge clone failed."
  else
    git_sync /opt/gamepad-tv-bridge "gamepad-tv-bridge"
  fi
  if [ -d /opt/gamepad-tv-bridge ]; then
    chown -R "${USER_NAME}:${USER_NAME}" /opt/gamepad-tv-bridge
    # ~/.venv is the most generic virtualenv path on Linux and the user may
    # already own one. Record whether WE created it, so the uninstaller knows
    # the difference between "delete this, it is ours" and "pip uninstall just
    # our package out of theirs".
    if [[ -d "$USER_HOME/.venv" ]]; then
      manifest_set BRIDGE_VENV_CREATED 0
    else
      sudo -u "$USER_NAME" -H python3 -m venv "$USER_HOME/.venv" 2>/dev/null \
        && manifest_set BRIDGE_VENV_CREATED 1 || manifest_set BRIDGE_VENV_CREATED 0
    fi
    sudo -u "$USER_NAME" -H "$USER_HOME/.venv/bin/pip" install -q -e /opt/gamepad-tv-bridge \
      && ok "bridge installed in $USER_HOME/.venv (editable)." || warn "bridge pip install failed."
    # WantedBy=default.target, NOT graphical-session.target: with linger the
    # user manager starts at boot (before any graphical login), so the bridge
    # comes up regardless of how the Plasma session starts; Restart=on-failure
    # covers the window where X isn't up yet.
    cat > "$UNIT_DIR/gamepad-tv-bridge.service" <<'EOF'
[Unit]
Description=Gamepad TV Bridge — gamepad to keyboard daemon

[Service]
Type=simple
Environment=DISPLAY=:0
ExecStart=%h/.venv/bin/python -m gamepad_bridge start
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
    ln -sf ../gamepad-tv-bridge.service "$UNIT_DIR/default.target.wants/gamepad-tv-bridge.service"
    rm -f "$UNIT_DIR/graphical-session.target.wants/gamepad-tv-bridge.service"
    RESTART_UNITS+=(gamepad-tv-bridge.service)
    ok "gamepad-tv-bridge.service installed (user unit)."
    # /dev/uinput access for key injection
    modprobe uinput 2>/dev/null || true
    echo "uinput" > /etc/modules-load.d/uinput.conf
    cat > /etc/udev/rules.d/99-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
    ok "uinput module + udev rule configured."
  fi
  fi  # twitch/youtube/stremio kiosk bridge

  # Only the directory we actually wrote into. A recursive chown of the whole
  # ~/.config silently rewrites the ownership of anything in there that
  # legitimately belonged to another uid, with no record and no way back.
  chown -R "${USER_NAME}:${USER_NAME}" "$USER_HOME/.config/systemd" 2>/dev/null || true

  # Record whether WE turned linger on, so the uninstaller does not switch it
  # off under a user who had it enabled for their own services.
  if loginctl show-user "$USER_NAME" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    manifest_set LINGER_ENABLED 0
  else
    loginctl enable-linger "$USER_NAME" 2>/dev/null \
      && { manifest_set LINGER_ENABLED 1; ok "user services will start at boot (linger)."; } || true
  fi

  # Make the freshly written user units effective NOW, not only after reboot:
  # the running user manager doesn't see manually symlinked units until a
  # daemon-reload, so embertv/gamepad-tv-bridge would stay dead post-install.
  USER_UID=$(id -u "$USER_NAME")
  if [ ${#RESTART_UNITS[@]} -gt 0 ]; then
    for i in $(seq 1 10); do [ -S "/run/user/$USER_UID/bus" ] && break; sleep 1; done
    if [ -S "/run/user/$USER_UID/bus" ]; then
      sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_UID" systemctl --user daemon-reload 2>/dev/null || true
      sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_UID" \
        systemctl --user restart "${RESTART_UNITS[@]}" 2>/dev/null \
        && ok "user services started: ${RESTART_UNITS[*]}." \
        || warn "user services will start at next boot."
    else
      warn "no user bus yet — ${RESTART_UNITS[*]} will start at next boot."
    fi
  fi

else
  msg "Minimal mode — skipping emulators, applications and configs."
fi

# ── Home-grid tiles (config/apps.json + config/systems.json) ─────
# An unchecked emulator or app must not leave a dead tile on the TV.
#
# Both files are regenerated from the pristine catalogues in install/*.dist
# on every run. Filtering in place used to be a one-way door: re-running the
# installer with MORE emulators selected could never bring back a tile a
# previous minimal run had deleted, because config/ is excluded from OTA and
# `cp -r` is skipped when the source already is the install dir. The .dist
# files live in install/, so they ride along with both the copy and the OTA
# rsync and stay current with each release.
progress 76 "Home-grid tiles"
msg "Home-grid tiles"
for pair in "apps.json" "systems.json"; do
  DIST="$GAMECORE_PATH/install/${pair}.dist"
  LIVE="$GAMECORE_PATH/config/${pair}"
  if [[ -f "$DIST" ]]; then
    # First run only: on a second pass $LIVE is already our generated file, and
    # overwriting the backup would lose the operator's hand-edited original.
    [[ -f "$LIVE" && ! -e "${LIVE}.bak-install" ]] && cp -f "$LIVE" "${LIVE}.bak-install"
    cp -f "$DIST" "$LIVE"
  else
    warn "install/${pair}.dist missing — filtering ${pair} in place."
  fi
done
# apps.json ships an @HOME@ token (it is generated from catalog/*/pack.json).
# The /home/pavic pass stays alongside it: a box upgrading from an older
# release still has the literal in its own config/apps.json, and config/ is
# excluded from the OTA rsync, so nothing else would ever fix it.
sed -i -e "s|@HOME@|$USER_HOME|g" -e "s|/home/pavic|$USER_HOME|g" \
  "$GAMECORE_PATH/config/apps.json"

KEEP_APPS=""
for app in $(python3 "$GAMECORE_PATH/scripts/catalog-query.py" ids --kind app); do
  want_app "$app" && KEEP_APPS="$KEEP_APPS $app"
done
python3 - "$GAMECORE_PATH/config/apps.json" $KEEP_APPS <<'EOF'
import json, sys
path, keep = sys.argv[1], set(sys.argv[2:])
apps = json.load(open(path))
kept = [a for a in apps if a.get("id") in keep]
if len(kept) != len(apps):
    json.dump(kept, open(path, "w"), indent=2, ensure_ascii=False)
removed = [a.get("id") for a in apps if a.get("id") not in keep]
print(f"[app-tiles] kept: {', '.join(sorted(keep)) or 'none'}"
      + (f" — removed: {', '.join(removed)}" if removed else ""))
EOF
ok "apps.json filtered to the selected apps."

# systems.json: rewrite the launchers to what this box actually has, and drop
# the systems that were not selected. In minimal mode nothing is installed,
# so the emulator half of the grid goes entirely.
progress 78 "Systems → launchers"
if [[ "$MODE" == "minimal" ]]; then
  EMU_SEL=""
else
  EMU_SEL="$EMULATORS"
fi
bash "$GAMECORE_PATH/install/flatpakify-systems.sh" "$GAMECORE_PATH" "$EMU_SEL" \
  && ok "systems.json adapted to the selected emulators." \
  || warn "flatpakify failed — check config/systems.json."
chown "${USER_NAME}:${USER_NAME}" \
  "$GAMECORE_PATH/config/apps.json" "$GAMECORE_PATH/config/systems.json" 2>/dev/null || true

# ── ROM directories ──────────────────────────────────────────────
progress 80 "ROM directories"
msg "ROM directories"
# From the catalogue: every pack declares its own roms.dir, so adding an
# emulator no longer means remembering to add a line here too. `covers` is not
# a system — it is where the cover pipeline caches art.
for d in $(python3 "$GAMECORE_PATH/scripts/catalog-query.py" rom-dirs) covers; do
  sudo -u "$USER_NAME" mkdir -p "$GAMECORE_PATH/emu/$d"
done
ok "ROM directories ready."

# ── Input group + udev rule (needed for evdev PS-button detection) ──
progress 82 "Gamepad input access"
msg "Gamepad input access"
# Record whether the membership is ours. `input` is required by plenty of
# unrelated software (Steam, retroarch, ydotool), so an uninstaller must not
# revoke it from a user who already had it.
if id -nG "$USER_NAME" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
  manifest_set INPUT_GROUP_ADDED 0
  ok "$USER_NAME already in the 'input' group."
elif usermod -aG input "$USER_NAME"; then
  manifest_set INPUT_GROUP_ADDED 1
  ok "$USER_NAME added to 'input' group."
else
  warn "Could not add to input group."
fi

# udev rule: make all gamepad/joystick event nodes group=input + world-readable
# This means the backend process can open them even before a re-login
cat > /etc/udev/rules.d/99-gamecore-input.rules <<'UDEV'
# GameCore — allow reading gamepad events for PS/guide button detection.
#
# MODE is 0660, never 0664: the second rule matches EVERY USB HID interface,
# which includes keyboards. World-readable /dev/input/event* would let any
# local uid — the caddy service user, any SSH session — read every keystroke
# on the machine, sudo passwords included. Group `input` is enough: the
# backend unit has SupplementaryGroups=input and the desktop user is a member.
KERNEL=="event*", SUBSYSTEM=="input", ATTRS{bInterfaceClass}=="03", MODE="0660", GROUP="input"
# Sony DualShock / DualSense (vendor 054c) — kept unconditional: a DualShock
# over Bluetooth does not always tag every child node as a joystick.
SUBSYSTEM=="input", ATTRS{idVendor}=="054c", MODE="0660", GROUP="input"
UDEV

# DualShock 4 over hidraw — needed by RPCS3's native DS4 pad handler
# (rumble, motion, correct mapping) over USB and Bluetooth.
cat > /etc/udev/rules.d/99-ds4-controllers.rules <<'UDEV'
# DualShock 4 over USB
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="05c4", MODE="0666"
# DualShock 4 Wireless Adapter over USB
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ba0", MODE="0666"
# DualShock 4 Slim over USB
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="09cc", MODE="0666"
# DualShock 4 over Bluetooth
KERNEL=="hidraw*", KERNELS=="*054C:05C4*", MODE="0666"
# DualShock 4 Slim over Bluetooth
KERNEL=="hidraw*", KERNELS=="*054C:09CC*", MODE="0666"
UDEV
ok "DualShock 4 hidraw rules installed."

udevadm control --reload-rules 2>/dev/null && udevadm trigger 2>/dev/null && ok "udev rules reloaded." || warn "udev reload failed — reconnect controller."

# ── Addon manager ────────────────────────────────────────────────
progress 84 "Addon manager"
msg "Addon manager (gamecore-addon)"
install -m 755 "$GAMECORE_PATH/install/gamecore-addon" /usr/local/bin/gamecore-addon
# Pre-create the addons checkout dir owned by the user so `gamecore-addon
# install` never needs root for user-level addons.
install -d -o "$USER_NAME" -g "$USER_NAME" /opt/gamecore-addons
ok "gamecore-addon CLI installed (addons live in /opt/gamecore-addons)."

# ── Python backend ───────────────────────────────────────────────
progress 86 "Python backend (venv)"
msg "Python backend (venv)"
sudo -u "$USER_NAME" -H python3 -m venv "$GAMECORE_PATH/.venv"
sudo -u "$USER_NAME" -H "$GAMECORE_PATH/.venv/bin/pip" install -q -r "$GAMECORE_PATH/backend/requirements.txt"
ok "Python dependencies installed."

# ── LAN login password (enforced by Caddy — see docs/SECURITY.md) ─
if [[ -f "$GAMECORE_PATH/config/auth.json" ]]; then
  ok "Web password already set — kept (reset: gamecore-addon auth-reset)."
else
  msg "Web access password (login at https://${LOCAL_IP}:8443)"
  WEB_PASSWORD="${WEB_PASSWORD:-}"
  if ! $UNATTENDED; then
    while true; do
      read -rsp "  Web password (cannot be empty) : " WEB_PASSWORD; echo
      [[ -n "$WEB_PASSWORD" ]] || { warn "Empty password refused."; continue; }
      read -rsp "  Confirm                        : " WEB_PASSWORD2; echo
      [[ "$WEB_PASSWORD" == "$WEB_PASSWORD2" ]] && break
      warn "Passwords differ — try again."
    done
  fi
  if [[ -n "$WEB_PASSWORD" ]]; then
    WEB_PASSWORD="$WEB_PASSWORD" GAMECORE_PATH="$GAMECORE_PATH" \
      "$GAMECORE_PATH/.venv/bin/python3" - <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["GAMECORE_PATH"])
from backend.services import auth
auth.set_password(os.environ["WEB_PASSWORD"])
PYEOF
    chown "$USER_NAME:$USER_NAME" "$GAMECORE_PATH/config/auth.json" "$GAMECORE_PATH/config/auth_secret"
    ok "Web password set (config/auth.json, survives OTA updates)."
  else
    warn "No WEB_PASSWORD in conf — LAN stays locked; run 'gamecore-addon auth-reset'."
  fi
fi


# ── systemd service ──────────────────────────────────────────────
progress 88 "systemd services"
msg "systemd service"

cat > /etc/systemd/system/gamecore-backend.service <<EOF
[Unit]
Description=GameCore — FastAPI Backend
After=network.target display-manager.service

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
SupplementaryGroups=input
Environment=GAMECORE_PATH=$GAMECORE_PATH
Environment=GAMECORE_BACKEND_PORT=$WEB_PORT
WorkingDirectory=$GAMECORE_PATH
# Wait for a display that ANSWERS, not merely for a socket to exist.
#
# The backend used to win the boot race against X on every cold boot: it
# started at 14:56:19 on the reference box, main.py's lifespan reached
# standby.resume_after_restart() → xset → the X probe at 14:56:20, and the
# first socket only appeared at 14:56:22.8 — :1, the one that answers there,
# at 14:56:24.3. Every emulator then launched against the wrong display and
# died instantly, until someone restarted the service.
#
# Waiting for a socket is not enough, which is why this differs from the UI
# unit's check: on that same boot X0 appeared 1.5 s before X1, so a socket
# test would have passed while the only usable display still did not exist.
# Each socket is tried with each cookie location — the same three the probe in
# process_manager.py knows about.
#
# Always exits 0: a box with no X at all (headless, SSH install) must still get
# its backend. The bound is 20 s, and process_manager retries the probe anyway,
# so this is ordering — not a correctness dependency.
ExecStartPre=/bin/bash -c 'command -v xdpyinfo >/dev/null || exit 0; for i in \$(seq 1 20); do for s in /tmp/.X11-unix/X*; do [ -S "\$s" ] || continue; for c in /run/user/\$(id -u)/xauth_* /tmp/xauth_* "\$HOME/.Xauthority" ""; do DISPLAY=":\${s##*/X}" XAUTHORITY="\$c" xdpyinfo >/dev/null 2>&1 && exit 0; done; done; sleep 1; done; exit 0'
ExecStart=$GAMECORE_PATH/.venv/bin/python3 -m uvicorn backend.main:app --host 127.0.0.1 --port $WEB_PORT
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Scraper credentials — one drop-in, mode 600, outside the repo. They are
# secrets: THEGAMESDB_API_KEY is a key, and the four ScreenScraper values are
# two accounts, one of which (the developer one) is shared by every user of the
# same softname and gets revoked if it leaks.
#
# Written as a single file rather than one per key: two drop-ins with the same
# name overwrite each other, and two different names are two places to look when
# a scrape stops working.
if [[ -n "$TGDB_API_KEY" || -n "$SS_DEV_ID" ]]; then
  mkdir -p /etc/systemd/system/gamecore-backend.service.d
  {
    echo "[Service]"
    [[ -n "$TGDB_API_KEY"    ]] && echo "Environment=THEGAMESDB_API_KEY=$TGDB_API_KEY"
    # Quoted: a ScreenScraper password may contain spaces, and systemd would
    # otherwise cut the value at the first one.
    [[ -n "$SS_DEV_ID"       ]] && echo "Environment=\"SCREENSCRAPER_DEV_ID=$SS_DEV_ID\""
    [[ -n "$SS_DEV_PASSWORD" ]] && echo "Environment=\"SCREENSCRAPER_DEV_PASSWORD=$SS_DEV_PASSWORD\""
    [[ -n "$SS_USER"         ]] && echo "Environment=\"SCREENSCRAPER_USER=$SS_USER\""
    [[ -n "$SS_PASSWORD"     ]] && echo "Environment=\"SCREENSCRAPER_PASSWORD=$SS_PASSWORD\""
  } > /etc/systemd/system/gamecore-backend.service.d/override.conf
  chmod 600 /etc/systemd/system/gamecore-backend.service.d/override.conf
  [[ -n "$TGDB_API_KEY" ]] && ok "TheGamesDB API key configured (local drop-in, never in git)."
  if [[ -n "$SS_DEV_ID" ]]; then
    ok "ScreenScraper credentials configured (local drop-in, never in git)."
    [[ -n "$SS_USER" ]] || warn "No ScreenScraper member account: the developer credentials alone give a level-0 quota."
  fi
fi

cat > /etc/systemd/system/gamecore-ui.service <<EOF
[Unit]
Description=GameCore — Electron UI
After=display-manager.service gamecore-backend.service
Requires=gamecore-backend.service

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
Environment=GAMECORE_PATH=$GAMECORE_PATH
Environment=GAMECORE_BACKEND_PORT=$WEB_PORT
WorkingDirectory=$GAMECORE_PATH
# Wait for an X server socket to exist, nothing more: start-ui.sh does the real
# display/cookie resolution and knows about all three cookie locations. The old
# version searched only /run/user/<uid>/xauth_*, which is where kwin_wayland
# puts the Xwayland cookie — SDDM's X11 session writes /tmp/xauth_XXXXXX, so it
# waited 60 s, found nothing, and Electron crash-looped.
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 60); do compgen -G "/tmp/.X11-unix/X*" >/dev/null && exit 0; sleep 1; done; exit 0'
ExecStart=$GAMECORE_PATH/electron/start-ui.sh
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOF

# ── SDDM auto-login ──────────────────────────────────────────────
progress 90 "SDDM auto-login (openbox kiosk)"
msg "SDDM auto-login"
# The kiosk logs into an openbox X session. The stack (overlays, fullscreen
# enforcer, gamepad-tv-bridge key injection, gamecore-xsetup) is X11-only, and
# openbox gives exactly that with nothing else attached — see the package block
# above for why this is no longer Plasma's X11 session.
if [ -f /usr/share/xsessions/openbox.desktop ]; then
  KIOSK_SESSION="openbox"
else
  KIOSK_SESSION=""
fi

if [[ -z "$KIOSK_SESSION" ]]; then
  warn "No openbox session in /usr/share/xsessions — auto-login NOT configured."
  warn "  GameCore cannot run on Wayland (overlays, fullscreen enforcer and the"
  warn "  gamepad bridge are all X11). Install it and re-run:"
  warn "      sudo pacman -S openbox && sudo bash install/arch.sh"
else
  mkdir -p /etc/sddm.conf.d
  # The filename matters. SDDM reads /etc/sddm.conf.d/* in name order and the
  # LAST file wins. Manjaro Plasma ships kde_settings.conf, which carries its
  # own [Autologin] with Session=plasma — the WAYLAND session — and 'k' sorts
  # after 'a', so a drop-in called autologin.conf is silently overridden and
  # the box boots into Wayland with the kiosk never starting. 'zz-' sorts last.
  rm -f /etc/sddm.conf.d/autologin.conf /etc/sddm.conf.d/gamecore-display.conf \
        /etc/sddm.conf.d/zz-gamecore-openbox.conf
  cat > /etc/sddm.conf.d/zz-gamecore-autologin.conf <<EOF
[Autologin]
User=$USER_NAME
Session=$KIOSK_SESSION
Relogin=true
EOF

  # Sort order alone is not enough: the Login Screen KCM rewrites
  # kde_settings.conf whenever someone opens it, and a future KDE could name
  # its file something that sorts after 'zz'. Strip the competing keys, and
  # keep a backup so the uninstaller can put the user's own autologin back.
  KDE_SDDM_CONF=/etc/sddm.conf.d/kde_settings.conf
  # The backup lives with the manifest, NOT next to the original: SDDM reads
  # every file in /etc/sddm.conf.d/ regardless of extension, so a .pre-gamecore
  # copy left there would itself be parsed as configuration.
  KDE_SDDM_BACKUP="${MANIFEST_DIR}/kde_settings.conf.pre-gamecore"
  if [[ -f "$KDE_SDDM_CONF" ]] && grep -q '^\[Autologin\]' "$KDE_SDDM_CONF"; then
    mkdir -p "$MANIFEST_DIR"
    [[ -f "$KDE_SDDM_BACKUP" ]] || cp "$KDE_SDDM_CONF" "$KDE_SDDM_BACKUP"
    manifest_set KDE_SDDM_BACKUP "$KDE_SDDM_BACKUP"
    python3 - "$KDE_SDDM_CONF" <<'PY'
import sys
path = sys.argv[1]
out, in_autologin = [], False
for line in open(path, encoding="utf-8", errors="replace"):
    stripped = line.strip()
    if stripped.startswith("["):
        in_autologin = stripped.lower() == "[autologin]"
    elif in_autologin and stripped.split("=", 1)[0].strip() in ("User", "Session", "Relogin"):
        continue          # GameCore's zz- drop-in owns these now
    out.append(line)
open(path, "w", encoding="utf-8").writelines(out)
PY
    manifest_set KDE_SDDM_CONF_PATCHED 1
    ok "Competing [Autologin] keys removed from kde_settings.conf (backup kept)."
  fi
  ok "SDDM configured for auto-login as $USER_NAME (openbox X11 session: $KIOSK_SESSION)."
fi

# Force 1920x1080 at the display-server level (never 4K). SDDM runs this as
# root at X startup, before any session, so the whole X server — kiosk, games
# and overlays — is pinned to 1080p. See install/gamecore-xsetup.sh.
# (start-ui.sh re-applies it inside the session, after KScreen has had its say.)
install -m755 "$GAMECORE_PATH/install/gamecore-xsetup.sh" /usr/local/bin/gamecore-xsetup

# The desktop escape hatch. The box auto-logs into openbox, which hosts the
# kiosk and nothing else; this is how someone gets to a real desktop for the
# ten minutes a year they need one, without editing SDDM drop-ins as root and
# without leaving gamecore-ui drawing the kiosk over it.
install -m755 "$GAMECORE_PATH/install/gamecore-session-select" /usr/local/bin/gamecore-session-select
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/zz-gamecore-display.conf <<EOF
[X11]
DisplayCommand=/usr/local/bin/gamecore-xsetup
EOF
ok "Display pinned to 1920x1080 (SDDM DisplayCommand)."

systemctl daemon-reload
systemctl enable sddm.service
systemctl enable gamecore-backend.service
systemctl enable gamecore-ui.service
ok "Services enabled."

# ── Caddy reverse-proxy — the only GameCore port exposed to the LAN ──
msg "Caddy reverse-proxy (HTTPS :8443)"
# Catch-all site + on-demand internal certs: no per-box templating for the
# *address*, so the box can change IP/network without touching this file.
# The backend port IS templated: the shipped Caddyfile says 8765 everywhere
# and a box installed on another port would 502 on every LAN request.
mkdir -p /etc/caddy
# "Was Caddy already serving something of the user's?" — deliberately NOT
# `systemctl is-active` and NOT "the file exists":
#   · the caddy package OWNS /etc/caddy/Caddyfile, so on a fresh install the
#     stock file is always there. Treating it as the user's site made every
#     clean install print a scary "an existing Caddyfile was saved" and, worse,
#     made the uninstaller leave caddy enabled with its CA private key on disk.
#   · is-active is true on the SECOND run of this idempotent installer, because
#     the first run started it — so GameCore would record its own service as
#     pre-existing.
# Ours iff we just installed the package, or the file is the packaged default.
CADDY_PREEXISTING=false
if ! grep -qxF caddy "$PKG_MANIFEST" 2>/dev/null \
   && [[ -f /etc/caddy/Caddyfile ]] \
   && ! grep -q 'GameCore' /etc/caddy/Caddyfile \
   && pacman -Qkk caddy 2>/dev/null | grep -q '/etc/caddy/Caddyfile'; then
  # caddy predates this install AND its config has been modified by someone.
  CADDY_PREEXISTING=true
  CADDY_BACKUP="/etc/caddy/Caddyfile.pre-gamecore"
  [[ -e "$CADDY_BACKUP" ]] || cp /etc/caddy/Caddyfile "$CADDY_BACKUP"
  manifest_set CADDYFILE_BACKUP "$CADDY_BACKUP"
  warn "An existing /etc/caddy/Caddyfile was saved as $CADDY_BACKUP."
fi
$CADDY_PREEXISTING && manifest_set CADDY_WAS_ACTIVE active \
                   || manifest_set CADDY_WAS_ACTIVE inactive
sed "s|127\.0\.0\.1:8765|127.0.0.1:${WEB_PORT}|g" \
  "$GAMECORE_PATH/install/Caddyfile" > /etc/caddy/Caddyfile
systemctl enable caddy.service
# restart, not `enable --now`: on a re-run caddy is already active and
# `--now` is a no-op, so it would keep serving the previous config.
systemctl restart caddy.service || warn "caddy failed to start — check /etc/caddy/Caddyfile"
# Install Caddy's root CA into the system trust store so the box itself
# (kiosk browser, Firefox) gets no TLS warning. `caddy trust` needs the
# admin API of the freshly started service — retry while it comes up.
CADDY_TRUSTED=0
for _ in $(seq 1 15); do
  if caddy trust >/dev/null 2>&1; then CADDY_TRUSTED=1; break; fi
  sleep 1
done
if [[ $CADDY_TRUSTED -eq 1 ]]; then
  ok "Caddy up on :8443 — root CA installed in the system trust store."
else
  warn "Caddy started but 'caddy trust' failed — run 'sudo caddy trust' once."
fi

# ── Bluetooth ────────────────────────────────────────────────────
progress 92 "Bluetooth, power & desktop launcher"
msg "Bluetooth"
systemctl enable --now bluetooth.service
ok "Bluetooth service enabled."

# ── Power management (reboot/shutdown from UI) ───────────────────
msg "Sudoers — power management"
cat > /etc/sudoers.d/gamecore-power <<EOF
$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot
# Gamepad hotplug (backend/routers/games.py) — the only udevadm this needs.
# Enumerated like the governor rule below: unrestricted, it also granted
# `udevadm control`, which reloads and can replace the device rules.
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/udevadm trigger
# Desktop escape hatch — switch auto-login between the openbox kiosk and the
# machine's desktop. Enumerated with its two arguments rather than left open:
# the script writes an SDDM drop-in as root, so "any argument" is not a thing
# to hand out.
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/gamecore-session-select gamecore, /usr/local/bin/gamecore-session-select desktop
# Desktop launcher (gamecore-launcher.sh) — start GameCore from the desktop
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl start gamecore-backend.service, /usr/bin/systemctl start gamecore-ui.service
# Standby (backend/services/standby.py) — drop the governor while the screen
# is off. Enumerated, not wildcarded: only the two governors GameCore uses.
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/cpupower frequency-set -g powersave, /usr/bin/cpupower frequency-set -g performance
EOF
chmod 440 /etc/sudoers.d/gamecore-power
if visudo -cf /etc/sudoers.d/gamecore-power >/dev/null; then
  ok "Sudoers rules created (power + udevadm + governor + GameCore start for $USER_NAME)."
else
  rm -f /etc/sudoers.d/gamecore-power
  warn "sudoers validation failed — power menu and standby governor will not work."
fi

# ── Desktop launcher (clickable "GameCore" icon) ─────────────────
msg "Desktop launcher"
chmod +x "$GAMECORE_PATH/install/gamecore-launcher.sh"
DESKTOP_DIR=$(sudo -u "$USER_NAME" bash -lc 'xdg-user-dir DESKTOP 2>/dev/null' || true)
[[ -n "$DESKTOP_DIR" && -d "$DESKTOP_DIR" ]] || DESKTOP_DIR="$USER_HOME/Desktop"
APPS_DIR="$USER_HOME/.local/share/applications"
sudo -u "$USER_NAME" mkdir -p "$DESKTOP_DIR" "$APPS_DIR"
LAUNCHER_DESKTOP="[Desktop Entry]
Type=Application
Name=GameCore
Comment=Lancer l'interface GameCore
Exec=$GAMECORE_PATH/install/gamecore-launcher.sh
Icon=input-gaming
Terminal=true
Categories=Game;"
echo "$LAUNCHER_DESKTOP" | sudo -u "$USER_NAME" tee "$APPS_DIR/gamecore.desktop" >/dev/null
echo "$LAUNCHER_DESKTOP" | sudo -u "$USER_NAME" tee "$DESKTOP_DIR/GameCore.desktop" >/dev/null
sudo -u "$USER_NAME" chmod +x "$DESKTOP_DIR/GameCore.desktop"
# KDE: mark the desktop file as trusted so it runs on click without a warning
sudo -u "$USER_NAME" gio set "$DESKTOP_DIR/GameCore.desktop" metadata::trusted true 2>/dev/null || true
ok "Desktop launcher installed ($DESKTOP_DIR/GameCore.desktop)."

# OTA update: detached restart unit + narrow sudoers rule
bash "$GAMECORE_PATH/install/setup-update-permissions.sh" "$USER_NAME" \
  && ok "OTA restart permissions installed." || warn "OTA restart setup failed."

# ── SSH ──────────────────────────────────────────────────────────
msg "SSH"
systemctl enable --now sshd
ok "SSH active."

# ── Node / frontend + Electron ───────────────────────────────────
# Deliberately the LAST thing before addons. Both steps pull ~150 MB
# from the network (npm registry + the Electron binary from GitHub) and
# are by far the most likely to fail on a flaky connection. When they ran
# earlier, a single failed download aborted the script under `set -e`
# before a single systemd unit, sudoers rule, udev rule, Caddyfile or
# autologin drop-in existed — leaving a machine with packages installed
# and nothing wired up. Now everything system-facing is already in place
# and a re-run only has to redo this part.
# ── Node / frontend ──────────────────────────────────────────────
progress 93 "Building the frontend"
msg "Node frontend build"
cd "$GAMECORE_PATH/frontend"
sudo -u "$USER_NAME" -H npm install
sudo -u "$USER_NAME" -H npm run build
cd "$SCRIPT_DIR"
ok "Frontend built → frontend/dist/"

# ── Electron ─────────────────────────────────────────────────────
progress 96 "Electron shell"
msg "Electron shell"
cd "$GAMECORE_PATH/electron"
# `|| warn`, not a hard failure: the electron package downloads a ~100 MB
# binary from GitHub in its postinstall, and a transient failure there used to
# abort the install. The explicit provisioning below exists precisely to
# recover from a missing binary — so let control reach it.
sudo -u "$USER_NAME" -H npm install \
  || warn "npm install reported an error — trying explicit Electron provisioning."

# The electron npm package downloads its actual binary from a postinstall
# script (node install.js). On machines with hardened npm (ignore-scripts,
# @lavamoat/allow-scripts, …) that step is silently skipped, leaving
# node_modules/electron with no binary → "Electron failed to install
# correctly" at runtime. Provision the binary explicitly so the install never
# depends on the postinstall running.
ELECTRON_DIR="$GAMECORE_PATH/electron/node_modules/electron"
if [[ ! -x "$ELECTRON_DIR/dist/electron" ]]; then
  warn "Electron binary missing (npm postinstall was skipped) — downloading it directly."
  # `EV=$(…)` under set -e exits on failure BEFORE its own `|| die` can run, so
  # the version lookup is guarded rather than chained. When npm died early
  # there is no node_modules/electron/package.json at all: fall back to the
  # major pinned in electron/package.json.
  EV=""
  if [[ -f "$ELECTRON_DIR/package.json" ]]; then
    EV="$(sudo -u "$USER_NAME" -H node -p "require('$ELECTRON_DIR/package.json').version" 2>/dev/null || true)"
  fi
  if [[ -z "$EV" ]]; then
    EV="$(python3 -c '
import json, re, sys
spec = json.load(open(sys.argv[1]))["dependencies"]["electron"]
m = re.search(r"[0-9][0-9.]*", spec)
print(m.group(0) if m else "")
' "$GAMECORE_PATH/electron/package.json" 2>/dev/null || true)"
    [[ -n "$EV" ]] && warn "Electron version taken from package.json: $EV"
  fi
  [[ -n "$EV" ]] || die "Could not determine the Electron version — re-run the installer once the network is back."
  case "$(uname -m)" in
    x86_64)  EARCH=x64 ;;
    aarch64) EARCH=arm64 ;;
    armv7l)  EARCH=armv7l ;;
    *)       EARCH=x64 ;;
  esac
  EZIP="electron-v${EV}-linux-${EARCH}.zip"
  EURL="https://github.com/electron/electron/releases/download/v${EV}/${EZIP}"
  TMPDIR_E="$(mktemp -d)"
  info "Downloading $EZIP …"
  # Download AND extract as root (root owns TMPDIR_E); chown the result to the
  # user afterwards. Doing the extract as the user fails because it cannot read
  # root's mktemp dir.
  if curl -fL --connect-timeout 15 --speed-limit 1024 --speed-time 30 -o "$TMPDIR_E/$EZIP" "$EURL"; then
    mkdir -p "$ELECTRON_DIR/dist"
    if bsdtar -xf "$TMPDIR_E/$EZIP" -C "$ELECTRON_DIR/dist" 2>/dev/null \
       || unzip -oq "$TMPDIR_E/$EZIP" -d "$ELECTRON_DIR/dist"; then
      # printf (not echo) — a trailing newline in path.txt makes Electron spawn
      # "…/dist/electron\n" → ENOENT.
      printf electron > "$ELECTRON_DIR/path.txt"
      chown -R "$USER_NAME:$USER_NAME" "$ELECTRON_DIR"
      ok "Electron $EV binary installed → dist/."
    else
      die "Failed to extract the Electron binary (install 'libarchive' for bsdtar, or 'unzip')."
    fi
  else
    die "Failed to download Electron $EV from GitHub — check the machine's network."
  fi
  rm -rf "$TMPDIR_E"
fi

# start-ui.sh execs node_modules/.bin/electron. That symlink is created by npm,
# so it is missing exactly when the binary had to be provisioned by hand above —
# the unit would then fail with "No such file or directory" on every boot.
if [[ -x "$ELECTRON_DIR/cli.js" || -f "$ELECTRON_DIR/cli.js" ]] \
   && [[ ! -e "$GAMECORE_PATH/electron/node_modules/.bin/electron" ]]; then
  mkdir -p "$GAMECORE_PATH/electron/node_modules/.bin"
  ln -sf ../electron/cli.js "$GAMECORE_PATH/electron/node_modules/.bin/electron"
  chmod +x "$ELECTRON_DIR/cli.js"
  chown -h "$USER_NAME:$USER_NAME" "$GAMECORE_PATH/electron/node_modules/.bin/electron"
  ok "node_modules/.bin/electron symlink restored."
fi

# chrome-sandbox must be a root-owned SUID binary, otherwise Electron refuses
# to start under an unprivileged user on some setups. Do this AFTER the
# chown -R above, which would otherwise hand it back to the user.
if [[ -f "$ELECTRON_DIR/dist/chrome-sandbox" ]]; then
  chown root:root "$ELECTRON_DIR/dist/chrome-sandbox"
  chmod 4755 "$ELECTRON_DIR/dist/chrome-sandbox"
fi
cd "$SCRIPT_DIR"
ok "Electron dependencies installed."

# ── Addons ───────────────────────────────────────────────────────
# Selected gamecore-addons modules (rom-manager by default — everyone
# wants the browser ROM upload). Each runs as a user-level service.
if [[ -n "$ADDONS" ]]; then
  progress 98 "Addons ($ADDONS)"
  msg "Addons ($ADDONS)"
  USER_UID=$(id -u "$USER_NAME")
  if loginctl show-user "$USER_NAME" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    grep -q '^LINGER_ENABLED=' "$MANIFEST" 2>/dev/null || manifest_set LINGER_ENABLED 0
  else
    loginctl enable-linger "$USER_NAME" 2>/dev/null && manifest_set LINGER_ENABLED 1 || true
  fi
  # systemctl --user needs the user manager's bus — wait for it briefly
  for i in $(seq 1 10); do [ -S "/run/user/$USER_UID/bus" ] && break; sleep 1; done
  for addon in $ADDONS; do
    if sudo -u "$USER_NAME" \
         env GAMECORE_PATH="$GAMECORE_PATH" GAMECORE_BACKEND_PORT="$WEB_PORT" \
             XDG_RUNTIME_DIR="/run/user/$USER_UID" \
         /usr/local/bin/gamecore-addon install "$addon"; then
      ok "addon '$addon' installed."
    else
      warn "addon '$addon' failed — run later: gamecore-addon install $addon"
    fi
  done
fi

# ── Final summary ────────────────────────────────────────────────
progress 100 "Installation complete"
echo
echo -e "${BLU}╔══════════════════════════════════════╗${RST}"
echo -e "${BLU}║     Installation complete!           ║${RST}"
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"
echo
ok "Web (LAN)     → https://${LOCAL_IP}:8443/roms  (login required)"
ok "Backend API   → http://127.0.0.1:${WEB_PORT}  (loopback only)"
ok "SSH           → ssh ${USER_NAME}@${LOCAL_IP}"
echo
echo -e "${YLW}  Next steps:${RST}"
echo "  1. Reboot — GameCore launches automatically."
echo "  2. Upload ROMs at https://${LOCAL_IP}:8443/roms  (drag & drop)"
echo "  3. Only manual step left: copy BIOS/firmwares (PS1/PS2/PS3, DS/3DS, Switch keys)."
echo
if [[ -z "${KIOSK_SESSION:-}" ]]; then
  warn "No openbox X11 session was configured — GameCore will NOT start after the reboot."
  warn "  Run: sudo pacman -S openbox && sudo bash install/arch.sh"
  echo
fi
if $NVIDIA_REBOOT_NEEDED; then
  warn "NVIDIA driver installed — the reboot is mandatory before the X11 session works."
  echo
fi
# Surfaced here on purpose: these warnings scroll past in the middle of a very
# long log, and the only other symptom is a tile that has quietly disappeared
# from the grid.
if $DUCK_MISSING; then
  warn "DuckStation (PlayStation) was NOT installed — its tile is missing from the grid."
  warn "  Re-run this installer to retry the download, or drop the AppImage yourself at:"
  warn "      $GAMECORE_PATH/bin/duckstation.AppImage   (chmod +x, then re-run the installer)"
  echo
fi
if $XENIA_MISSING; then
  warn "Xenia Canary (Xbox 360) was NOT installed — its tile is missing from the grid."
  warn "  Re-run this installer to retry the download, or extract the release yourself into:"
  warn "      $GAMECORE_PATH/lib/xenia/   (xenia_canary.exe at its root, then re-run)"
  echo
fi
echo -e "${YLW}  To remove GameCore later:${RST}"
echo "  sudo bash $GAMECORE_PATH/install/uninstall.sh --dry-run   # see what would go"
echo "  sudo bash $GAMECORE_PATH/install/uninstall.sh             # ROMs and config kept"
echo
