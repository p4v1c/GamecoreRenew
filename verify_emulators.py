"""Check that everything the catalogue says to install still exists upstream.

Driven by catalog/<id>/pack.json, and that matters: this list used to be
hand-written and still carried io.github.gopher64.gopher64 long after the N64
slot moved to Rosalie's Mupen GUI. It reported a healthy Flathub entry for an
application nobody installs — green on the wrong target, which is worse than
red. Reading the catalogue is what turns this into the job that would have
caught the whole thing.

A pack declares an ORDERED list of app ids, so the question is per pack and
not per id: a pack is healthy when at least one candidate still resolves, and
degraded — worth an issue, not a red install — when its preferred one is gone
and a fallback is carrying it. A pack whose whole list is dead is the failure
this job exists to catch, a week before a player does.

Needs the network. Run it on a schedule, not on every push: CI must not go red
because Flathub is slow. Exits non-zero only on a finding, so the workflow can
tell "nothing to report" from "Flathub said no".
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.services.catalog import load_catalog  # noqa: E402

# --no-probe territory: this runs in CI, where no emulator is installed and
# `flatpak` does not exist. Reading the DECLARED order is the whole point —
# we are checking the catalogue against upstream, not a box against itself.
_PACKS = load_catalog()

FLATPAK_PACKS = [(p.id, p.app_ids)
                 for p in sorted(_PACKS.values(), key=lambda p: p.id) if p.app_ids]

# The two emulators that do not come from Flathub, and where their releases
# live. Also from the catalogue: `github-asset` / `github-archive` providers.
GITHUB_ASSETS = [
    (p.id, p.data["install"]["repo"], p.data["install"].get("assetPattern")
     or p.data["install"]["asset"])
    for p in sorted(_PACKS.values(), key=lambda p: p.id)
    if (p.data.get("install") or {}).get("provider", "").startswith("github-")
]

def check_flatpak(app_id):
    # Flathub API v2
    url = f"https://flathub.org/api/v2/appstream/{app_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True, "OK"
        elif response.status_code == 404:
            return False, "Not Found"
        else:
            return False, f"Error {response.status_code}"
    except Exception as e:
        return False, str(e)

def check_github_release_asset(repo, pattern):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            assets = data.get("assets", [])
            for asset in assets:
                if pattern in asset.get("browser_download_url", ""):
                    return True, f"Found: {asset.get('name')}"
            return False, f"Asset matching '{pattern}' not found in latest release"
        elif response.status_code == 404:
            return False, "Repo not found"
        else:
            return False, f"Error {response.status_code}"
    except Exception as e:
        return False, str(e)

def check_url(url):
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            return True, "OK"
        else:
            return False, f"Error {response.status_code}"
    except Exception as e:
        return False, str(e)

def main():
    print("Verifying Emulators and Resources existence...")
    print("-" * 50)

    results = []
    degraded = []

    print("\nChecking Flatpaks on Flathub:")
    for pack_id, app_ids in FLATPAK_PACKS:
        alive = []
        for app_id in app_ids:
            exists, status = check_flatpak(app_id)
            marker = "\u2713" if exists else "\u2717"
            print(f"[{marker}] {app_id:35} : {status}")
            if exists:
                alive.append(app_id)
        # The pack, not the id, is what has to be reported: one dead candidate
        # out of two is a catalogue that still works and a fallback that has
        # been spent. Silence there is how a list quietly becomes a string
        # again, one disappearance at a time.
        results.append((f"{pack_id} (no surviving app id)", bool(alive), ""))
        if alive and alive[0] != app_ids[0]:
            degraded.append(f"{pack_id}: {app_ids[0]} is gone; "
                            f"falling back to {alive[0]}")
        elif len(app_ids) > 1 and len(alive) < len(app_ids):
            dead = [a for a in app_ids if a not in alive]
            degraded.append(f"{pack_id}: fallback(s) gone: {', '.join(dead)}")

    print("\nChecking GitHub Assets:")
    for label, repo, pattern in GITHUB_ASSETS:
        exists, status = check_github_release_asset(repo, pattern)
        results.append((label, exists, status))
        marker = "\u2713" if exists else "\u2717"
        print(f"[{marker}] {label:35} : {status}")

    print("\nChecking External Resources:")
    sdl2_url = "https://raw.githubusercontent.com/gabomdq/SDL_GameControllerDB/master/gamecontrollerdb.txt"
    exists, status = check_url(sdl2_url)
    results.append(("SDL2 GameControllerDB", exists, status))
    marker = "\u2713" if exists else "\u2717"
    print(f"[{marker}] {'SDL2 GameControllerDB':35} : {status}")

    print("\n" + "-" * 50)
    failed = [r[0] for r in results if not r[1]]
    for line in degraded:
        print(f"DEGRADED: {line}")
    if failed:
        print(f"WARNING: {len(failed)} items failed verification!")
        for f in failed:
            print(f" - {f}")
    if not failed and not degraded:
        print("All emulators and resources verified successfully.")
        return 0
    # Non-zero on a spent fallback too. A catalogue down to its last app id is
    # exactly the state this job is meant to give a week's warning about, and
    # a green tick would spend that week.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
