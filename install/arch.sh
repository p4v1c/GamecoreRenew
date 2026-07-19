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
echo
if ! $UNATTENDED; then
  read -rp "  Continue? (y/N) " CONFIRM
  [[ "$CONFIRM" =~ ^[yY]$ ]] || die "Aborted."
fi

# ── User check ───────────────────────────────────────────────────
progress 2 "Checking user"
msg "Checking user"
id "$USER_NAME" >/dev/null 2>&1 || { useradd -m -s /bin/bash "$USER_NAME"; ok "User $USER_NAME created."; }
ok "User $USER_NAME OK"
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)

# ── Copy files ───────────────────────────────────────────────────
progress 4 "Copying GameCore files"
msg "Setting up $GAMECORE_PATH"
mkdir -p "$(dirname "$GAMECORE_PATH")"
if [ "$PROJECT_ROOT" != "$GAMECORE_PATH" ]; then
  cp -r "$PROJECT_ROOT/." "$GAMECORE_PATH"
  ok "Copied $PROJECT_ROOT → $GAMECORE_PATH"
else
  ok "Already in place."
fi
chown -R "${USER_NAME}:${USER_NAME}" "$GAMECORE_PATH"

# ── System packages ──────────────────────────────────────────────
progress 6 "System packages (pacman) — this can take a while"
msg "System packages"
pacman -Syu --noconfirm

PKGS=(
  mesa
  base-devel git flatpak openssh
  python python-pip
  nodejs npm
  plasma-desktop sddm xorg-xdpyinfo xorg-xrandr xorg-xset unclutter
  bluez bluez-utils
  caddy
)

# GPU drivers — detect the vendor instead of assuming AMD
GPU_INFO=$(lspci -nn 2>/dev/null | grep -Ei 'vga|3d|display' || true)
if echo "$GPU_INFO" | grep -qiE 'amd|radeon'; then
  PKGS+=(xf86-video-amdgpu vulkan-radeon lib32-vulkan-radeon)
  info "GPU detected: AMD (vulkan-radeon)"
elif echo "$GPU_INFO" | grep -qi 'intel'; then
  PKGS+=(vulkan-intel lib32-vulkan-intel)
  info "GPU detected: Intel (vulkan-intel)"
elif echo "$GPU_INFO" | grep -qi 'nvidia'; then
  PKGS+=(nvidia nvidia-utils lib32-nvidia-utils)
  info "GPU detected: NVIDIA (proprietary driver)"
elif echo "$GPU_INFO" | grep -qiE 'vmware|virtualbox|virtio|qxl|bochs'; then
  # VM GPU — no hardware Vulkan; llvmpipe lets Vulkan apps at least start.
  PKGS+=(vulkan-swrast)
  info "GPU detected: virtual machine (software Vulkan via llvmpipe)"
else
  warn "GPU not identified — installing mesa only (add your Vulkan driver manually)."
fi

# Kernel headers
KERNEL=$(uname -r)
if $IS_MANJARO; then
  KSHORT=$(echo "$KERNEL" | grep -oP '^\d+\.\d+' | tr -d '.')
  PKGS+=("linux${KSHORT}-headers")
else
  [[ $KERNEL == *zen* ]] && PKGS+=("linux-zen-headers") || PKGS+=("linux-headers")
fi

pacman -S --noconfirm --needed "${PKGS[@]}"
ok "System packages installed."

pacman_optional cpupower
pacman_optional amd-ucode
pacman_optional feh
# Plasma 6 ships the X11 session in a separate package on recent Arch/Manjaro;
# on older Plasma the X11 session is built in and this package doesn't exist.
pacman_optional plasma-x11-session

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
if [[ "$MODE" == "full" ]]; then
  msg "Installing emulators (Flatpak)"
  declare -A EMU_FLATPAK=(
    [azahar]=org.azahar_emu.Azahar
    [rpcs3]=net.rpcs3.RPCS3
    [pcsx2]=net.pcsx2.PCSX2
    [dolphin]=org.DolphinEmu.dolphin-emu
    [melonds]=net.kuribo64.melonDS
    [gopher64]=io.github.gopher64.gopher64
    [mgba]=io.mgba.mGBA
    [ppsspp]=org.ppsspp.PPSSPP
    [cemu]=info.cemu.Cemu
    [ryujinx]=io.github.ryubing.Ryujinx
    [shadps4]=net.shadps4.shadPS4
  )
  FLATPAKS=()
  for id in azahar rpcs3 pcsx2 dolphin melonds gopher64 mgba ppsspp cemu ryujinx shadps4; do
    want_emu "$id" && FLATPAKS+=("${EMU_FLATPAK[$id]}")
  done
  # Steam moved to the apps selection but rides the same Flatpak pipeline
  # (install + ROMs/gamepad overrides below).
  want_app steam && FLATPAKS+=(com.valvesoftware.Steam)
  EMU_I=0
  for pkg in "${FLATPAKS[@]}"; do
    EMU_I=$((EMU_I + 1))
    # interpolate 25 → 50 % across the selected emulators/apps
    progress $((25 + EMU_I * 25 / ${#FLATPAKS[@]})) "Installing $pkg"
    flatpak list --app 2>/dev/null | grep -q "$pkg" \
      && info "$pkg — already installed." \
      || { flatpak install -y flathub "$pkg" && ok "$pkg installed." || warn "$pkg failed."; }
  done

  # Sandbox permissions: ROM directory + gamepad access for every emulator
  for pkg in "${FLATPAKS[@]}"; do
    flatpak override --filesystem="$GAMECORE_PATH" --device=all "$pkg" 2>/dev/null || true
  done
  ok "Flatpak overrides applied (ROMs dir + controller access)."

  # ── DuckStation AppImage ───────────────────────────────────────
  if want_emu duckstation; then
  progress 50 "DuckStation AppImage"
  msg "DuckStation AppImage"
  DUCK_BIN="$GAMECORE_PATH/bin/duckstation.AppImage"
  sudo -u "$USER_NAME" mkdir -p "$GAMECORE_PATH/bin"
  if [ -f "$DUCK_BIN" ]; then
    ok "DuckStation already present."
  else
    # `|| true`: an unreachable API leaves DUCK_URL empty (warn below) instead
    # of json.load crashing on an empty stream and killing the install (set -e).
    DUCK_URL=$(curl -sf --connect-timeout 15 --max-time 60 "https://api.github.com/repos/stenzek/duckstation/releases/latest" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((a["browser_download_url"] for a in d.get("assets",[]) if a["name"]=="DuckStation-x64.AppImage"), ""))' || true)
    if [[ -n "$DUCK_URL" ]]; then
      curl -L --connect-timeout 15 --speed-limit 1024 --speed-time 30 -o "$DUCK_BIN" "$DUCK_URL" && chmod +x "$DUCK_BIN" && ok "DuckStation installed." || warn "Download failed."
    else
      warn "Could not fetch DuckStation URL."
    fi
  fi

  fi  # duckstation

  # ── Xenia Canary (Xbox 360) — runs through Wine ────────────────
  if want_emu xenia; then
  progress 52 "Xenia Canary (Wine)"
  msg "Xenia Canary (Wine)"
  pacman -S --noconfirm --needed wine unzip p7zip && ok "wine + archive tools installed." || warn "wine install failed."
  XENIA_DIR="$GAMECORE_PATH/lib/xenia"
  if [ -f "$XENIA_DIR/xenia_canary.exe" ]; then
    ok "Xenia already present."
  else
    XENIA_URL=$(curl -sf --connect-timeout 15 --max-time 60 "https://api.github.com/repos/xenia-canary/xenia-canary-releases/releases/latest" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((a["browser_download_url"] for a in d.get("assets",[]) if "windows" in a["name"].lower()), ""))' || true)
    if [[ -n "$XENIA_URL" ]]; then
      mkdir -p "$XENIA_DIR"
      XENIA_PKG="/tmp/xenia_canary_pkg"
      curl -sfL --connect-timeout 15 --speed-limit 1024 --speed-time 30 -o "$XENIA_PKG" "$XENIA_URL" || warn "Xenia download failed."
      case "$XENIA_URL" in
        *.zip) unzip -o -q "$XENIA_PKG" -d "$XENIA_DIR" ;;
        *.7z)  7z x -y -o"$XENIA_DIR" "$XENIA_PKG" >/dev/null ;;
        *)     warn "Unknown Xenia archive format: $XENIA_URL" ;;
      esac
      rm -f "$XENIA_PKG"
      chown -R "${USER_NAME}:${USER_NAME}" "$XENIA_DIR"
      [ -f "$XENIA_DIR/xenia_canary.exe" ] \
        && ok "Xenia Canary installed → lib/xenia/ (launched via wine)." \
        || warn "xenia_canary.exe not found after extraction."
    else
      warn "Could not fetch Xenia Canary URL."
    fi
  fi

  fi  # xenia

  # ── Adapt systems.json to this machine's launchers ─────────────
  progress 55 "Adapting systems.json"
  msg "Systems → Flatpak launchers"
  bash "$GAMECORE_PATH/install/flatpakify-systems.sh" "$GAMECORE_PATH" \
    && ok "systems.json adapted." || warn "flatpakify failed — check config/systems.json."

  # ── Curated emulator configs (incl. controller bindings) ───────
  progress 56 "Emulator configs"
  msg "Emulator configs"
  if [ -d "$GAMECORE_PATH/emu-configs" ]; then
    sudo -u "$USER_NAME" bash "$GAMECORE_PATH/install/install-emu-configs.sh" \
      && ok "Curated configs deployed." || warn "Config deployment failed."
  else
    warn "emu-configs/ not found — skipping."
  fi

  # ── Living-room companions: EmberTV, gamepad bridge, kiosk apps ─
  # Each app (twitch / youtube / stremio — steam is handled with the Flatpaks
  # above) only installs when selected in APPS; unchecked means nothing is
  # cloned, built or enabled for it.
  progress 58 "Living-room applications"
  msg "Living-room companions"
  UNIT_DIR="$USER_HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR/default.target.wants"
  # user services to (re)start once the user bus is up, filled per app below
  RESTART_UNITS=()

  if want_app twitch || want_app youtube; then
    pacman -S --noconfirm --needed firefox nss && ok "firefox + nss (certutil) installed." || warn "firefox install failed."
  fi

  if want_app twitch; then
  progress 60 "Twitch (EmberTV)"
  # EmberTV — Twitch for the big screen (GameCore's Twitch tile opens it)
  if [ ! -d /opt/Twitch-TV ]; then
    git_clone https://github.com/p4v1c/Twitch-TV.git /opt/Twitch-TV \
      && ok "EmberTV cloned → /opt/Twitch-TV" || warn "EmberTV clone failed."
  else
    ok "EmberTV already present."
  fi
  if [ -d /opt/Twitch-TV ]; then
    if [[ -n "$TWITCH_CLIENT_ID" && -n "$TWITCH_CLIENT_SECRET" ]]; then
      cat > /opt/Twitch-TV/config.json <<TWCFG
{
  "clientId": "$TWITCH_CLIENT_ID",
  "clientSecret": "$TWITCH_CLIENT_SECRET",
  "port": 8097,
  "host": "0.0.0.0",
  "httpsKey": "",
  "httpsCert": ""
}
TWCFG
      chmod 600 /opt/Twitch-TV/config.json
      ok "Twitch credentials written (config.json, kept out of git)."
    elif [ ! -f /opt/Twitch-TV/config.json ]; then
      cp /opt/Twitch-TV/config.example.json /opt/Twitch-TV/config.json
      warn "No Twitch credentials — EmberTV starts in demo mode (edit /opt/Twitch-TV/config.json later)."
    fi
    chown -R "${USER_NAME}:${USER_NAME}" /opt/Twitch-TV
    # Generate the TLS cert now (instead of first service start) so it can be
    # trusted in the Firefox profile below — zero interaction at first launch.
    if [ ! -f /opt/Twitch-TV/cert/cert.pem ]; then
      sudo -u "$USER_NAME" bash /opt/Twitch-TV/make-cert.sh >/dev/null 2>&1 \
        && ok "EmberTV TLS certificate generated." \
        || warn "make-cert failed — it will be generated at first start instead."
    fi
    cat > "$UNIT_DIR/embertv.service" <<'EOF'
[Unit]
Description=EmberTV — Twitch for the big screen
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/Twitch-TV
Environment=PATH=/usr/bin:/usr/local/bin:/bin
ExecStart=/usr/bin/env bash /opt/Twitch-TV/start-tv.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
    ln -sf ../embertv.service "$UNIT_DIR/default.target.wants/embertv.service"
    RESTART_UNITS+=(embertv.service)
    ok "embertv.service installed (user unit, starts at login)."
  fi
  fi  # twitch

  if want_app twitch || want_app youtube || want_app stremio; then
  progress 64 "Gamepad TV bridge"
  # gamepad-tv-bridge — gamepad → keyboard for kiosk web apps
  if [ ! -d /opt/gamepad-tv-bridge ]; then
    git_clone https://github.com/p4v1c/gamepad-tv-bridge.git /opt/gamepad-tv-bridge \
      && ok "gamepad-tv-bridge cloned → /opt/gamepad-tv-bridge" || warn "gamepad-tv-bridge clone failed."
  else
    ok "gamepad-tv-bridge already present."
  fi
  if [ -d /opt/gamepad-tv-bridge ]; then
    chown -R "${USER_NAME}:${USER_NAME}" /opt/gamepad-tv-bridge
    sudo -u "$USER_NAME" python3 -m venv "$USER_HOME/.venv" 2>/dev/null || true
    sudo -u "$USER_NAME" "$USER_HOME/.venv/bin/pip" install -q -e /opt/gamepad-tv-bridge \
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

  chown -R "${USER_NAME}:${USER_NAME}" "$USER_HOME/.config"
  loginctl enable-linger "$USER_NAME" 2>/dev/null && ok "user services will start at boot (linger)." || true

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

  # Firefox kiosk profiles used by the YouTube/Twitch tiles in apps.json.
  # The user.js is the important part: it carries the Smart-TV user agent
  # (youtube.com/tv rejects desktop browsers) and the kiosk prefs.
  # Plain directories launched with `firefox --profile <dir>` — no
  # profiles.ini registration needed, so no flaky `-CreateProfile` run.
  # Everything is created AS THE USER: a root-owned profile dir breaks
  # certutil below (SEC_ERROR_BAD_DATABASE) and firefox's own caches.
  FIREFOX_PROFILES=()
  want_app youtube && FIREFOX_PROFILES+=(youtube-tv)
  want_app twitch  && FIREFOX_PROFILES+=(twitch-tv)
  for prof in ${FIREFOX_PROFILES[@]+"${FIREFOX_PROFILES[@]}"}; do
    PROF_DIR="$USER_HOME/.mozilla/firefox/$prof"
    sudo -u "$USER_NAME" mkdir -p "$PROF_DIR"
    install -o "$USER_NAME" -g "$USER_NAME" -m 644 \
      "$GAMECORE_PATH/install/firefox-profiles/$prof.user.js" "$PROF_DIR/user.js"
  done
  if want_app twitch; then
  # Trust EmberTV's self-signed cert inside the twitch-tv profile (NSS db):
  # no certificate warning at first launch — required for the unattended/ISO path.
  # Every certutil step is guarded: a cert hiccup must never abort the install.
  TW_PROF="$USER_HOME/.mozilla/firefox/twitch-tv"
  if [ -f /opt/Twitch-TV/cert/cert.pem ] && command -v certutil >/dev/null; then
    if [ -f "$TW_PROF/cert9.db" ] || sudo -u "$USER_NAME" certutil -N --empty-password -d sql:"$TW_PROF"; then
      sudo -u "$USER_NAME" certutil -D -n "EmberTV localhost" -d sql:"$TW_PROF" 2>/dev/null || true
      sudo -u "$USER_NAME" certutil -A -n "EmberTV localhost" -t "P,," \
          -i /opt/Twitch-TV/cert/cert.pem -d sql:"$TW_PROF" \
        && ok "EmberTV certificate trusted in the twitch-tv profile." \
        || warn "certutil import failed — accept the cert warning once at first launch."
    else
      warn "NSS db init failed — accept the cert warning once at first launch."
    fi
  fi
  fi  # twitch certutil
  if [ ${#FIREFOX_PROFILES[@]} -gt 0 ]; then
    chown -R "${USER_NAME}:${USER_NAME}" "$USER_HOME/.mozilla"
    ok "Firefox kiosk profiles ready (${FIREFOX_PROFILES[*]} — Smart-TV user agent)."
  fi

  if want_app stremio; then
  progress 68 "Stremio"
  # Stremio (media tile) — needs gamepad + media access inside the sandbox
  flatpak list --app 2>/dev/null | grep -q com.stremio.Stremio \
    || { flatpak install -y flathub com.stremio.Stremio && ok "Stremio installed." || warn "Stremio failed."; }
  flatpak override --device=all --filesystem=host com.stremio.Stremio 2>/dev/null || true

  # Stremio media center over the gamepad: a fork of stremio-web with a TV
  # on-screen keyboard, served in a Firefox kiosk and driven by
  # gamepad-tv-bridge (stremio profile). The Flatpak above stays installed —
  # its bundled node/server.js is the streaming server (stremio-server.service).
  STREMIO_WEB_DIR="$USER_HOME/stremio-web"
  if [ ! -d "$STREMIO_WEB_DIR" ]; then
    git_clone https://github.com/p4v1c/stremio-web.git "$STREMIO_WEB_DIR" \
      && sudo -u "$USER_NAME" git -C "$STREMIO_WEB_DIR" checkout feature/tv-virtual-keyboard \
      && ok "stremio-web fork cloned → $STREMIO_WEB_DIR" || warn "stremio-web clone failed."
  fi
  if [ -d "$STREMIO_WEB_DIR" ] && [ -x /opt/gamepad-tv-bridge/install/setup-stremio.sh ]; then
    chown -R "${USER_NAME}:${USER_NAME}" "$STREMIO_WEB_DIR"
    # pnpm (>= 11): reuse an existing one, else install into ~/.local.
    PNPM_BIN="$USER_HOME/.local/bin/pnpm"
    sudo -u "$USER_NAME" bash -lc 'command -v pnpm >/dev/null 2>&1' && PNPM_BIN="$(sudo -u "$USER_NAME" bash -lc 'command -v pnpm')"
    if ! sudo -u "$USER_NAME" test -x "$PNPM_BIN"; then
      sudo -u "$USER_NAME" npm install -g pnpm@latest --prefix "$USER_HOME/.local" >/dev/null 2>&1 \
        && ok "pnpm installed for $USER_NAME." || warn "pnpm install failed — build the fork manually."
      PNPM_BIN="$USER_HOME/.local/bin/pnpm"
    fi
    if sudo -u "$USER_NAME" test -x "$PNPM_BIN"; then
      progress 70 "Building stremio-web (a few minutes)"
      msg "Building stremio-web fork (can take a few minutes)…"
      sudo -u "$USER_NAME" bash -lc "cd '$STREMIO_WEB_DIR' && '$PNPM_BIN' install && SERVICE_WORKER_DISABLED=true '$PNPM_BIN' build" \
        && ok "stremio-web built." || warn "stremio-web build failed — run 'pnpm install && pnpm build' later."
    fi
    # Install + enable the user services (streaming server / static UI / kiosk).
    sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_UID" \
      bash /opt/gamepad-tv-bridge/install/setup-stremio.sh \
      && ok "Stremio TV kiosk services installed." || warn "Stremio TV setup deferred to next login."
  fi
  fi  # stremio
else
  msg "Minimal mode — skipping emulators, applications and configs."
fi

# ── App tiles (config/apps.json) ─────────────────────────────────
# Keep only the tiles of the apps actually installed — an unchecked app must
# not leave a dead tile in the UI (minimal mode keeps none). Same spirit as
# flatpakify-systems.sh for the emulators.
progress 78 "App tiles"
msg "App tiles"
# apps.json was harvested on a box where HOME was /home/pavic — adapt it
sed -i "s|/home/pavic|$USER_HOME|g" "$GAMECORE_PATH/config/apps.json"
KEEP_APPS=""
for app in twitch stremio steam youtube; do
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

# ── ROM directories ──────────────────────────────────────────────
progress 80 "ROM directories"
msg "ROM directories"
for d in azahar cemu ryujinx dolphin duckstation gopher64 melonds mgba pcsx2 ppsspp rpcs3 xenia shadps4 covers; do
  sudo -u "$USER_NAME" mkdir -p "$GAMECORE_PATH/emu/$d"
done
ok "ROM directories ready."

# ── Input group + udev rule (needed for evdev PS-button detection) ──
progress 82 "Gamepad input access"
msg "Gamepad input access"
usermod -aG input "$USER_NAME" && ok "$USER_NAME added to 'input' group." || warn "Could not add to input group."

# udev rule: make all gamepad/joystick event nodes group=input + world-readable
# This means the backend process can open them even before a re-login
cat > /etc/udev/rules.d/99-gamecore-input.rules <<'UDEV'
# GameCore — allow reading gamepad events for PS/guide button detection
KERNEL=="event*", SUBSYSTEM=="input", TAG=="seat", MODE="0664", GROUP="input"
KERNEL=="event*", SUBSYSTEM=="input", ATTRS{bInterfaceClass}=="03", MODE="0664", GROUP="input"
# Sony DualShock / DualSense (vendor 054c)
SUBSYSTEM=="input", ATTRS{idVendor}=="054c", MODE="0664", GROUP="input"
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

# ── Node / frontend ──────────────────────────────────────────────
progress 89 "Building the frontend"
msg "Node frontend build"
cd "$GAMECORE_PATH/frontend"
sudo -u "$USER_NAME" -H npm install
sudo -u "$USER_NAME" -H npm run build
cd "$SCRIPT_DIR"
ok "Frontend built → frontend/dist/"

# ── Electron ─────────────────────────────────────────────────────
progress 93 "Electron shell"
msg "Electron shell"
cd "$GAMECORE_PATH/electron"
sudo -u "$USER_NAME" -H npm install

# The electron npm package downloads its actual binary from a postinstall
# script (node install.js). On machines with hardened npm (ignore-scripts,
# @lavamoat/allow-scripts, …) that step is silently skipped, leaving
# node_modules/electron with no binary → "Electron failed to install
# correctly" at runtime. Provision the binary explicitly so the install never
# depends on the postinstall running.
ELECTRON_DIR="$GAMECORE_PATH/electron/node_modules/electron"
if [[ ! -x "$ELECTRON_DIR/dist/electron" ]]; then
  warn "Electron binary missing (npm postinstall was skipped) — downloading it directly."
  EV="$(sudo -u "$USER_NAME" node -p "require('$ELECTRON_DIR/package.json').version" 2>/dev/null)"
  [[ -n "$EV" ]] || die "Could not determine the Electron version."
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

# chrome-sandbox must be a root-owned SUID binary, otherwise Electron refuses
# to start under an unprivileged user on some setups.
if [[ -f "$ELECTRON_DIR/dist/chrome-sandbox" ]]; then
  chown root:root "$ELECTRON_DIR/dist/chrome-sandbox"
  chmod 4755 "$ELECTRON_DIR/dist/chrome-sandbox"
fi
cd "$SCRIPT_DIR"
ok "Electron dependencies installed."

# ── systemd service ──────────────────────────────────────────────
progress 95 "systemd services"
msg "systemd service"

cat > /etc/systemd/system/gamecore-backend.service <<EOF
[Unit]
Description=GameCore — FastAPI Backend
After=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
SupplementaryGroups=input
Environment=GAMECORE_PATH=$GAMECORE_PATH
Environment=GAMECORE_BACKEND_PORT=$WEB_PORT
WorkingDirectory=$GAMECORE_PATH
ExecStart=$GAMECORE_PATH/.venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port $WEB_PORT --log-level debug
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

if [[ -n "$TGDB_API_KEY" ]]; then
  mkdir -p /etc/systemd/system/gamecore-backend.service.d
  cat > /etc/systemd/system/gamecore-backend.service.d/override.conf <<EOF
[Service]
Environment=THEGAMESDB_API_KEY=$TGDB_API_KEY
EOF
  chmod 600 /etc/systemd/system/gamecore-backend.service.d/override.conf
  ok "TheGamesDB API key configured (local drop-in, never in git)."
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
WorkingDirectory=$GAMECORE_PATH
# Wait for any X display (SDDM may use :0 or :1) — start-ui.sh then detects
# the display and xauth cookie itself.
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 60); do XAUTH=\$(find /run/user/\$(id -u) -name "xauth_*" 2>/dev/null | head -1); if [ -n "\$XAUTH" ]; then for D in :1 :0 :2; do XAUTHORITY=\$XAUTH xdpyinfo -display \$D >/dev/null 2>&1 && exit 0; done; fi; sleep 1; done; exit 0'
ExecStart=$GAMECORE_PATH/electron/start-ui.sh
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOF

# ── SDDM auto-login ──────────────────────────────────────────────
progress 96 "SDDM auto-login (KDE Plasma)"
msg "SDDM auto-login"
# KDE Plasma on X11 — the whole stack (overlays, fullscreen enforcer,
# gamepad-tv-bridge key injection, gamecore-xsetup) is X11-only, so never
# pick the Wayland session. Plasma 6 names its X11 session "plasmax11"
# (plasma-x11-session package); older Plasma ships it as "plasma".
if [ -f /usr/share/xsessions/plasmax11.desktop ]; then
  KDE_SESSION="plasmax11"
elif [ -f /usr/share/xsessions/plasma.desktop ]; then
  KDE_SESSION="plasma"
else
  warn "No Plasma X11 session found in /usr/share/xsessions — defaulting to 'plasmax11'."
  KDE_SESSION="plasmax11"
fi
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/autologin.conf <<EOF
[Autologin]
User=$USER_NAME
Session=$KDE_SESSION
Relogin=true
EOF
ok "SDDM configured for auto-login as $USER_NAME (KDE Plasma X11 session: $KDE_SESSION)."

# Force 1920x1080 at the display-server level (never 4K). SDDM runs this as
# root at X startup, before any session, so the whole X server — kiosk, games
# and overlays — is pinned to 1080p. See install/gamecore-xsetup.sh.
install -m755 "$GAMECORE_PATH/install/gamecore-xsetup.sh" /usr/local/bin/gamecore-xsetup
cat > /etc/sddm.conf.d/gamecore-display.conf <<EOF
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
# Every name the box answers to needs its own internal certificate —
# a client hitting an unlisted address gets a TLS handshake error.
CADDY_ADDRS="https://${LOCAL_IP}:8443"
if command -v tailscale >/dev/null 2>&1; then
  TS_IP=$(tailscale ip -4 2>/dev/null | head -1) || true
  [[ -n "${TS_IP:-}" ]] && CADDY_ADDRS="${CADDY_ADDRS}, https://${TS_IP}:8443"
  TS_NAME=$(tailscale status --json 2>/dev/null | python3 -c \
    'import json,sys; print(json.load(sys.stdin).get("Self",{}).get("DNSName","").rstrip("."))' 2>/dev/null) || true
  [[ -n "${TS_NAME:-}" ]] && CADDY_ADDRS="${CADDY_ADDRS}, https://${TS_NAME}:8443"
fi
sed "s|__GAMECORE_SITE_ADDRESSES__|${CADDY_ADDRS}|" "$GAMECORE_PATH/install/Caddyfile" > /etc/caddy/Caddyfile
systemctl enable --now caddy.service
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
progress 97 "Bluetooth, power & desktop launcher"
msg "Bluetooth"
systemctl enable --now bluetooth.service
ok "Bluetooth service enabled."

# ── Power management (reboot/shutdown from UI) ───────────────────
msg "Sudoers — power management"
cat > /etc/sudoers.d/gamecore-power <<EOF
$USER_NAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/udevadm
# Desktop launcher (gamecore-launcher.sh) — start GameCore from the desktop
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl start gamecore-backend.service, /usr/bin/systemctl start gamecore-ui.service
EOF
chmod 440 /etc/sudoers.d/gamecore-power
visudo -cf /etc/sudoers.d/gamecore-power >/dev/null || { rm -f /etc/sudoers.d/gamecore-power; warn "sudoers validation failed."; }
ok "Sudoers rules created (power + udevadm + GameCore start for $USER_NAME)."

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

# ── Addons ───────────────────────────────────────────────────────
# Selected gamecore-addons modules (rom-manager by default — everyone
# wants the browser ROM upload). Each runs as a user-level service.
if [[ -n "$ADDONS" ]]; then
  progress 98 "Addons ($ADDONS)"
  msg "Addons ($ADDONS)"
  USER_UID=$(id -u "$USER_NAME")
  loginctl enable-linger "$USER_NAME" 2>/dev/null || true
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
