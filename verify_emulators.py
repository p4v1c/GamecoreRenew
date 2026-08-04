"""Check that everything the catalogue says to install still exists upstream.

Driven by catalog/<id>/pack.json, and that matters: this list used to be
hand-written and still carried io.github.gopher64.gopher64 long after the N64
slot moved to Rosalie's Mupen GUI. It reported a healthy Flathub entry for an
application nobody installs — green on the wrong target, which is worse than
red. Reading the catalogue is what turns this into the job that would have
caught the whole thing.

Needs the network. Run it on a schedule, not on every push: CI must not go red
because Flathub is slow.
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.services.catalog import load_catalog  # noqa: E402

_PACKS = load_catalog()

FLATPAK_IDS = sorted({p.app_id for p in _PACKS.values() if p.app_id})

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
    
    print("\nChecking Flatpaks on Flathub:")
    for app_id in FLATPAK_IDS:
        exists, status = check_flatpak(app_id)
        results.append((app_id, exists, status))
        marker = "✓" if exists else "✗"
        print(f"[{marker}] {app_id:35} : {status}")

    print("\nChecking GitHub Assets:")
    for label, repo, pattern in GITHUB_ASSETS:
        exists, status = check_github_release_asset(repo, pattern)
        results.append((label, exists, status))
        marker = "✓" if exists else "✗"
        print(f"[{marker}] {label:35} : {status}")

    print("\nChecking External Resources:")
    sdl2_url = "https://raw.githubusercontent.com/gabomdq/SDL_GameControllerDB/master/gamecontrollerdb.txt"
    exists, status = check_url(sdl2_url)
    results.append(("SDL2 GameControllerDB", exists, status))
    marker = "✓" if exists else "✗"
    print(f"[{marker}] {'SDL2 GameControllerDB':35} : {status}")

    print("\n" + "-" * 50)
    failed = [r[0] for r in results if not r[1]]
    if failed:
        print(f"WARNING: {len(failed)} items failed verification!")
        for f in failed:
            print(f" - {f}")
    else:
        print("All emulators and resources verified successfully.")

if __name__ == "__main__":
    main()
