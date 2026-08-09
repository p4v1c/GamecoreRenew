#!/usr/bin/env bash
# ================================================================
#  GameCore — Adapt config/systems.json to this machine
#
#  Three passes, in order:
#
#  1. SELECT   — drop every system the installer was not asked to install.
#                An unchecked emulator must not leave a tile on the TV that
#                launches something the box does not have.
#  2. REWRITE  — the reference box launches some emulators from native
#                binaries in lib/ (kept out of git — too big, machine
#                specific). On a fresh install those don't exist: every
#                system whose configured launcher is missing is rewritten to
#                its Flatpak equivalent (DuckStation to the AppImage the
#                installer downloads). Systems whose launcher exists are left
#                untouched, so re-running on the reference box is a no-op.
#  3. PRUNE    — drop anything whose launcher STILL does not resolve after
#                the rewrite: a Flatpak that failed to install, a DuckStation
#                AppImage whose download failed, Xenia without wine. A tile
#                that cannot launch is worse than no tile.
#
#  Usage:  bash install/steps/flatpakify-systems.sh [GAMECORE_PATH] [SELECTION]
#            SELECTION = "all" (default), "" (none), or a space-separated
#            list of system ids, matching arch.sh's EMULATORS.
# ================================================================
set -euo pipefail

GAMECORE_PATH="${1:-${GAMECORE_PATH:-/opt/GameCore}}"
SELECTION="${2-all}"

python3 - "$GAMECORE_PATH" "$SELECTION" <<'EOF'
import json, os, shutil, subprocess, sys

root = sys.argv[1]
selection = sys.argv[2] if len(sys.argv) > 2 else "all"
path = os.path.join(root, "config", "systems.json")
systems = json.load(open(path))
before = len(systems)

# system id → (path, args) on a Flatpak-only machine, FROM THE CATALOGUE.
#
# This was a hand-written map of six entries and it carried the pre-migration
# N64 app id (io.github.gopher64.gopher64) for months. It was harmless only by
# accident: systems.json already said "flatpak", and launcher_exists() returns
# True for that before the rewrite is ever considered. A mine, not a
# protection — the day the N64 slot goes back to a native binary, this fires
# and writes an app id nobody installs.
#
# `launch` in a pack IS the fresh-install launcher; `preferIfPresent` is what
# systems.json.dist records for the reference box's native binaries in lib/.
# So the rewrite target is simply launch, for every pack — no list to maintain,
# and a new emulator is covered the day its pack lands.
sys.path.insert(0, root)
try:
    from backend.services.catalog import load_catalog
    from backend.services.catalog.tiles import APPID_TOKEN, flatpak_app_id
    PACKS = load_catalog()
    FLATPAK_MAP = {p.id: p.launcher() for p in PACKS.values()}
    # id → every app id the pack would accept, for the prune below.
    CANDIDATES = {p.id: p.app_ids for p in PACKS.values() if p.app_ids}
except Exception as e:                       # never let this abort the install
    print(f"[flatpakify] catalogue unavailable ({e}) — launchers left as they are.")
    APPID_TOKEN = "@APPID@"
    FLATPAK_MAP, CANDIDATES = {}, {}
    def flatpak_app_id(args):
        parts = args.split()
        if not parts or parts[0] != "run":
            return ""
        return next((t for t in parts[1:] if not t.startswith("-")), "")

# ── 1. selection ────────────────────────────────────────────────
dropped_unselected = []
if selection.strip() != "all":
    keep = set(selection.split())
    kept = []
    for s in systems:
        # Only emulator entries are gated by the emulator selection; anything
        # else in the file (a tile someone added by hand) is left alone.
        if s.get("type", "emulator") == "emulator" and s.get("id") not in keep:
            dropped_unselected.append(s.get("id", "?"))
        else:
            kept.append(s)
    systems = kept


# ── 2. rewrite missing launchers to Flatpak ─────────────────────
def launcher_exists(p: str) -> bool:
    if not p:
        return False
    if p == "flatpak":
        return True                      # already flatpak — nothing to adapt
    if os.path.isabs(p):
        return os.path.exists(p)
    if "/" in p:                         # relative to the install dir only
        return os.path.exists(os.path.join(root, p))
    return shutil.which(p) is not None   # bare command → PATH lookup


changed = []
for s in systems:
    sid = s.get("id", "")
    if sid in FLATPAK_MAP and not launcher_exists(s.get("path", "")):
        s["path"], s["args"] = FLATPAK_MAP[sid]
        changed.append(sid)


# ── 3. prune what still cannot launch ───────────────────────────
# Deliberately conservative. Dropping a tile the user could have used is worse
# than keeping one that errors, so every uncertainty resolves to "keep":
#   · a Flatpak id is only pruned when `flatpak list` SUCCEEDED and returned a
#     non-empty set. An empty or failed query means we cannot see the system
#     installation (wrong scope, flatpak not initialised, sandbox) — not that
#     nothing is installed.
#   · if the prune would empty the whole grid, it is skipped entirely: that is
#     the signature of a broken probe, not of thirteen failed installs.
def _flatpak_apps():
    try:
        r = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return None
        apps = {line.strip() for line in r.stdout.splitlines() if line.strip()}
        return apps or None
    except (OSError, subprocess.SubprocessError):
        return None


FLATPAK_APPS = _flatpak_apps()


def runnable(s: dict) -> bool:
    p, args = s.get("path", ""), s.get("args", "")
    if p == "flatpak":
        if FLATPAK_APPS is None:
            return True                  # cannot tell — keep the tile
        # `flatpak_app_id`, not args.split()[1]: flatpak takes its own flags
        # after `run`, so a tile needing --socket=x11 read the flag as the
        # application id and was pruned for not being installed.
        app_id = flatpak_app_id(args)
        if app_id == APPID_TOKEN:
            # A modern tile names no id — it defers to the catalogue. Ask the
            # same question of every candidate the pack declares. Reading the
            # token as a literal id would have found it in no `flatpak list`
            # and quietly pruned EVERY Flatpak tile off a fresh install.
            wanted = CANDIDATES.get(s.get("id", ""), [])
            return not wanted or any(a in FLATPAK_APPS for a in wanted)
        return not app_id or app_id in FLATPAK_APPS
    return launcher_exists(p)


dropped_dead = []
survivors = [s for s in systems if runnable(s)]
if survivors or not systems:
    dropped_dead = [s.get("id", "?") for s in systems if not runnable(s)]
    systems = survivors
else:
    print("[flatpakify] every launcher looks missing — probe is unreliable, "
          "keeping all tiles.")

if len(systems) != before or changed:
    json.dump(systems, open(path, "w"), indent=2, ensure_ascii=False)

if dropped_unselected:
    print(f"[flatpakify] not selected, removed: {', '.join(dropped_unselected)}")
if changed:
    print(f"[flatpakify] rewritten to Flatpak launchers: {', '.join(changed)}")
if dropped_dead:
    print(f"[flatpakify] launcher missing, removed: {', '.join(dropped_dead)}")
if not (dropped_unselected or changed or dropped_dead):
    print("[flatpakify] all configured launchers exist — nothing to change.")
print(f"[flatpakify] {len(systems)} system(s) kept out of {before}.")
EOF
