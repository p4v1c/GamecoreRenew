import requests

FLATPAK_IDS = [
    "org.azahar_emu.Azahar",
    "net.rpcs3.RPCS3",
    "net.pcsx2.PCSX2",
    "org.DolphinEmu.dolphin-emu",
    "net.kuribo64.melonDS",
    "io.github.gopher64.gopher64",
    "io.mgba.mGBA",
    "org.ppsspp.PPSSPP",
    "info.cemu.Cemu",
    "net.shadps4.shadPS4",
    "com.valvesoftware.Steam",
    "com.stremio.Stremio",
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
    for label, repo, pattern in (
        ("DuckStation AppImage", "stenzek/duckstation", "x64.AppImage"),
        ("citron-neo AppImage", "citron-neo/emulator", "linux-x86_64.AppImage"),
        ("Xenia Canary (Windows)", "xenia-canary/xenia-canary-releases", "windows"),
    ):
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
