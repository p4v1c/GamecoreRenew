"""GE-Proton, fetched where the Flatpak Lutris lists it.

Lutris 0.5.22 and 0.5.23 find a Proton build in `<runners>/wine/<name>/` when the
directory holds a `proton` script (`lutris/util/wine/proton.py`), lists it
under that name and runs it through umu. `runners/proton/` is the old
location; a Lutris migration moves it into `runners/wine/`.

GE's release workflow (`Makefile.in`, `make redist`) publishes
`<tag>.tar.gz`, whose single top directory is `<tag>/`, and
`<tag>.sha512sum`. The tag of the latest release is read from the
`/releases/latest` redirect, the GitHub API only as a fallback: the API
allows 60 requests an hour per address.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

REPO = "GloriousEggroll/proton-ge-custom"
LATEST_URL = f"https://github.com/{REPO}/releases/latest"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_URL = "https://github.com/" + REPO + "/releases/download/{tag}/{tag}.{ext}"
TAG_RE = re.compile(r"GE-Proton\d+-\d+\Z")
HTTP_TIMEOUT_S = 30
CHUNK = 1 << 20
# The archive (~0.5 GB) and the unpacked build (~1.5 GB) exist side by side.
MIN_FREE_BYTES = 3 * 1024 ** 3
STAGING_PREFIX = ".gamecore-"

Log = Callable[[str], None]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def tag_from_location(location: str) -> str | None:
    tag = location.rstrip("/").rsplit("/", 1)[-1]
    return tag if TAG_RE.match(tag) else None


def latest_tag(log: Log) -> str | None:
    """The newest release's tag, or None when GitHub could not be asked."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(LATEST_URL, timeout=HTTP_TIMEOUT_S).close()
    except urllib.error.HTTPError as e:
        if tag := tag_from_location(e.headers.get("Location", "")):
            return tag
        log(f"releases/latest answered {e.code}, not a redirect")
    except (OSError, ValueError) as e:
        log(f"releases/latest did not answer: {e}")
    try:
        with urllib.request.urlopen(API_URL, timeout=HTTP_TIMEOUT_S) as r:
            tag = str(json.load(r).get("tag_name", ""))
    except (OSError, ValueError) as e:
        log(f"the GitHub API did not answer either: {e}")
        return None
    return tag if TAG_RE.match(tag) else None


def is_installed(wine_dir: Path, tag: str) -> bool:
    return (wine_dir / tag / "proton").is_file()


def parse_sha512(text: str, filename: str) -> str | None:
    """The digest `sha512sum` printed for `filename`."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename \
                and re.fullmatch(r"[0-9a-f]{128}", parts[0]):
            return parts[0]
    return None


def download(url: str, dest: Path) -> str:
    """Stream `url` into `dest`. Returns its sha512."""
    digest = hashlib.sha512()
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as r, dest.open("wb") as out:
        while chunk := r.read(CHUNK):
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def extract(archive: Path, wine_dir: Path, tag: str) -> None:
    """Unpack into a hidden staging folder, then move `<tag>/` into place.

    Raises ValueError for an archive that is not one GE-Proton build.
    """
    staging = wine_dir / f"{STAGING_PREFIX}{tag}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            if not names or any(n != tag and not n.startswith(f"{tag}/") for n in names):
                raise ValueError(f"{archive.name} does not hold a single {tag}/ folder")
            # "tar", not "data": Proton ships symlinks between its own folders.
            tar.extractall(staging, filter="tar")
        if not (staging / tag / "proton").is_file():
            raise ValueError(f"{tag} has no proton script")
        (staging / tag).rename(wine_dir / tag)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def fetch(wine_dir: Path, tag: str, log: Log) -> bool:
    """Download, verify and unpack one build. False on any failure."""
    wine_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(wine_dir).free
    if free < MIN_FREE_BYTES:
        log(f"{tag}: only {free // 1024 ** 2} MB free in {wine_dir}; not downloaded")
        return False
    archive = f"{tag}.tar.gz"
    part = wine_dir / f"{STAGING_PREFIX}{archive}.part"
    try:
        with urllib.request.urlopen(ASSET_URL.format(tag=tag, ext="sha512sum"),
                                    timeout=HTTP_TIMEOUT_S) as r:
            expected = parse_sha512(r.read(4096).decode("utf-8", "replace"), archive)
        if expected is None:
            log(f"{tag}: the release carries no usable sha512sum")
            return False
        log(f"{tag}: downloading")
        if download(ASSET_URL.format(tag=tag, ext="tar.gz"), part) != expected:
            log(f"{tag}: checksum mismatch, archive discarded")
            return False
        extract(part, wine_dir, tag)
    except (OSError, ValueError, tarfile.TarError) as e:
        log(f"{tag}: {e}")
        return False
    finally:
        part.unlink(missing_ok=True)
    log(f"{tag}: installed in {wine_dir}")
    return True


def referenced(config_dir: Path, tag: str) -> bool:
    """Whether any Lutris config names this build (a game pinned to it)."""
    for folder in (config_dir / "games", config_dir / "runners"):
        for path in folder.glob("*.yml"):
            try:
                if tag in path.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                return True             # unreadable: assume it is in use
    return False


def prune(wine_dir: Path, ours: list[str], keep: int, config_dir: Path) -> list[str]:
    """Remove our older builds beyond `keep`, never one a config still names."""
    removed = []
    for tag in sorted(ours, key=version_key)[:-keep] if keep else []:
        if referenced(config_dir, tag):
            continue
        shutil.rmtree(wine_dir / tag, ignore_errors=True)
        removed.append(tag)
    return removed


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", tag))
