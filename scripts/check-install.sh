#!/usr/bin/env bash
# ================================================================
#  check-install.sh — verify a GameCore installation from the outside
#
#  Run it on a freshly installed box (a VM is the right place) after
#  `sudo bash install/arch.sh --full`. It changes nothing: every check is a
#  read or a query.
#
#      bash scripts/check-install.sh
#      bash scripts/check-install.sh --json     # machine-readable summary
#
#  Why this exists: "the install finished without an error" and "the box
#  works" are different statements. arch.sh warns and carries on for a dozen
#  recoverable failures — a Flatpak that would not download, an AppImage the
#  network refused, a missing X11 session — and each one is a tile that
#  is quietly absent, or a kiosk that will not come up at the next boot.
#  Those warnings scroll past in a very long log.
#
#  Exit status: 0 when every REQUIRED check passes. Warnings never fail the
#  run — a box with no Xbox 360 emulator is degraded, not broken.
# ================================================================
set -uo pipefail

GAMECORE_PATH="${GAMECORE_PATH:-/opt/GameCore}"
# The generated config and the ROMs follow the data root, which is the
# install unless the box has been split. Checking them under GAMECORE_PATH
# on a split box would report a perfectly healthy install as broken.
GAMECORE_DATA="${GAMECORE_DATA:-$GAMECORE_PATH}"
JSON=false
[[ "${1:-}" == "--json" ]] && JSON=true

RED='\033[1;31m'; GRN='\033[1;32m'; YLW='\033[1;33m'; RST='\033[0m'
FAILED=0; WARNED=0; PASSED=0
declare -a RESULTS=()

# `set -u` is on, so the optional detail needs a default — without it every
# single-argument call aborts the run at the first check.
_record() { RESULTS+=("$1|$2|${3:-}"); }
ok()   { local d="${2:-}"; PASSED=$((PASSED+1)); _record OK   "$1" "$d"; $JSON || echo -e "  ${GRN}✓${RST} $1${d:+ — $d}"; }
warn() { local d="${2:-}"; WARNED=$((WARNED+1)); _record WARN "$1" "$d"; $JSON || echo -e "  ${YLW}⚠${RST} $1${d:+ — $d}"; }
bad()  { local d="${2:-}"; FAILED=$((FAILED+1)); _record FAIL "$1" "$d"; $JSON || echo -e "  ${RED}✗${RST} $1${d:+ — $d}"; }
head_() { $JSON || echo -e "\n\033[1;34m── $* ─────────────────────────${RST}"; }

PY="$GAMECORE_PATH/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3

# ── 1. the files are there ────────────────────────────────────────────────
head_ "Files"
for d in backend frontend electron install update catalog scripts; do
  [[ -d "$GAMECORE_PATH/$d" ]] && ok "$d/" || bad "$d/" "missing from $GAMECORE_PATH"
done
[[ -d "$GAMECORE_DATA/config" ]] && ok "config/" || bad "config/" "missing from $GAMECORE_DATA"
# scripts/ is the one the installers CALL. Leaving it out does not degrade
# anything — it breaks the install outright, and only on a real box.
for f in scripts/catalog-query.py scripts/gamecore-provider.py install/bin/gamecore-emu; do
  [[ -f "$GAMECORE_PATH/$f" ]] && ok "$f" || bad "$f" "the installers call this"
done
[[ -f "$GAMECORE_PATH/frontend/dist/index.html" ]] && ok "frontend built" \
  || bad "frontend/dist" "the UI has nothing to serve"
[[ -x "$GAMECORE_PATH/electron/node_modules/.bin/electron" \
   || -x "$GAMECORE_PATH/electron/node_modules/electron/dist/electron" ]] \
  && ok "electron binary" || bad "electron binary" "the kiosk cannot start"

# ── 2. the catalogue is coherent ──────────────────────────────────────────
head_ "Catalogue"
if [[ -f "$GAMECORE_PATH/scripts/check-catalog.py" ]]; then
  if out=$("$PY" "$GAMECORE_PATH/scripts/check-catalog.py" 2>&1); then
    ok "packs valid" "${out##*: }"
  else
    bad "packs invalid" "$(echo "$out" | head -1)"
  fi
fi
n_sys=$("$PY" -c "import json;print(len(json.load(open('$GAMECORE_DATA/config/systems.json'))))" 2>/dev/null || echo 0)
n_app=$("$PY" -c "import json;print(len(json.load(open('$GAMECORE_DATA/config/apps.json'))))" 2>/dev/null || echo 0)
[[ "$n_sys" -gt 0 ]] && ok "grid" "$n_sys systems, $n_app apps" || bad "grid" "systems.json is empty"

# A launcher naming a Flatpak nobody installed is a dead tile. This is the
# gopher64 class of failure, checked from the outside.
"$PY" - "$GAMECORE_DATA" <<'PY' 2>/dev/null | while IFS='|' read -r kind msg; do
import json, subprocess, sys
root = sys.argv[1]
try:
    rows = json.load(open(f"{root}/config/systems.json"))
except Exception:
    sys.exit(0)
try:
    r = subprocess.run(["flatpak", "list", "--app", "--columns=application"],
                       capture_output=True, text=True, timeout=60)
    installed = {l.strip() for l in r.stdout.splitlines() if l.strip()} if r.returncode == 0 else None
except Exception:
    installed = None
if installed is None:
    print("WARN|flatpak could not be queried — launcher check skipped")
    sys.exit(0)
dead = []
for s in rows:
    if s.get("path") != "flatpak":
        continue
    parts = s.get("args", "").split()
    app = parts[1] if len(parts) > 1 and parts[0] == "run" else ""
    if app and app not in installed:
        dead.append(f"{s['id']}→{app}")
print(("FAIL|dead launchers: " + ", ".join(dead)) if dead else "OK|every Flatpak launcher resolves")
PY
    case "$kind" in
      OK)   ok "launchers" "$msg" ;;
      WARN) warn "launchers" "$msg" ;;
      *)    bad "launchers" "$msg" ;;
    esac
  done

# ── 3. what the catalogue says should be installed, is ────────────────────
head_ "Emulators"
if [[ -x /usr/local/bin/gamecore-emu || -f "$GAMECORE_PATH/install/bin/gamecore-emu" ]]; then
  CLI=$(command -v gamecore-emu || echo "$GAMECORE_PATH/install/bin/gamecore-emu")
  while read -r line; do
    case "$line" in
      *OK) ok "${line%% *}" ;;
      *MISSING*) warn "${line%% *}" "${line#* }" ;;
      *"nothing to obtain") : ;;
    esac
  done < <(GAMECORE_PATH="$GAMECORE_PATH" bash "$CLI" verify 2>/dev/null | sed 's/^ *//')
fi

# ── 4. services and the kiosk chain ───────────────────────────────────────
head_ "Services"
for unit in gamecore-backend sddm; do
  en=$(systemctl is-enabled "$unit" 2>/dev/null || echo unknown)
  [[ "$en" == enabled ]] && ok "$unit enabled" || bad "$unit" "is-enabled=$en — it will not start at boot"
done
# gamecore-ui is the one unit that is legitimately off: `gamecore-session-select
# desktop` disables it on purpose, and calling that box broken would be wrong.
# It is parked, and it says so.
en=$(systemctl is-enabled gamecore-ui 2>/dev/null || echo unknown)
case "$en" in
  enabled)  ok   "gamecore-ui enabled" "kiosk mode" ;;
  disabled) warn "gamecore-ui" "disabled — desktop mode, the kiosk will not start"$'\n'"      back to the kiosk: sudo gamecore-session-select gamecore" ;;
  *)        bad  "gamecore-ui" "is-enabled=$en — it will not start at boot" ;;
esac
act=$(systemctl is-active gamecore-backend 2>/dev/null)
[[ "$act" == active ]] && ok "backend running" || bad "backend" "is-active=$act"

# The kiosk is X11-only: overlays, the fullscreen enforcer, gamecore-xsetup and
# the gamepad bridge all need X. It is hosted on the machine's own X11 desktop
# session and draws over it.
if compgen -G "/usr/share/xsessions/*.desktop" >/dev/null; then
  ok "X11 session(s) present" "$(cd /usr/share/xsessions && echo *.desktop | sed 's/\.desktop//g')"
else
  bad "no X11 session" "the box has no X session to host the kiosk"
fi
# SDDM reads /etc/sddm.conf.d/* in name order and the LAST [Autologin] wins, so
# the effective session is the last Session= across every file — not the one in
# GameCore's own drop-in, which a later-sorting file can override in silence.
sess=$(grep -h '^Session=' /etc/sddm.conf.d/*.conf 2>/dev/null | tail -1 | cut -d= -f2)
# What the session IS varies by box, so it is read back from the manifest rather
# than compared to a literal — it is the machine's own desktop session, whatever
# it is called here. Kiosk mode and desktop mode use the SAME session; only
# gamecore-ui differs, which is what the check above covers.
want=$(sed -n 's/^KIOSK_SESSION=//p' /var/lib/gamecore/manifest.env 2>/dev/null | tail -1 | tr -d "'\"")
case "$sess" in
  "")      bad "SDDM autologin" "no Session= in /etc/sddm.conf.d — no auto-login" ;;
  "$want") ok  "SDDM autologin session" "$sess" ;;
  *)       warn "SDDM autologin" "session is '$sess', the install recorded '$want'"$'\n'"      something else in /etc/sddm.conf.d/ sorts later and overrode it" ;;
esac

# ── 5. the API actually answers ───────────────────────────────────────────
head_ "API"
PORT=$(grep -oP 'GAMECORE_BACKEND_PORT=\K[0-9]+' /etc/systemd/system/gamecore-backend.service 2>/dev/null || echo 8765)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$PORT/api/sysinfo" 2>/dev/null)
[[ "$code" == 200 ]] && ok "GET /api/sysinfo" "port $PORT" || bad "API" "port $PORT answered $code"

if [[ "$code" == 200 ]]; then
  # Every tile must have an image. The logos moved into the packs, and a
  # fresh install is precisely the case where a mistake there shows up.
  blank=$("$PY" - "$PORT" <<'PY' 2>/dev/null
import json, sys, urllib.request
port = sys.argv[1]
try:
    rows = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/systems", timeout=10))
except Exception:
    print("?"); sys.exit(0)
bad = []
for s in rows:
    icon = s.get("iconPath")
    if not icon:
        bad.append(s["id"]); continue
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/{icon}", timeout=10) as r:
            if not r.read():
                bad.append(s["id"])
    except Exception:
        bad.append(s["id"])
print(",".join(bad))
PY
)
  case "$blank" in
    "")  ok "every tile has a logo" ;;
    "?") warn "logo check" "could not query /api/systems" ;;
    *)   bad "tiles with no logo" "$blank" ;;
  esac
fi

# ── 6. no personal path shipped ───────────────────────────────────────────
head_ "Hygiene"
# `-I` skips binary files. Without it this fired on __pycache__/*.pyc, which
# embed the absolute path they were compiled from — a real thing to clean up,
# but not a leak in the shipped content. The two are reported separately.
#
# The pattern is any /home/<user>/, not the one username: a tree harvested on
# someone else's machine is the same problem wearing a different name.
if grep -rIqs '/home/[a-z][a-z0-9_-]*/' "$GAMECORE_PATH/catalog" "$GAMECORE_PATH/install"/*.dist 2>/dev/null; then
  bad "harvest-box path" "an absolute /home/<user>/ path is in the shipped content"
else
  ok "no harvest-box path in the catalogue"
fi
# No __pycache__ check here on purpose. The backend imports each pack's
# generator.py through importlib, so Python writes bytecode into catalog/<id>/
# the first time a pad connects — on every healthy box. Warning about it would
# fire always and mean nothing. What mattered was that those .pyc files made
# the grep above report a leak that was not one; `-I` settles it, and the
# release archives strip them anyway.
if grep -qs '@HOME@' "$GAMECORE_DATA/config/apps.json" 2>/dev/null; then
  warn "apps.json" "@HOME@ still unsubstituted — the backend resolves it at read time, but arch.sh should have"
else
  ok "apps.json tokens resolved"
fi

# ── verdict ───────────────────────────────────────────────────────────────
if $JSON; then
  printf '{"passed":%d,"warned":%d,"failed":%d,"results":[' "$PASSED" "$WARNED" "$FAILED"
  sep=""
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r k n d <<<"$r"
    printf '%s{"status":"%s","check":"%s","detail":"%s"}' "$sep" "$k" "${n//\"/}" "${d//\"/}"
    sep=","
  done
  printf ']}\n'
else
  echo
  echo -e "  ${GRN}${PASSED} ok${RST}   ${YLW}${WARNED} warning(s)${RST}   ${RED}${FAILED} failure(s)${RST}"
  if [[ $FAILED -gt 0 ]]; then
    echo -e "\n  ${RED}This install is not usable as it stands.${RST} Each ✗ above says why."
  elif [[ $WARNED -gt 0 ]]; then
    echo -e "\n  Usable. The warnings are missing tiles, not a broken box —"
    echo "  re-run the installer once the network is back to pick them up."
  else
    echo -e "\n  ${GRN}Nothing to report.${RST}"
  fi
fi
exit $(( FAILED > 0 ? 1 : 0 ))
