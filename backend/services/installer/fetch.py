"""One download helper, factored out of `duck_fetch` and `xenia_fetch`.

Those two shell functions were already almost identical — same timeouts, same
`--speed-limit`, same magic-byte check, same fall back to the GitHub API — and
every one of those protections is there because of a real failure. They are
reproduced here exactly, with the reasoning that earned them.

**curl, not urllib.** The flags below encode behaviour that would have to be
re-implemented by hand otherwise: a transfer that stalls under 1 KB/s for 30 s
is aborted, connection refusals are retried, and an HTTP error body is never
written to disk. Re-writing that in Python is a way to lose one of them
quietly. curl is a hard dependency of the installer already.

What each protection is for:

  -f                  an HTTP error page is never saved and chmod +x'd.
  --speed-limit/-time a transfer that stalls forever does not hang the install.
  --retry-connrefused a box whose network comes up late still installs.
  a `.part` temp file  a transfer aborted by --speed-limit never lands at the
                      final name and gets mistaken for a good install next run.
  magic bytes         a 200 carrying the wrong body is still a failed
                      download; `curl -f` cannot catch a proxy or CDN that
                      answers 200 with something else entirely.
  fixed URL first     the GitHub API allows 60 requests per hour per IP
                      unauthenticated. Fresh installs kept ending up with no
                      PlayStation emulator at all: a second run — or anything
                      else behind the same NAT — exhausted the quota, the API
                      returned nothing, and the step gave up WITHOUT EVER
                      TRYING TO DOWNLOAD. `/releases/latest/download/<asset>`
                      is a plain 302 served outside that budget. The API keeps
                      its place for the day upstream renames the asset and the
                      fixed URL starts 404-ing.

New here, and the reason this file exists rather than a straight copy: an
optional `sha256`. There is no integrity check anywhere in install/ or update/
today — magic bytes catch an HTML error page or a truncated transfer, not a
tampered binary.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

# First bytes that say "this really is the kind of file we asked for".
MAGIC = {
    "ELF": b"\x7fELF",      # an AppImage is an ELF
    "PK": b"PK",            # zip
    "7z": b"7z",            # 7-zip
}

CURL_FLAGS = [
    "-fL",
    "--connect-timeout", "15",
    "--max-time", "900",
    "--speed-limit", "1024",
    "--speed-time", "30",
    "--retry", "3",
    "--retry-delay", "5",
    "--retry-connrefused",
]


class FetchError(Exception):
    """Nothing usable was downloaded. Never fatal to the caller by itself —
    a missing emulator costs a tile, not the install."""


def _magic_ok(path: Path, magic: str | None) -> bool:
    if not magic:
        return True
    want = MAGIC.get(magic)
    if want is None:
        raise ValueError(f"unknown magic {magic!r}")
    try:
        with path.open("rb") as f:
            head = f.read(max(len(m) for m in MAGIC.values()))
    except OSError:
        return False
    # `grep -qa -e PK -e 7z` matched either anywhere in the first two bytes;
    # anchoring at the start is what it meant and is stricter.
    return head.startswith(want)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, *, magic: str | None = None,
             sha256: str | None = None, timeout: int = 960) -> bool:
    """Fetch `url` to `dest`, atomically. True on success.

    Writes through `dest.part` and renames, so an aborted transfer never leaves
    something at the final name that the next run reads as "already installed".
    """
    part = dest.with_name(dest.name + ".part")
    part.unlink(missing_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(["curl", *CURL_FLAGS, "-o", str(part), url],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("fetch: curl failed for %s — %s", url, e)
        part.unlink(missing_ok=True)
        return False

    if r.returncode != 0 or not part.exists() or part.stat().st_size == 0:
        log.warning("fetch: %s — curl exit %s", url, r.returncode)
        part.unlink(missing_ok=True)
        return False

    if not _magic_ok(part, magic):
        log.warning("fetch: %s answered 200 but the body is not %s — "
                    "a proxy or an error page, not the asset", url, magic)
        part.unlink(missing_ok=True)
        return False

    if sha256:
        got = sha256_of(part)
        if got.lower() != sha256.lower():
            # Deliberately loud and deliberately fatal to THIS download: an
            # integrity mismatch is the one failure that must never be
            # retried against a different URL or silently accepted.
            log.error("fetch: %s has sha256 %s, expected %s — refusing it",
                      url, got, sha256)
            part.unlink(missing_ok=True)
            return False

    part.replace(dest)
    return True


def github_asset_url(repo: str, asset: str, version: str = "latest") -> str:
    """The fixed release URL — a 302, served outside the API quota."""
    if version and version != "latest":
        return f"https://github.com/{repo}/releases/download/{version}/{asset}"
    return f"https://github.com/{repo}/releases/latest/download/{asset}"


def github_api_asset(repo: str, pattern: str, version: str = "latest") -> str:
    """Ask the API which asset matches `pattern`. "" when it cannot be asked.

    The fallback, never the first attempt. Returns "" rather than raising: an
    unreachable API must leave the caller with an empty URL it already handles,
    not a traceback in the middle of an installer log.
    """
    url = (f"https://api.github.com/repos/{repo}/releases/latest"
           if not version or version == "latest"
           else f"https://api.github.com/repos/{repo}/releases/tags/{version}")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:      # noqa: S310
            data = json.load(r)
    except Exception:
        log.warning("fetch: GitHub API unreachable for %s", repo)
        return ""
    needle = pattern.lower()
    for a in data.get("assets", []):
        name = a.get("name", "")
        if name == pattern or needle in name.lower():
            return a.get("browser_download_url", "")
    return ""


def fetch_release_asset(repo: str, asset: str, dest: Path, *,
                        magic: str | None = None, pattern: str | None = None,
                        version: str = "latest",
                        sha256: str | None = None) -> bool:
    """Fixed URL first, GitHub API second. True when `dest` now holds the asset.

    The order is the whole point — see the module docstring on the 60/hour
    quota. A pinned `version` uses the tag URL, which is a 302 just the same.
    """
    if download(github_asset_url(repo, asset, version), dest,
                magic=magic, sha256=sha256):
        return True
    log.warning("fetch: fixed download URL failed for %s — asking the GitHub API",
                repo)
    url = github_api_asset(repo, pattern or asset, version)
    if not url:
        return False
    return download(url, dest, magic=magic, sha256=sha256)


def extract(archive: Path, into: Path) -> bool:
    """Unpack a zip or a 7z. False on failure, never an exception.

    The extraction used to run whatever the download had produced, and a
    GitHub hiccup left `unzip` exiting 9 on a missing file. Because the `case`
    around it was not part of an &&/|| list, `set -e` aborted the WHOLE install
    at 52 % — before a single systemd unit, sudoers rule or autologin config
    existed. A failed extraction costs one tile; it must never cost the box.
    """
    into.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".7z"):
        cmd = ["7z", "x", "-y", f"-o{into}", str(archive)]
    else:
        cmd = ["unzip", "-o", "-q", str(archive), "-d", str(into)]
    if shutil.which(cmd[0]) is None:
        log.warning("extract: %s is not installed", cmd[0])
        return False
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("extract: %s failed — %s", cmd[0], e)
        return False
    if r.returncode != 0:
        log.warning("extract: %s exited %s — %s", cmd[0], r.returncode,
                    (r.stderr or "").strip()[:200])
        return False
    return True
