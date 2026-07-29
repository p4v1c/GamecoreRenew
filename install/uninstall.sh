#!/usr/bin/env bash
# ================================================================
#  GameCore — Uninstaller
#  Manjaro / Arch Linux · reverses install/arch.sh
#
#  Reads the manifest install/arch.sh writes to /var/lib/gamecore/, so it
#  only undoes what THIS box's install actually did: packages that were
#  already present are never touched, a user account that predates GameCore
#  is never deleted, emulator configs are restored from their
#  .bak-preinstall backups rather than deleted, and a Caddyfile that was
#  there first is put back.
#
#  Without a manifest (installed by an older arch.sh, or it was deleted) it
#  falls back to reading the user and install path out of the systemd unit
#  and stays conservative: every ambiguous action defaults to "don't".
#
#  Idempotent: safe to run several times.
#
#  Run `--dry-run` first. It prints every single action and changes nothing.
# ================================================================
#
# No `set -e`, on purpose. An uninstaller that aborts on the first missing
# file leaves the machine half-cleaned, which is the one outcome worse than
# not running it at all. Every step reports its own failure and carries on.
set -uo pipefail

RED='\033[1;31m'; GRN='\033[1;32m'; YLW='\033[1;33m'
BLU='\033[1;34m'; RST='\033[0m'

msg()  { echo -e "\n${BLU}──────────────────────────────────────${RST}\n${GRN}  $*${RST}"; }
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YLW}⚠  $*${RST}"; }
info() { echo -e "  ${RST}$*"; }
die()  { echo -e "\n${RED}[ERROR]${RST} $*" >&2; exit 1; }

MANIFEST_DIR="/var/lib/gamecore"
MANIFEST="${MANIFEST_DIR}/manifest.env"
PKG_LIST="${MANIFEST_DIR}/pacman-installed"
FLATPAK_LIST="${MANIFEST_DIR}/flatpak-installed"
OVERRIDE_LIST="${MANIFEST_DIR}/flatpak-overrides"

# ── Options ──────────────────────────────────────────────────────
DRY=false
ASSUME_YES=false
PURGE=false
REMOVE_FLATPAKS=false
REMOVE_PACKAGES=false
REMOVE_USER=false
GC_USER=""
GC_PATH=""
# Set when `userdel -r` actually removed the home directory, so the closing
# summary stops promising that ~/.var/app/ was left in place — it was inside it.
HOME_DELETED=false

usage() {
  cat <<'EOF'
GameCore uninstaller

  sudo bash install/uninstall.sh [options]

Options
  --dry-run            Print every action, change nothing. Run this first.
  --yes, -y            Do not ask for confirmation.
  --purge              Also delete ROMs, covers and config/
                       (default: $GAMECORE_PATH/emu and config/ are KEPT).
  --remove-flatpaks    Uninstall the Flatpak emulators/apps THIS install added
                       (from the manifest). Save data in ~/.var/app/<id>/ is
                       KEPT — remove it yourself with
                       `flatpak uninstall --delete-data <id>` if you want it gone.
  --remove-packages    pacman -Rns the packages this install added and that
                       nothing else requires. Packages that were already on the
                       machine are never touched.
  --remove-user        Delete the GameCore Linux user and its home — only if the
                       manifest proves the installer created it.
  --user <name>        GameCore user (default: manifest, then the unit file).
  --path <dir>         Install directory (default: manifest, then the unit file).
  -h, --help           This text.

Always removed
  systemd units and drop-ins, SDDM auto-login, sudoers rules, udev rules,
  /usr/local/bin/gamecore-*, the Caddy root CA in the system trust store,
  desktop launchers, Firefox kiosk profiles, the companion checkouts in /opt,
  the stored web password, and the GameCore application files.

Kept unless you ask
  Your ROMs, config/, assets/ (uploaded bezels and logos) and lib/ (--purge),
  the Flatpak emulators (--remove-flatpaks), system packages
  (--remove-packages), the Linux user (--remove-user), and services that
  predate GameCore (sshd, bluetooth, sddm). Emulator save data in
  ~/.var/app/ is never touched.
EOF
}

ORIG_ARGS=("$@")   # kept for the re-exec below, which happens after parsing

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)         DRY=true ;;
    --yes|-y)          ASSUME_YES=true ;;
    --purge)           PURGE=true ;;
    --remove-flatpaks) REMOVE_FLATPAKS=true ;;
    --remove-packages) REMOVE_PACKAGES=true ;;
    --remove-user)     REMOVE_USER=true ;;
    --user)            GC_USER="${2:-}"; [[ -n "${2:-}" ]] || die "--user needs a value"; shift ;;
    --path)            GC_PATH="${2:-}"; [[ -n "${2:-}" ]] || die "--path needs a value"; shift ;;
    -h|--help)         usage; exit 0 ;;
    *)                 usage; die "Unknown option '$1'" ;;
  esac
  shift
done

[[ $EUID -eq 0 ]] || die "Run with sudo: sudo bash install/uninstall.sh [--dry-run]"

# This script normally lives in the very directory it is about to delete
# ($GAMECORE_PATH/install). Bash reads a script lazily, so pulling the file out
# from under it mid-run is a genuine hazard. Re-exec from a private copy first.
if [[ "${GAMECORE_UNINSTALL_RELOCATED:-}" != "1" ]]; then
  SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  RELOC="$(mktemp /tmp/gamecore-uninstall-XXXXXXXX.sh)"
  # Armed before the copy, and on signals as well as EXIT: mktemp has already
  # created the file, so any path out of here — a failed cp, a Ctrl-C — must
  # still clean it up.
  # shellcheck disable=SC2064
  trap "rm -f '$RELOC'" EXIT INT TERM HUP
  if cp "$SELF" "$RELOC" 2>/dev/null; then
    chmod +x "$RELOC"
    export GAMECORE_UNINSTALL_RELOCATED=1
    bash "$RELOC" ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}
    exit $?
  fi
  # Could not relocate (noexec /tmp, full disk…). Carry on in place and warn:
  # the install/ directory is deleted late, so this usually still works.
  warn "Could not copy myself to /tmp — running from $SELF, which I am about to delete."
fi

# ── run / rm helpers ─────────────────────────────────────────────
# Every mutating action goes through these, so --dry-run is honest: there is
# no second code path that could drift from the real one.
run() {
  if $DRY; then
    echo -e "  ${YLW}[dry-run]${RST} $*"
    return 0
  fi
  "$@"
}

# rm -rf with a guard. An empty or too-shallow path here would be a disaster,
# and several of these paths come out of a file on disk.
safe_rm() {  # safe_rm <path…>
  local p depth
  for p in "$@"; do
    [[ -n "$p" ]] || { warn "refusing to remove an empty path"; continue; }
    [[ "$p" == /* ]] || { warn "refusing to remove relative path '$p'"; continue; }
    case "$p" in
      */../*|*/..) warn "refusing to remove path with '..': $p"; continue ;;
    esac
    depth=$(awk -F/ '{print NF-1}' <<<"${p%/}")
    [[ "$depth" -ge 2 ]] || { warn "refusing to remove top-level path '$p'"; continue; }
    [[ -e "$p" || -L "$p" ]] || continue
    if run rm -rf -- "$p"; then
      $DRY || info "removed $p"
    else
      warn "could not remove $p"
    fi
  done
}

confirm() {  # confirm <prompt>
  $ASSUME_YES && return 0
  $DRY && return 0
  local answer
  read -rp "  $1 (y/N) " answer
  [[ "$answer" =~ ^[yY]$ ]]
}

# systemctl --user for the GameCore user, if its manager is actually up.
user_systemctl() {
  [[ -n "$GC_UID" && -S "/run/user/$GC_UID/bus" ]] || return 1
  if $DRY; then
    echo -e "  ${YLW}[dry-run]${RST} systemctl --user (as $GC_USER) $*"
    return 0
  fi
  sudo -u "$GC_USER" XDG_RUNTIME_DIR="/run/user/$GC_UID" systemctl --user "$@" >/dev/null 2>&1
}

# ── Locate the installation ──────────────────────────────────────
BACKEND_UNIT="/etc/systemd/system/gamecore-backend.service"
MANIFEST_FOUND=false
CADDYFILE_BACKUP=""
CADDY_WAS_ACTIVE=""
KDE_SDDM_CONF_PATCHED=0
KDE_SDDM_BACKUP=""
USER_CREATED=0
INPUT_GROUP_ADDED=0
LINGER_ENABLED=0
BRIDGE_VENV_CREATED=""

if [[ -f "$MANIFEST" ]]; then
  MANIFEST_FOUND=true
  # shellcheck disable=SC1090
  source "$MANIFEST"
  [[ -n "$GC_USER" ]] || GC_USER="${USER_NAME:-}"
  [[ -n "$GC_PATH" ]] || GC_PATH="${GAMECORE_PATH:-}"
fi

# Fallbacks: the unit the installer wrote, then whoever owns the install dir.
if [[ -z "$GC_USER" && -f "$BACKEND_UNIT" ]]; then
  GC_USER=$(awk -F= '/^User=/{print $2; exit}' "$BACKEND_UNIT")
fi
if [[ -z "$GC_PATH" && -f "$BACKEND_UNIT" ]]; then
  GC_PATH=$(awk -F= '/^Environment=GAMECORE_PATH=/{print $3; exit}' "$BACKEND_UNIT")
fi
GC_PATH="${GC_PATH:-/opt/GameCore}"
if [[ -z "$GC_USER" && -d "$GC_PATH" ]]; then
  GC_USER=$(stat -c %U "$GC_PATH" 2>/dev/null)
fi

if [[ -z "$GC_USER" ]]; then
  # No manifest, no unit, no install directory: either GameCore was never here
  # or a previous run already finished. Re-running an uninstaller must be a
  # no-op, not an error.
  if ! $MANIFEST_FOUND && [[ ! -f "$BACKEND_UNIT" && ! -d "$GC_PATH" ]]; then
    echo
    ok "GameCore does not appear to be installed — nothing to do."
    info "If it is installed somewhere unusual:  --user <name> --path <dir>"
    exit 0
  fi
  die "Could not determine the GameCore user — pass --user <name>."
fi

if id "$GC_USER" >/dev/null 2>&1; then
  GC_HOME=$(getent passwd "$GC_USER" | cut -d: -f6)
  GC_UID=$(id -u "$GC_USER")
else
  warn "User '$GC_USER' does not exist (already removed?) — home-directory cleanup will be skipped."
  GC_HOME=""; GC_UID=""
fi

echo -e "\n${BLU}╔══════════════════════════════════════╗${RST}"
echo -e "${BLU}║     GameCore — Uninstaller           ║${RST}"
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"
echo
info "User          : $GC_USER${GC_HOME:+  (home: $GC_HOME)}"
info "Install path  : $GC_PATH"
if $MANIFEST_FOUND; then
  info "Manifest      : $MANIFEST"
else
  info "Manifest      : not found — conservative mode (nothing ambiguous is touched)"
fi
info "ROMs & config : $($PURGE && echo 'DELETED (--purge)' || echo 'kept')"
info "Flatpaks      : $($REMOVE_FLATPAKS && echo 'remove the ones we installed' || echo 'kept')"
info "Packages      : $($REMOVE_PACKAGES && echo 'remove the ones we installed' || echo 'kept')"
info "Linux user    : $($REMOVE_USER && echo "delete '$GC_USER' if we created it" || echo 'kept')"
$DRY && echo -e "\n  ${YLW}DRY RUN — nothing will be modified.${RST}"
echo

if ! $DRY; then
  $PURGE && warn "--purge will DELETE YOUR ROMs, covers and configuration under $GC_PATH."
  $REMOVE_FLATPAKS && info "--remove-flatpaks keeps save data in ~/.var/app/ — only the apps go."
  confirm "Continue?" || die "Aborted."
fi

# ================================================================
#  1. Stop the stack — restart unit first
# ================================================================
msg "Stopping GameCore"

# gamecore-restart.service goes FIRST. It is a oneshot that restarts the two
# services after a 2 s sleep; if an OTA queued it, it would resurrect
# everything we are about to stop. It has no [Install] section, so `disable`
# is a no-op — that is expected, not an error.
if [[ -f /etc/systemd/system/gamecore-restart.service ]]; then
  run systemctl stop gamecore-restart.service 2>/dev/null
  ok "gamecore-restart.service stopped (no more queued OTA restarts)."
fi

# UI before backend: the UI Requires= the backend, and letting systemd cascade
# the stop has left stray Electron processes behind.
for unit in gamecore-ui.service gamecore-backend.service; do
  if [[ -f "/etc/systemd/system/$unit" ]]; then
    run systemctl stop "$unit" 2>/dev/null
    run systemctl disable "$unit" 2>/dev/null
    ok "$unit stopped and disabled."
  fi
done

# A running emulator is NOT in any unit's cgroup — the backend spawns it with
# start_new_session=True — so stopping the backend does not kill a game.
if command -v flatpak >/dev/null 2>&1 && [[ -n "$(flatpak ps --columns=application 2>/dev/null)" ]]; then
  warn "Flatpak apps are still running: $(flatpak ps --columns=application 2>/dev/null | tr '\n' ' ')"
  warn "  Close them before continuing if one of them is a game with unsaved progress."
fi
if [[ -n "$GC_UID" ]]; then
  for proc in electron unclutter; do
    if pgrep -u "$GC_UID" -x "$proc" >/dev/null 2>&1; then
      run pkill -u "$GC_UID" -x "$proc"
      ok "stray $proc killed."
    fi
  done
fi

# ================================================================
#  2. Addons — while the CLI and the checkout still exist
# ================================================================
msg "Addons"
ADDON_CLI="/usr/local/bin/gamecore-addon"
REGISTRY="$GC_PATH/config/addons.json"
if [[ -x "$ADDON_CLI" && -f "$REGISTRY" ]]; then
  mapfile -t INSTALLED_ADDONS < <(python3 -c '
import json, sys
try:
    print("\n".join(sorted(json.load(open(sys.argv[1])))))
except Exception:
    pass
' "$REGISTRY" 2>/dev/null)
  if [[ ${#INSTALLED_ADDONS[@]} -gt 0 ]]; then
    for addon in "${INSTALLED_ADDONS[@]}"; do
      [[ -n "$addon" ]] || continue
      if $DRY; then
        echo -e "  ${YLW}[dry-run]${RST} gamecore-addon remove $addon"
      elif sudo -u "$GC_USER" -H \
             env GAMECORE_PATH="$GC_PATH" XDG_RUNTIME_DIR="/run/user/${GC_UID:-0}" \
             "$ADDON_CLI" remove "$addon" >/dev/null 2>&1; then
        ok "addon '$addon' removed."
      else
        warn "addon '$addon' did not uninstall cleanly — its units are swept below."
      fi
    done
  else
    info "No addon registered."
  fi
elif [[ -f "$REGISTRY" ]]; then
  warn "Addons are registered but /usr/local/bin/gamecore-addon is gone —"
  warn "  they cannot uninstall themselves. Their units are swept below,"
  warn "  but check for leftovers in /opt/gamecore-addons before it is deleted."
else
  info "No addon registry — nothing to uninstall."
fi

# ================================================================
#  3. User and system units left by addons and companions
# ================================================================
msg "User services"
if [[ -n "$GC_HOME" && -d "$GC_HOME/.config/systemd/user" ]]; then
  UNIT_DIR="$GC_HOME/.config/systemd/user"
  USER_UNITS=(embertv.service gamepad-tv-bridge.service)
  # Sweep-up net for addons whose own uninstall.sh failed or whose checkout
  # was already gone.
  while IFS= read -r u; do
    [[ -n "$u" ]] && USER_UNITS+=("$(basename "$u")")
  done < <(find "$UNIT_DIR" -maxdepth 1 -name 'gamecore-addon-*.service' 2>/dev/null)

  for unit in "${USER_UNITS[@]}"; do
    [[ -e "$UNIT_DIR/$unit" ]] || continue
    user_systemctl disable --now "$unit" || true
    safe_rm "$UNIT_DIR/$unit" \
            "$UNIT_DIR/default.target.wants/$unit" \
            "$UNIT_DIR/graphical-session.target.wants/$unit"
    ok "$unit removed."
  done
  user_systemctl daemon-reload || true

  # rmdir, never rm -rf: the user may keep their own units in there.
  run rmdir "$UNIT_DIR/default.target.wants" 2>/dev/null
  run rmdir "$UNIT_DIR/graphical-session.target.wants" 2>/dev/null
  run rmdir "$UNIT_DIR" 2>/dev/null
fi

# Addons that declare `service: system` install a root unit — the user-unit
# sweep above never sees those.
for u in /etc/systemd/system/gamecore-addon-*.service; do
  [[ -e "$u" ]] || continue
  run systemctl disable --now "$(basename "$u")" 2>/dev/null
  safe_rm "$u"
  ok "$(basename "$u") removed (system-scoped addon)."
done

if [[ "$LINGER_ENABLED" == "1" ]]; then
  run loginctl disable-linger "$GC_USER" 2>/dev/null && ok "linger disabled for $GC_USER."
elif [[ -n "$GC_UID" ]]; then
  info "linger left as it was (it was already on, or unknown — see the manifest)."
fi

# ================================================================
#  4. Emulator configs — restore, do not delete
# ================================================================
# install-emu-configs.sh copies emu-configs/<emu>/** into each emulator's real
# config dir, saving any pre-existing file as <name>.bak-preinstall. Reversing
# it means putting every backup back and deleting only the files GameCore
# introduced. Everything else in ~/.var/app/ — save states, memory cards,
# BIOS, the user's own tweaks — is never touched.
#
# Runs BEFORE the install dir goes (emu-configs/ is the only list of which
# files were touched) and BEFORE any flatpak uninstall (which wipes ~/.var/app).
msg "Emulator configurations"
declare -A RESTORED_TARGETS=()
if [[ -n "$GC_HOME" && -d "$GC_PATH/emu-configs" ]]; then
  declare -A EMU_DEST=(
    [duckstation]="$GC_HOME/.local/share/duckstation"
    [pcsx2]="$GC_HOME/.var/app/net.pcsx2.PCSX2/config/PCSX2/inis"
    [rpcs3]="$GC_HOME/.var/app/net.rpcs3.RPCS3/config/rpcs3"
    [gopher64]="$GC_HOME/.var/app/io.github.gopher64.gopher64/config/gopher64"
    [melonds]="$GC_HOME/.var/app/net.kuribo64.melonDS/config/melonDS"
    [mgba]="$GC_HOME/.var/app/io.mgba.mGBA/config/mgba"
    [azahar]="$GC_HOME/.var/app/org.azahar_emu.Azahar/config/azahar-emu"
    [dolphin]="$GC_HOME/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"
    [ppsspp]="$GC_HOME/.var/app/org.ppsspp.PPSSPP/config/ppsspp/PSP/SYSTEM"
    [cemu]="$GC_HOME/.var/app/info.cemu.Cemu/config/Cemu"
    [ryujinx]="$GC_HOME/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx"
    [shadps4]="$GC_HOME/.var/app/net.shadps4.shadPS4/config/shadps4"
    [xenia]="$GC_PATH/lib/xenia"
  )
  RESTORED=0; DELETED=0
  for emu in "${!EMU_DEST[@]}"; do
    src="$GC_PATH/emu-configs/$emu"
    dest="${EMU_DEST[$emu]}"
    [[ -d "$src" && -d "$dest" ]] || continue
    while IFS= read -r -d '' f; do
      rel="${f#"$src"/}"
      tgt="${dest}/${rel}"
      if [[ -f "${tgt}.bak-preinstall" ]]; then
        run mv -f "${tgt}.bak-preinstall" "$tgt" && { RESTORED=$((RESTORED + 1)); RESTORED_TARGETS["$tgt"]=1; }
      elif [[ -f "$tgt" ]]; then
        run rm -f -- "$tgt" && DELETED=$((DELETED + 1))
      fi
    done < <(find "$src" -type f -print0 2>/dev/null)
  done
  ok "emulator configs: $RESTORED restored from backup, $DELETED GameCore files removed."
  info "Save states, memory cards and BIOS in ~/.var/app/ are untouched."
else
  info "No emu-configs/ to reverse — skipping."
fi

# install/apply-multi-ds4.sh (run by hand, not by the installer) leaves its own
# .bak-multids4 backups. Restore them only where emu-configs had no backup of
# its own — otherwise the .bak-preinstall we just put back is the older, more
# correct "before" state and the multi-ds4 copy is stale.
if [[ -n "$GC_HOME" ]]; then
  MDS4=0
  while IFS= read -r -d '' bak; do
    tgt="${bak%.bak-multids4}"
    if [[ -n "${RESTORED_TARGETS[$tgt]:-}" ]]; then
      run rm -f -- "$bak"
    else
      run mv -f "$bak" "$tgt" && MDS4=$((MDS4 + 1))
    fi
  done < <(find "$GC_HOME/.var/app" "$GC_HOME/.local/share/duckstation" \
                -name '*.bak-multids4' -print0 2>/dev/null)
  [[ $MDS4 -gt 0 ]] && ok "$MDS4 controller config(s) restored from apply-multi-ds4 backups."
fi

# ================================================================
#  5. systemd system units
# ================================================================
msg "systemd units"
safe_rm /etc/systemd/system/gamecore-backend.service \
        /etc/systemd/system/gamecore-ui.service \
        /etc/systemd/system/gamecore-restart.service \
        /etc/systemd/system/gamecore-backend.service.d \
        /etc/systemd/system/multi-user.target.wants/gamecore-backend.service \
        /etc/systemd/system/graphical.target.wants/gamecore-ui.service
run systemctl daemon-reload
run systemctl reset-failed gamecore-backend.service gamecore-ui.service gamecore-restart.service 2>/dev/null
ok "units removed (incl. the drop-in holding the TheGamesDB key)."

# ================================================================
#  6. SDDM auto-login and the 1080p display command
# ================================================================
msg "SDDM"
safe_rm /etc/sddm.conf.d/zz-gamecore-autologin.conf \
        /etc/sddm.conf.d/zz-gamecore-display.conf \
        /etc/sddm.conf.d/gamecore-display.conf

# Older installs used the generic name autologin.conf — which is also a name a
# user may have picked themselves. Only remove it if it is ours.
if [[ -f /etc/sddm.conf.d/autologin.conf ]]; then
  if grep -q "^User=${GC_USER}\$" /etc/sddm.conf.d/autologin.conf 2>/dev/null \
     && grep -q '^Session=plasma' /etc/sddm.conf.d/autologin.conf 2>/dev/null; then
    safe_rm /etc/sddm.conf.d/autologin.conf
  else
    warn "/etc/sddm.conf.d/autologin.conf does not look like GameCore's — left in place."
  fi
fi

# Put the user's own [Autologin] block back if we stripped it.
KDE_SDDM_CONF=/etc/sddm.conf.d/kde_settings.conf
# Older installs kept the backup next to the original; look in both places.
for b in "${KDE_SDDM_BACKUP:-}" "${MANIFEST_DIR}/kde_settings.conf.pre-gamecore" \
         "${KDE_SDDM_CONF}.pre-gamecore"; do
  [[ -n "$b" && -f "$b" ]] || continue
  run mv -f "$b" "$KDE_SDDM_CONF" \
    && ok "kde_settings.conf restored to its pre-GameCore contents."
  KDE_SDDM_RESTORED=1
  break
done
safe_rm "${KDE_SDDM_CONF}.pre-gamecore"
if [[ -n "${KDE_SDDM_RESTORED:-}" ]]; then
  :
elif [[ "$KDE_SDDM_CONF_PATCHED" == "1" ]]; then
  warn "kde_settings.conf was modified but its backup is gone — check your login settings."
fi
ok "SDDM drop-ins removed — the distribution defaults apply again."
warn "The login screen will ask for a password again on the next boot."

# ================================================================
#  7. Helper binaries, sudoers, udev
# ================================================================
msg "System integration"
# gamecore-addon last among the addon steps — its own `remove` needed it.
safe_rm /usr/local/bin/gamecore-xsetup /usr/local/bin/gamecore-addon

safe_rm /etc/sudoers.d/gamecore-power /etc/sudoers.d/gamecore-update /etc/sudoers.d/gamecore-standby
if $DRY || visudo -c >/dev/null 2>&1; then
  ok "sudoers rules removed (/etc/sudoers still parses)."
else
  warn "/etc/sudoers does not parse cleanly — check it before logging out!"
fi

safe_rm /etc/udev/rules.d/99-gamecore-input.rules \
        /etc/udev/rules.d/99-ds4-controllers.rules \
        /etc/udev/rules.d/99-uinput.rules \
        /etc/modules-load.d/uinput.conf
run udevadm control --reload-rules 2>/dev/null
run udevadm trigger 2>/dev/null
ok "udev rules removed and reloaded."
info "The uinput module is left loaded — other software (ydotool, Steam Input) may need it."

if [[ "$INPUT_GROUP_ADDED" == "1" ]]; then
  if id -nG "$GC_USER" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
    run gpasswd -d "$GC_USER" input >/dev/null 2>&1 && ok "$GC_USER removed from the 'input' group."
  fi
else
  info "'input' group membership left alone (it predates GameCore, or is unknown)."
fi

# ================================================================
#  8. Caddy
# ================================================================
msg "Caddy reverse-proxy"
CADDYFILE_IS_OURS=false
[[ -f /etc/caddy/Caddyfile ]] && grep -q 'GameCore' /etc/caddy/Caddyfile 2>/dev/null && CADDYFILE_IS_OURS=true

# `caddy untrust` FIRST, while the service is still running and the config is
# still ours: with no --cert it fetches the root certificate from the admin
# API. Leaving this CA installed means the machine permanently trusts a
# private CA whose key sits in /var/lib/caddy — a silent security regression.
if command -v caddy >/dev/null 2>&1; then
  if run caddy untrust >/dev/null 2>&1; then
    ok "Caddy root CA removed from the system trust store."
  else
    warn "'caddy untrust' failed — removing the anchor by hand."
    for c in /etc/ca-certificates/trust-source/anchors/Caddy_Local_Authority*.crt; do
      [[ -e "$c" ]] && safe_rm "$c"
    done
    run trust extract-compat 2>/dev/null
  fi
fi

# Two independent decisions, deliberately not chained: (1) what config should
# be in place afterwards, (2) whether caddy should keep running. Folding them
# into one if/elif is how the CA private key used to survive an uninstall.

# (1) config
if [[ -n "$CADDYFILE_BACKUP" && -f "$CADDYFILE_BACKUP" ]]; then
  run mv -f "$CADDYFILE_BACKUP" /etc/caddy/Caddyfile \
    && ok "the Caddyfile that was here before GameCore is back."
elif $CADDYFILE_IS_OURS && pacman -Qo /etc/caddy/Caddyfile >/dev/null 2>&1; then
  # /etc/caddy/Caddyfile is a pacman `backup=` file, and pacman NEVER overwrites
  # one it has marked [modified] — a plain reinstall silently leaves GameCore's
  # config in place. Removing it first makes pacman see the backup file as
  # missing, which is the one case where it does reinstall it.
  if $DRY; then
    echo -e "  ${YLW}[dry-run]${RST} rm /etc/caddy/Caddyfile && pacman -S --noconfirm caddy   (restore the packaged default)"
  else
    rm -f /etc/caddy/Caddyfile
    pacman -S --noconfirm caddy >/dev/null 2>&1
    if [[ -f /etc/caddy/Caddyfile ]] && ! grep -q 'GameCore' /etc/caddy/Caddyfile; then
      ok "packaged /etc/caddy/Caddyfile restored."
    else
      warn "could not restore the packaged Caddyfile — /etc/caddy/Caddyfile is now absent."
      warn "  Reinstall it with: sudo pacman -S caddy"
    fi
  fi
elif ! $CADDYFILE_IS_OURS; then
  info "/etc/caddy/Caddyfile is not GameCore's — left untouched."
fi

# (2) service and CA
if [[ "$CADDY_WAS_ACTIVE" == "active" ]]; then
  info "caddy was serving something before GameCore — left enabled."
  run systemctl restart caddy.service 2>/dev/null
elif $CADDYFILE_IS_OURS || [[ -n "$CADDYFILE_BACKUP" ]] || ! $MANIFEST_FOUND; then
  if systemctl is-enabled caddy.service >/dev/null 2>&1 || systemctl is-active caddy.service >/dev/null 2>&1; then
    run systemctl disable --now caddy.service 2>/dev/null && ok "caddy.service stopped and disabled."
  fi
  # The local CA *and its private key*. Leaving it means the machine keeps a
  # private CA whose key is on disk, trusted by every device that installed it.
  safe_rm /var/lib/caddy/pki
fi

# ================================================================
#  9. Desktop launchers, kiosk profiles, Electron state
# ================================================================
msg "Desktop integration"
if [[ -n "$GC_HOME" ]]; then
  # Resolve DESKTOP the way arch.sh did — on a localized session this is not
  # ~/Desktop (fr: ~/Bureau).
  DESKTOP_DIR=$(sudo -u "$GC_USER" bash -lc 'xdg-user-dir DESKTOP 2>/dev/null' 2>/dev/null)
  [[ -n "$DESKTOP_DIR" && -d "$DESKTOP_DIR" ]] || DESKTOP_DIR="$GC_HOME/Desktop"
  safe_rm "$DESKTOP_DIR/GameCore.desktop" \
          "$GC_HOME/.local/share/applications/gamecore.desktop"
  run sudo -u "$GC_USER" update-desktop-database "$GC_HOME/.local/share/applications" 2>/dev/null

  # Bare profile directories, never registered in profiles.ini — the user's
  # real Firefox profile lives in the same parent and is not touched.
  safe_rm "$GC_HOME/.mozilla/firefox/youtube-tv" "$GC_HOME/.mozilla/firefox/twitch-tv"
  # Electron user data (caches, local storage) — pure GameCore state.
  safe_rm "$GC_HOME/.config/gamecore-electron" "$GC_HOME/.config/GameCore"
  ok "launchers, kiosk profiles and Electron state removed."
fi

# ================================================================
#  10. Companion projects
# ================================================================
msg "Companion projects"
# /opt/Twitch-TV/config.json holds the Twitch client secret in cleartext.
safe_rm /opt/Twitch-TV /opt/gamepad-tv-bridge /opt/Stremio /opt/gamecore-addons

# ~/.venv is where arch.sh pip-installs the gamepad bridge — and it is the most
# generic virtualenv path on Linux. arch.sh reuses an existing one, so deleting
# it blindly can destroy the user's own environment.
if [[ -n "$GC_HOME" && -d "$GC_HOME/.venv" ]]; then
  # The distribution is `gamepad-tv-bridge` (site-packages: gamepad_tv_bridge-*),
  # and it drags in its own dependency tree — so "are there other packages in
  # here?" is useless as a test: the answer is always yes. The manifest records
  # whether the installer created this venv, which is the only reliable signal.
  if compgen -G "$GC_HOME/.venv/lib/python*/site-packages/*gamepad*bridge*" >/dev/null 2>&1 \
     || [[ -e "$GC_HOME/.venv/bin/gamepad-bridge" ]]; then
    if [[ "${BRIDGE_VENV_CREATED:-}" == "1" ]]; then
      safe_rm "$GC_HOME/.venv"
      ok "gamepad-tv-bridge virtualenv removed (GameCore created it)."
    else
      if [[ "${BRIDGE_VENV_CREATED:-}" == "0" ]]; then
        info "$GC_HOME/.venv predates GameCore — uninstalling only the bridge."
      else
        info "Cannot tell who created $GC_HOME/.venv — uninstalling only the bridge."
      fi
      run sudo -u "$GC_USER" -H "$GC_HOME/.venv/bin/pip" uninstall -y -q gamepad-tv-bridge 2>/dev/null \
        && ok "gamepad-tv-bridge uninstalled from the venv." \
        || warn "pip uninstall failed — remove gamepad-tv-bridge from $GC_HOME/.venv by hand."
    fi
  else
    warn "$GC_HOME/.venv is not the gamepad bridge venv — kept."
  fi
fi

# Temp files, including the wizard's conf — it holds the Twitch secret, the
# TheGamesDB key and the web password in cleartext.
msg "Temporary files"
for f in /tmp/gamecore-install-*.conf; do
  [[ -e "$f" ]] || continue
  if $DRY; then echo -e "  ${YLW}[dry-run]${RST} shred -u $f"
  else shred -u "$f" 2>/dev/null || rm -f "$f"; fi
  ok "removed $f (contained installer secrets)."
done
safe_rm /tmp/gamecore_ota /tmp/gamecore-installer-addons /tmp/xenia_canary_pkg
for d in /tmp/gamecore-src-* /tmp/gamecore-xenia-*; do
  [[ -e "$d" ]] && safe_rm "$d"
done

# ================================================================
#  11. Flatpak applications
# ================================================================
msg "Flatpak applications"
if $REMOVE_FLATPAKS; then
  if [[ -f "$FLATPAK_LIST" ]]; then
    mapfile -t FLATPAKS_TO_REMOVE < <(grep -v '^[[:space:]]*$' "$FLATPAK_LIST")
    info "the manifest records ${#FLATPAKS_TO_REMOVE[@]} Flatpak(s) installed by GameCore."
    for app in ${FLATPAKS_TO_REMOVE[@]+"${FLATPAKS_TO_REMOVE[@]}"}; do
      [[ -n "$app" ]] || continue
      flatpak list --app --columns=application 2>/dev/null | grep -qxF "$app" || continue
      # Steam's data directory can hold hundreds of GB of installed games.
      # GameCore did install it, so removing it is defensible — but never
      # without asking a second time.
      if [[ "$app" == "com.valvesoftware.Steam" ]]; then
        warn "Steam was installed by GameCore. Your library in"
        warn "  ~/.var/app/com.valvesoftware.Steam is kept, but Steam itself goes."
        confirm "Really uninstall Steam?" || { info "Steam kept."; continue; }
      fi
      run flatpak override --reset "$app" 2>/dev/null
      run flatpak uninstall -y --noninteractive "$app" 2>/dev/null \
        && ok "$app removed." || warn "$app could not be removed."
    done
    info "Reclaim the runtimes with:  flatpak uninstall --unused"
    info "Delete leftover app data with: flatpak uninstall --delete-data <app-id>"
  else
    warn "No Flatpak manifest — refusing to guess which emulators predate GameCore."
    info "Remove them yourself if you want to:  flatpak uninstall <app-id>"
  fi
else
  info "kept (pass --remove-flatpaks to uninstall the ones GameCore added)."
fi

# Whatever happens above, the --filesystem=$GC_PATH override now points at a
# directory that is about to disappear. Reset every app GameCore re-permissioned
# — including ones it did not install, which the flatpak-installed list misses.
if [[ -f "$OVERRIDE_LIST" ]]; then
  RESET=0
  while IFS= read -r app; do
    [[ -n "$app" ]] || continue
    flatpak list --app --columns=application 2>/dev/null | grep -qxF "$app" || continue
    run flatpak override --reset "$app" 2>/dev/null
    run flatpak override --user --reset "$app" 2>/dev/null
    RESET=$((RESET + 1))
  done < "$OVERRIDE_LIST"
  if [[ $RESET -gt 0 ]]; then
    ok "Flatpak sandbox overrides reset on $RESET app(s) (ROM path + device access)."
    warn "This also clears permissions you may have set yourself on those apps."
  fi
fi

# ================================================================
#  12. pacman packages
# ================================================================
msg "System packages"
if $REMOVE_PACKAGES; then
  if [[ -f "$PKG_LIST" ]]; then
    mapfile -t CANDIDATES < <(grep -v '^[[:space:]]*$' "$PKG_LIST")
    REMOVABLE=()
    # Never remove anything that would take the desktop or the boot with it,
    # however the manifest got there.
    NEVER='^(plasma-desktop|plasma-x11-session|sddm|mesa|base-devel|linux[0-9-]*-headers|linux-headers|nvidia.*|.*-nvidia|vulkan-.*|lib32-.*|xf86-video-.*|amd-ucode|firefox|nss|git|python|python-pip|openssh|dkms)$'
    for p in ${CANDIDATES[@]+"${CANDIDATES[@]}"}; do
      pacman -Qq "$p" >/dev/null 2>&1 || continue
      if [[ "$p" =~ $NEVER ]]; then
        info "$p — kept (removing it could break the desktop or boot)."
        continue
      fi
      if LC_ALL=C pacman -Qi "$p" 2>/dev/null | awk -F': ' '/^Required By/{print $2}' | grep -qv '^None$'; then
        info "$p — kept (another package requires it)."
        continue
      fi
      REMOVABLE+=("$p")
    done
    if [[ ${#REMOVABLE[@]} -gt 0 ]]; then
      info "would remove: ${REMOVABLE[*]}"
      if confirm "Remove ${#REMOVABLE[@]} package(s)?"; then
        run pacman -Rns --noconfirm "${REMOVABLE[@]}" && ok "packages removed." \
          || warn "pacman removal failed — remove them by hand."
      else
        info "skipped."
      fi
    else
      info "nothing safe to remove."
    fi
  else
    warn "No package manifest — refusing to guess which packages predate GameCore."
    info "GameCore realistically adds only:  caddy  unclutter"
  fi
else
  info "kept (pass --remove-packages to remove the ones GameCore added)."
fi

# ================================================================
#  13. Application files
# ================================================================
msg "Application files"
# The stored web password and cookie key go regardless of --purge: they live
# under config/, which the default path preserves, and leaving an argon2 hash
# and an HMAC key behind after removal is not acceptable.
safe_rm "$GC_PATH/config/auth.json" "$GC_PATH/config/auth_secret"

if [[ -d "$GC_PATH" ]]; then
  if $PURGE; then
    safe_rm "$GC_PATH"
    ok "$GC_PATH deleted, ROMs and configuration included."
  else
    # `assets` is kept alongside emu/ and config/: assets/overlays holds the
    # bezels the user uploaded through the ROM manager and assets/logos their
    # custom system art — update/linux.sh excludes both from the OTA rsync for
    # exactly that reason. A few hundred KB of bundled artwork stays behind
    # with them, which is a much better trade than deleting someone's bezels.
    # `lib` too: lib/xenia holds Xbox 360 content and the user may have put
    # native emulator binaries there (it is gitignored).
    while IFS= read -r -d '' entry; do
      case "$(basename "$entry")" in
        emu|config|assets|lib) continue ;;
      esac
      safe_rm "$entry"
    done < <(find "$GC_PATH" -mindepth 1 -maxdepth 1 -print0 2>/dev/null)
    if $DRY; then
      info "[dry-run] emu/ and config/ would be kept in $GC_PATH"
    else
      ok "application files removed."
      info "Kept: $GC_PATH/{emu (ROMs), config, assets (your bezels/logos), lib}"
      info "Delete them yourself, or re-run with --purge."
    fi
  fi
  # electron/node_modules/electron/dist/chrome-sandbox is SUID root. A stray
  # SUID binary after a partial uninstall is a real privilege-escalation
  # surface, so prove it is gone.
  if ! $DRY && [[ -d "$GC_PATH" ]]; then
    LEFT=$(find "$GC_PATH" -perm -4000 -type f 2>/dev/null)
    [[ -n "$LEFT" ]] && warn "SUID binaries still present under $GC_PATH:"$'\n'"$LEFT"
  fi
else
  info "$GC_PATH does not exist."
fi

# ================================================================
#  14. The Linux user
# ================================================================
if $REMOVE_USER; then
  msg "Linux user"
  if ! $MANIFEST_FOUND; then
    warn "No manifest — cannot prove GameCore created '$GC_USER'. NOT deleting it."
    info "If you are sure:  sudo userdel -r $GC_USER"
  elif [[ "$USER_CREATED" != "1" ]]; then
    warn "'$GC_USER' existed before GameCore was installed — NOT deleting it."
  elif [[ "$GC_USER" == "root" ]]; then
    warn "refusing to delete root."
  elif confirm "Delete user '$GC_USER' and its home directory $GC_HOME?"; then
    # No blanket `pkill -u`: it would kill the SSH session running this very
    # script and abandon the remaining steps. userdel reports the problem
    # perfectly well on its own.
    if run userdel -r "$GC_USER" 2>/dev/null; then
      ok "user '$GC_USER' deleted."
      # -r took the home directory with it, and ~/.var/app/ lives inside it.
      # The summary must stop claiming the emulator saves were left alone.
      HOME_DELETED=true
    else
      warn "userdel failed — log '$GC_USER' out (loginctl terminate-user $GC_USER), then re-run."
    fi
  fi
fi

# ================================================================
#  15. CPU governor and the manifest
# ================================================================
msg "Final touches"
# arch.sh pins the governor to `performance`. Left alone, the box burns idle
# power forever after GameCore is gone. Restore a sane default rather than
# disabling cpupower.service, which may predate GameCore.
if command -v cpupower >/dev/null 2>&1 && [[ -d /sys/devices/system/cpu/cpu0/cpufreq ]]; then
  if grep -qw schedutil /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors 2>/dev/null; then
    run cpupower frequency-set -g schedutil >/dev/null 2>&1 \
      && ok "CPU governor back to schedutil (was pinned to performance)."
  fi
fi

safe_rm "$MANIFEST" "$PKG_LIST" "$FLATPAK_LIST" "$OVERRIDE_LIST"
run rmdir "$MANIFEST_DIR" 2>/dev/null

# ── Summary ──────────────────────────────────────────────────────
echo
echo -e "${BLU}╔══════════════════════════════════════╗${RST}"
if $DRY; then
  echo -e "${BLU}║   Dry run complete — no changes      ║${RST}"
else
  echo -e "${BLU}║   GameCore removed                   ║${RST}"
fi
echo -e "${BLU}╚══════════════════════════════════════╝${RST}"
echo
if ! $DRY; then
  ok "GameCore no longer starts at boot."
  $PURGE || info "Your ROMs are still in $GC_PATH/emu"
  echo
  echo -e "${YLW}  Left in place on purpose:${RST}"
  echo "  · sshd, bluetooth and sddm — system services that likely predate GameCore"
  echo "    (GameCore did enable sshd: 'sudo systemctl disable --now sshd' if you want it closed)"
  $HOME_DELETED || echo "  · emulator save data in ~/.var/app/ (flatpak uninstall --delete-data <id>)"
  $REMOVE_FLATPAKS || echo "  · the Flatpak emulators themselves"
  $REMOVE_PACKAGES || echo "  · the system packages GameCore added"
  echo
  echo -e "${YLW}  Cannot be undone:${RST}"
  echo "  · the full 'pacman -Syu' the installer ran — your system stays upgraded"
  echo "  · config/systems.json and config/apps.json were rewritten in place"
  echo
  echo "  Reboot to land on a normal desktop session."
fi
