"""OTA update via GitHub Releases."""
import asyncio
import sys
from fastapi import APIRouter, HTTPException
import httpx

from ..config import APP_VERSION, GITHUB_REPO, UPDATE_ASSET, GAMECORE_ROOT
from .. import ws

router = APIRouter(prefix="/update", tags=["update"])

_GH_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _version_int(tag: str) -> int:
    s = tag.lstrip("vV")
    parts = s.split(".")
    return sum(int(parts[i]) * (10000 ** (2 - i)) for i in range(min(3, len(parts))))


@router.get("/check")
async def check_update():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(_GH_API, headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(503, f"GitHub unreachable: {e}")

    remote_tag = data.get("tag_name", "")
    download_url = ""
    for asset in data.get("assets", []):
        if asset["name"] == UPDATE_ASSET:
            download_url = asset["browser_download_url"]
            break

    if _version_int(remote_tag) > _version_int(APP_VERSION):
        return {
            "update_available": True,
            "current": APP_VERSION,
            "latest": remote_tag,
            "download_url": download_url,
        }
    return {"update_available": False, "current": APP_VERSION, "latest": remote_tag}


@router.post("/apply")
async def apply_update():
    """Run the platform update script in background, stream progress via WebSocket."""
    if sys.platform == "win32":
        script = GAMECORE_ROOT / "update" / "windows.bat"
        cmd = [str(script)]
    else:
        script = GAMECORE_ROOT / "update" / "linux.sh"
        cmd = ["bash", str(script)]

    if not script.exists():
        raise HTTPException(404, f"Update script not found: {script}")

    async def _run_update():
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if proc.stdout:
            async for line in proc.stdout:
                await ws.broadcast("update:log", {"line": line.decode().rstrip()})
        await proc.wait()
        code = proc.returncode or 0
        await ws.broadcast("update:done", {"success": code == 0, "code": code})

    asyncio.create_task(_run_update())
    return {"ok": True, "message": "Update started"}
