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
#   shadps4 steam duckstation xenia
# ADDONS: space-separated gamecore-addons names installed at the end.
EMULATORS="all"
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
else
  read -rp "  System username (e.g. pavic)         : " USER_NAME
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

echo
msg "Summary"
info "User         : $USER_NAME"
info "Install path : $GAMECORE_PATH"
info "API port     : $WEB_PORT"
info "Detected IP  : $LOCAL_IP"
info "Mode         : $MODE $([ "$MODE" = minimal ] && echo '(no emulators, no apps)' || echo '(emulators + apps + configs)')"
[[ "$MODE" == "full" ]] && info "Emulators    : $EMULATORS"
info "Addons       : ${ADDONS:-none}"
[[ "$MODE" == "full" ]] && info "EmberTV      : $([ -n "$TWITCH_CLIENT_ID" ] && echo 'live Twitch (credentials set)' || echo 'demo mode (no credentials)')"
echo
if ! $UNATTENDED; then
  read -rp "  Continue? (y/N) " CONFIRM
  [[ "$CONFIRM" =~ ^[yY]$ ]] || die "Aborted."
fi

# ── User check ───────────────────────────────────────────────────
msg "Checking user"
id "$USER_NAME" >/dev/null 2>&1 || { useradd -m -s /bin/bash "$USER_NAME"; ok "User $USER_NAME created."; }
ok "User $USER_NAME OK"

# ── Copy files ───────────────────────────────────────────────────
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
msg "System packages"
pacman -Syu --noconfirm

PKGS=(
  mesa
  base-devel git flatpak openssh
  python python-pip
  nodejs npm
  openbox xorg-xdpyinfo xorg-xrandr
  bluez bluez-utils
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

# ── CPU governor ─────────────────────────────────────────────────
msg "CPU governor"
systemctl enable --now cpupower.service 2>/dev/null \
  && cpupower frequency-set -g performance 2>/dev/null \
  && ok "Performance mode set." \
  || warn "cpupower not available."

# ── Flatpak ──────────────────────────────────────────────────────
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
    [steam]=com.valvesoftware.Steam
  )
  FLATPAKS=()
  for id in azahar rpcs3 pcsx2 dolphin melonds gopher64 mgba ppsspp cemu ryujinx shadps4 steam; do
    want_emu "$id" && FLATPAKS+=("${EMU_FLATPAK[$id]}")
  done
  for pkg in "${FLATPAKS[@]}"; do
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
  msg "DuckStation AppImage"
  DUCK_BIN="$GAMECORE_PATH/bin/duckstation.AppImage"
  sudo -u "$USER_NAME" mkdir -p "$GAMECORE_PATH/bin"
  if [ -f "$DUCK_BIN" ]; then
    ok "DuckStation already present."
  else
    DUCK_URL=$(curl -sf "https://api.github.com/repos/stenzek/duckstation/releases/latest" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((a["browser_download_url"] for a in d.get("assets",[]) if a["name"]=="DuckStation-x64.AppImage"), ""))')
    if [[ -n "$DUCK_URL" ]]; then
      curl -L -o "$DUCK_BIN" "$DUCK_URL" && chmod +x "$DUCK_BIN" && ok "DuckStation installed." || warn "Download failed."
    else
      warn "Could not fetch DuckStation URL."
    fi
  fi

  fi  # duckstation

  # ── Xenia Canary (Xbox 360) — runs through Wine ────────────────
  if want_emu xenia; then
  msg "Xenia Canary (Wine)"
  pacman -S --noconfirm --needed wine unzip p7zip && ok "wine + archive tools installed." || warn "wine install failed."
  XENIA_DIR="$GAMECORE_PATH/lib/xenia"
  if [ -f "$XENIA_DIR/xenia_canary.exe" ]; then
    ok "Xenia already present."
  else
    XENIA_URL=$(curl -sf "https://api.github.com/repos/xenia-canary/xenia-canary-releases/releases/latest" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((a["browser_download_url"] for a in d.get("assets",[]) if "windows" in a["name"].lower()), ""))')
    if [[ -n "$XENIA_URL" ]]; then
      mkdir -p "$XENIA_DIR"
      XENIA_PKG="/tmp/xenia_canary_pkg"
      curl -sfL -o "$XENIA_PKG" "$XENIA_URL" || warn "Xenia download failed."
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
  msg "Systems → Flatpak launchers"
  bash "$GAMECORE_PATH/install/flatpakify-systems.sh" "$GAMECORE_PATH" \
    && ok "systems.json adapted." || warn "flatpakify failed — check config/systems.json."

  # ── Curated emulator configs (incl. controller bindings) ───────
  msg "Emulator configs"
  if [ -d "$GAMECORE_PATH/emu-configs" ]; then
    sudo -u "$USER_NAME" bash "$GAMECORE_PATH/install/install-emu-configs.sh" \
      && ok "Curated configs deployed." || warn "Config deployment failed."
  else
    warn "emu-configs/ not found — skipping."
  fi

  # ── Living-room companions: EmberTV, gamepad bridge, kiosk apps ─
  msg "Living-room companions"
  USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)
  UNIT_DIR="$USER_HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR/default.target.wants" "$UNIT_DIR/graphical-session.target.wants"

  pacman -S --noconfirm --needed firefox nss && ok "firefox + nss (certutil) installed." || warn "firefox install failed."

  # EmberTV — Twitch for the big screen (GameCore's Twitch tile opens it)
  if [ ! -d /opt/Twitch-TV ]; then
    git clone -q https://github.com/p4v1c/Twitch-TV.git /opt/Twitch-TV \
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
    ok "embertv.service installed (user unit, starts at login)."
  fi

  # gamepad-tv-bridge — gamepad → keyboard for kiosk web apps
  if [ ! -d /opt/gamepad-tv-bridge ]; then
    git clone -q https://github.com/p4v1c/gamepad-tv-bridge.git /opt/gamepad-tv-bridge \
      && ok "gamepad-tv-bridge cloned → /opt/gamepad-tv-bridge" || warn "gamepad-tv-bridge clone failed."
  else
    ok "gamepad-tv-bridge already present."
  fi
  if [ -d /opt/gamepad-tv-bridge ]; then
    chown -R "${USER_NAME}:${USER_NAME}" /opt/gamepad-tv-bridge
    sudo -u "$USER_NAME" python3 -m venv "$USER_HOME/.venv" 2>/dev/null || true
    sudo -u "$USER_NAME" "$USER_HOME/.venv/bin/pip" install -q -e /opt/gamepad-tv-bridge \
      && ok "bridge installed in $USER_HOME/.venv (editable)." || warn "bridge pip install failed."
    cat > "$UNIT_DIR/gamepad-tv-bridge.service" <<'EOF'
[Unit]
Description=Gamepad TV Bridge — gamepad to keyboard daemon
After=graphical-session.target

[Service]
Type=simple
Environment=DISPLAY=:0
ExecStart=%h/.venv/bin/python -m gamepad_bridge start
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
    ln -sf ../gamepad-tv-bridge.service "$UNIT_DIR/graphical-session.target.wants/gamepad-tv-bridge.service"
    ok "gamepad-tv-bridge.service installed (user unit)."
    # /dev/uinput access for key injection
    modprobe uinput 2>/dev/null || true
    echo "uinput" > /etc/modules-load.d/uinput.conf
    cat > /etc/udev/rules.d/99-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
    ok "uinput module + udev rule configured."
  fi

  chown -R "${USER_NAME}:${USER_NAME}" "$USER_HOME/.config"
  loginctl enable-linger "$USER_NAME" 2>/dev/null && ok "user services will start at boot (linger)." || true

  # Firefox kiosk profiles used by the YouTube/Twitch tiles in apps.json.
  # The user.js is the important part: it carries the Smart-TV user agent
  # (youtube.com/tv rejects desktop browsers) and the kiosk prefs.
  for prof in youtube-tv twitch-tv; do
    PROF_DIR="$USER_HOME/.mozilla/firefox/$prof"
    sudo -u "$USER_NAME" HOME="$USER_HOME" firefox --headless -CreateProfile "$prof $PROF_DIR" >/dev/null 2>&1 || true
    mkdir -p "$PROF_DIR"
    cp "$GAMECORE_PATH/install/firefox-profiles/$prof.user.js" "$PROF_DIR/user.js"
  done
  # Trust EmberTV's self-signed cert inside the twitch-tv profile (NSS db):
  # no certificate warning at first launch — required for the unattended/ISO path.
  TW_PROF="$USER_HOME/.mozilla/firefox/twitch-tv"
  if [ -f /opt/Twitch-TV/cert/cert.pem ] && command -v certutil >/dev/null; then
    [ -f "$TW_PROF/cert9.db" ] || sudo -u "$USER_NAME" certutil -N --empty-password -d sql:"$TW_PROF"
    sudo -u "$USER_NAME" certutil -D -n "EmberTV localhost" -d sql:"$TW_PROF" 2>/dev/null || true
    sudo -u "$USER_NAME" certutil -A -n "EmberTV localhost" -t "P,," \
        -i /opt/Twitch-TV/cert/cert.pem -d sql:"$TW_PROF" \
      && ok "EmberTV certificate trusted in the twitch-tv profile." \
      || warn "certutil import failed — accept the cert warning once at first launch."
  fi
  chown -R "${USER_NAME}:${USER_NAME}" "$USER_HOME/.mozilla"
  ok "Firefox kiosk profiles ready (youtube-tv, twitch-tv — Smart-TV user agent)."
  # apps.json was harvested on a box where HOME was /home/pavic — adapt it
  sed -i "s|/home/pavic|$USER_HOME|g" "$GAMECORE_PATH/config/apps.json"
  ok "apps.json paths adapted to $USER_HOME."

  # Stremio (media tile) — needs gamepad + media access inside the sandbox
  flatpak list --app 2>/dev/null | grep -q com.stremio.Stremio \
    || { flatpak install -y flathub com.stremio.Stremio && ok "Stremio installed." || warn "Stremio failed."; }
  flatpak override --device=all --filesystem=host com.stremio.Stremio 2>/dev/null || true
else
  msg "Minimal mode — skipping emulators, applications and configs."
fi

# ── ROM directories ──────────────────────────────────────────────
msg "ROM directories"
for d in azahar cemu ryujinx dolphin duckstation gopher64 melonds mgba pcsx2 ppsspp rpcs3 xenia shadps4 covers; do
  sudo -u "$USER_NAME" mkdir -p "$GAMECORE_PATH/emu/$d"
done
ok "ROM directories ready."

# ── Input group + udev rule (needed for evdev PS-button detection) ──
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
msg "Addon manager (gamecore-addon)"
install -m 755 "$GAMECORE_PATH/install/gamecore-addon" /usr/local/bin/gamecore-addon
# Pre-create the addons checkout dir owned by the user so `gamecore-addon
# install` never needs root for user-level addons.
install -d -o "$USER_NAME" -g "$USER_NAME" /opt/gamecore-addons
ok "gamecore-addon CLI installed (addons live in /opt/gamecore-addons)."

# ── Python backend ───────────────────────────────────────────────
msg "Python backend (venv)"
sudo -u "$USER_NAME" -H python3 -m venv "$GAMECORE_PATH/.venv"
sudo -u "$USER_NAME" -H "$GAMECORE_PATH/.venv/bin/pip" install -q -r "$GAMECORE_PATH/backend/requirements.txt"
ok "Python dependencies installed."

# ── Node / frontend ──────────────────────────────────────────────
msg "Node frontend build"
cd "$GAMECORE_PATH/frontend"
sudo -u "$USER_NAME" -H npm install
sudo -u "$USER_NAME" -H npm run build
cd "$SCRIPT_DIR"
ok "Frontend built → frontend/dist/"

# ── Electron ─────────────────────────────────────────────────────
msg "Electron shell"
cd "$GAMECORE_PATH/electron"
sudo -u "$USER_NAME" -H npm install
cd "$SCRIPT_DIR"
ok "Electron dependencies installed."

# ── systemd service ──────────────────────────────────────────────
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
msg "SDDM auto-login"
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/autologin.conf <<EOF
[Autologin]
User=$USER_NAME
Session=openbox
Relogin=true
EOF
ok "SDDM configured for auto-login as $USER_NAME (openbox session)."

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

# ── Bluetooth ────────────────────────────────────────────────────
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
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)
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
echo
echo -e "${BLU}╔══════════════════════════════════════╗${RST}"
echo -e "${BLU}║     Installation complete!           ║${RST}"
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"
echo
ok "Backend API   → http://${LOCAL_IP}:${WEB_PORT}"
ok "ROM Manager   → http://${LOCAL_IP}:8770  (addon)"
ok "SSH           → ssh ${USER_NAME}@${LOCAL_IP}"
echo
echo -e "${YLW}  Next steps:${RST}"
echo "  1. Reboot — GameCore launches automatically."
echo "  2. Upload ROMs at http://${LOCAL_IP}:8770  (drag & drop)"
echo "  3. Only manual step left: copy BIOS/firmwares (PS1/PS2/PS3, DS/3DS, Switch keys)."
echo
