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

[[ $EUID -eq 0 ]] || die "Run with sudo: sudo bash install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Detect distro ────────────────────────────────────────────────
IS_MANJARO=false
grep -qi "manjaro" /etc/os-release 2>/dev/null && IS_MANJARO=true

# ── Banner ───────────────────────────────────────────────────────
echo -e "\n${BLU}╔══════════════════════════════════════╗${RST}"
echo -e "${BLU}║     GameCore — Installer          ║${RST}"
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"

# ── Prompts ──────────────────────────────────────────────────────
read -rp "  System username (e.g. pavic)         : " USER_NAME
read -rp "  Install path [default: /opt/GameCore] : " GAMECORE_PATH
GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
read -rp "  Web ROM port [default: 8765]          : " WEB_PORT
WEB_PORT="${WEB_PORT:-8765}"

LOCAL_IP=$(hostname -I | awk '{print $1}')

echo
msg "Summary"
info "User         : $USER_NAME"
info "Install path : $GAMECORE_PATH"
info "API port     : $WEB_PORT"
info "Detected IP  : $LOCAL_IP"
echo
read -rp "  Continue? (y/N) " CONFIRM
[[ "$CONFIRM" =~ ^[yY]$ ]] || die "Aborted."

# ── User check ───────────────────────────────────────────────────
msg "Checking user"
id "$USER_NAME" >/dev/null 2>&1 || { useradd -m -s /bin/bash "$USER_NAME"; ok "User $USER_NAME created."; }
ok "User $USER_NAME OK"

# ── Copy files ───────────────────────────────────────────────────
msg "Setting up $GAMECORE_PATH"
mkdir -p "$(dirname "$GAMECORE_PATH")"
if [ "$SCRIPT_DIR" != "$GAMECORE_PATH" ]; then
  cp -r "$SCRIPT_DIR/." "$GAMECORE_PATH"
  ok "Copied $SCRIPT_DIR → $GAMECORE_PATH"
else
  ok "Already in place."
fi
chown -R "${USER_NAME}:${USER_NAME}" "$GAMECORE_PATH"

# ── System packages ──────────────────────────────────────────────
msg "System packages"
pacman -Syu --noconfirm

PKGS=(
  mesa xf86-video-amdgpu vulkan-radeon lib32-vulkan-radeon
  base-devel git flatpak openssh
  python python-pip
  nodejs npm
  openbox xorg-xdpyinfo
)

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

# ── Emulators ────────────────────────────────────────────────────
msg "Installing emulators (Flatpak)"
FLATPAKS=(
  org.azahar_emu.Azahar
  net.rpcs3.RPCS3
  net.pcsx2.PCSX2
  org.DolphinEmu.dolphin-emu
  net.kuribo64.melonDS
  io.github.gopher64.gopher64
  io.mgba.mGBA
  org.ppsspp.PPSSPP
  info.cemu.Cemu
  io.github.ryubing.Ryujinx
  com.valvesoftware.Steam
)
for pkg in "${FLATPAKS[@]}"; do
  flatpak list --app 2>/dev/null | grep -q "$pkg" \
    && info "$pkg — already installed." \
    || { flatpak install -y flathub "$pkg" && ok "$pkg installed." || warn "$pkg failed."; }
done

# ── DuckStation AppImage ─────────────────────────────────────────
msg "DuckStation AppImage"
DUCK_BIN="$GAMECORE_PATH/bin/duckstation.AppImage"
sudo -u "$USER_NAME" mkdir -p "$GAMECORE_PATH/bin"
if [ -f "$DUCK_BIN" ]; then
  ok "DuckStation already present."
else
  DUCK_URL=$(curl -sf "https://api.github.com/repos/stenzek/duckstation/releases/latest" \
    | grep -o '"browser_download_url":"[^"]*x64\.AppImage"' | grep -o 'https://[^"]*' | head -1)
  if [[ -n "$DUCK_URL" ]]; then
    curl -L -o "$DUCK_BIN" "$DUCK_URL" && chmod +x "$DUCK_BIN" && ok "DuckStation installed." || warn "Download failed."
  else
    warn "Could not fetch DuckStation URL."
  fi
fi

# ── ROM directories ──────────────────────────────────────────────
msg "ROM directories"
for d in azahar cemu ryujinx dolphin duckstation gopher64 melonds mgba pcsx2 ppsspp rpcs3 covers; do
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
udevadm control --reload-rules 2>/dev/null && udevadm trigger 2>/dev/null && ok "udev rules reloaded." || warn "udev reload failed — reconnect controller."

# ── Python backend ───────────────────────────────────────────────
msg "Python backend (venv)"
sudo -u "$USER_NAME" python3 -m venv "$GAMECORE_PATH/.venv"
sudo -u "$USER_NAME" "$GAMECORE_PATH/.venv/bin/pip" install -q -r "$GAMECORE_PATH/backend/requirements.txt"
ok "Python dependencies installed."

# ── Node / frontend ──────────────────────────────────────────────
msg "Node frontend build"
cd "$GAMECORE_PATH/frontend"
sudo -u "$USER_NAME" npm install --silent
sudo -u "$USER_NAME" npm run build
cd "$SCRIPT_DIR"
ok "Frontend built → frontend/dist/"

# ── Electron ─────────────────────────────────────────────────────
msg "Electron shell"
cd "$GAMECORE_PATH/electron"
sudo -u "$USER_NAME" npm install --silent
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
ExecStart=$GAMECORE_PATH/.venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port $WEB_PORT --log-level warning
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

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
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$USER_NAME/.Xauthority
WorkingDirectory=$GAMECORE_PATH
# Attend que le serveur X soit prêt (max 30s)
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 30); do xdpyinfo -display :0 >/dev/null 2>&1 && break || sleep 1; done'
ExecStart=$GAMECORE_PATH/electron/node_modules/.bin/electron $GAMECORE_PATH/electron/main.js
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

systemctl daemon-reload
systemctl enable sddm.service
systemctl enable gamecore-backend.service
systemctl enable gamecore-ui.service
ok "Services enabled."

# ── SSH ──────────────────────────────────────────────────────────
msg "SSH"
systemctl enable --now sshd
ok "SSH active."

# ── Final summary ────────────────────────────────────────────────
echo
echo -e "${BLU}╔══════════════════════════════════════╗${RST}"
echo -e "${BLU}║     Installation complete!           ║${RST}"
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"
echo
ok "Backend API   → http://${LOCAL_IP}:${WEB_PORT}"
ok "ROM Manager   → http://${LOCAL_IP}:${WEB_PORT}/roms"
ok "SSH           → ssh ${USER_NAME}@${LOCAL_IP}"
echo
echo -e "${YLW}  Next steps:${RST}"
echo "  1. Reboot — GameCore launches automatically."
echo "  2. Upload ROMs at http://${LOCAL_IP}:${WEB_PORT}/roms  (drag & drop)"
echo "  3. Install firmware for DS/3DS/PS1/PS2/Wii U/PS3."
echo
