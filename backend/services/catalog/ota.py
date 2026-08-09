"""The catalogue's own update channel, versioned apart from the release.

The concrete objective: an app id dies on Flathub, and every box in the fleet
is corrected inside 24 hours — without cutting a release, without a frontend
build, without anyone rebooting anything.

Today that correction is a release. `release.yml` fires on every push to main,
so fixing one string in one `pack.json` rebuilds the frontend, rebuilds the
PyInstaller wizard, publishes three assets and ships the whole application to
every box. That is a lot of moving parts to change one string, and each of them
is a way for the fix to be delayed or to break something unrelated.

So the catalogue gets a version of its own (`catalog/CATALOG_VERSION`) and an
endpoint of its own.

What a remote catalogue may change, and what it may not
-------------------------------------------------------
It is DATA ONLY, and more strictly so than `config/catalog.d/`.

A local pack is a directory the operator put on their own machine; it is
stripped of the code-executing blocks unless they opt in. A remote pack arrives
over the network from a machine nobody in the room controls, so there is no
opt-in and there is no `generator.py`: the bundle is a single JSON document,
which has no way to express a file, a symlink, a path or a mode. The blocks
that run code or change the system are dropped with a warning.

That is enough for the objective. Correcting `install.appIds`, `launch.args`
or an extension list is exactly what the channel exists for. Shipping new
generator code stays a release, where it goes through review and CI — and
"remote catalogue can ship code" is the sentence this design exists to avoid
having to write.

Three tiers, and why the order is this one::

    catalog/                 shipped   the release. Reviewed, tested, signed by
                                       virtue of being in the release.
    <data>/catalog-ota/      remote    signed corrections. Overrides shipped.
    config/catalog.d/        local     the operator. Overrides everything.

The operator wins, always. A box whose owner has pinned a pack by hand must not
have that undone by an endpoint — otherwise the channel is also a way to
override the person holding the machine.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import paths
from ..paths import catalog_dir
from . import signing

log = logging.getLogger(__name__)

# The version of the catalogue currently baked into this release.
VERSION_FILE = "CATALOG_VERSION"
# Where a verified remote catalogue is cached. Under the DATA root: the code
# root is read-only on a box, and this is state the box owns.
STATE_DIR_NAME = "catalog-ota"
APPLIED_FILE = "applied.json"

# Blocks a remote pack may never carry, whatever it says. Supersets
# `loader.PRIVILEGED_BLOCKS` — `files` and `secrets` are added because a remote
# document that can name a destination path is a remote document that can write
# one, and `sources` is a git clone from a URL of the sender's choosing.
FORBIDDEN_BLOCKS = ("postInstall", "services", "sources", "packages",
                    "files", "secrets")


def shipped_version(root: Path | None = None) -> int:
    """The catalogue version this release ships. 0 when the file is absent —
    an unversioned catalogue accepts any signed correction, which is what an
    older box needs."""
    path = (root or catalog_dir()) / VERSION_FILE
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def state_dir() -> Path:
    # Through the module, not a name bound at import: `paths.use_roots()`
    # re-points the roots at runtime, and the test suite aims them at a
    # throwaway directory. A copy taken at import time would keep answering
    # with the real box's path.
    return paths.GAMECORE_DATA / STATE_DIR_NAME


def applied_version(state: Path | None = None) -> int:
    """The version this box has already accepted. 0 = none."""
    try:
        data = json.loads(((state or state_dir()) / APPLIED_FILE)
                          .read_text(encoding="utf-8"))
        return int(data.get("version", 0))
    except (OSError, ValueError, TypeError):
        return 0


def _sanitise(pack_id: str, data: dict) -> tuple[dict, list[str]]:
    """A remote pack, reduced to what it is allowed to say."""
    clean = {k: v for k, v in data.items() if k not in FORBIDDEN_BLOCKS}
    dropped = sorted(set(data) & set(FORBIDDEN_BLOCKS))
    # The id is what decides which directory this lands in. A pack whose id
    # disagrees with its key would write over a neighbour's; `..` or a slash
    # would write outside the tree entirely.
    clean["id"] = pack_id
    return clean, dropped


_ID_OK = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


def _id_is_safe(pack_id: str) -> bool:
    return (bool(pack_id) and pack_id[0].isalnum()
            and set(pack_id) <= _ID_OK and ".." not in pack_id)


def apply_bundle(envelope_bytes: bytes, *, public_key: Path,
                 state: Path | None = None, current: int | None = None) -> dict:
    """Verify a bundle and write it to the OTA tier. Returns a summary.

    Raises `signing.SignatureError` for anything that fails to authenticate,
    and `ValueError` for a bundle that authenticates but says something this
    box will not act on. The distinction matters to the caller: the first is
    hostile or misconfigured, the second is a catalogue that needs fixing.
    """
    catalogue = signing.verify(envelope_bytes, public_key)

    try:
        version = int(catalogue.get("version", 0))
    except (TypeError, ValueError):
        raise ValueError("the catalogue declares no usable integer version")
    if version <= 0:
        raise ValueError("the catalogue declares no version — refusing, since "
                         "an unversioned bundle can never be rolled forward")

    state = state or state_dir()
    have = applied_version(state) if current is None else current
    if version <= have:
        # A validly signed OLD catalogue is exactly what an adversary who can
        # serve bytes would replay, to put back the app id today's bundle
        # fixes. The signature cannot express freshness; only this can.
        raise ValueError(
            f"catalogue version {version} is not newer than the {have} this box "
            f"already applied — refusing (a replayed bundle is signed too)")

    packs = catalogue.get("packs")
    if not isinstance(packs, dict) or not packs:
        raise ValueError("the catalogue carries no packs")

    written, dropped_blocks, rejected = [], {}, []
    state.mkdir(parents=True, exist_ok=True)

    for pack_id, data in sorted(packs.items()):
        if not _id_is_safe(pack_id) or not isinstance(data, dict):
            rejected.append(pack_id)
            continue
        clean, dropped = _sanitise(pack_id, data)
        if dropped:
            dropped_blocks[pack_id] = dropped
            log.warning("catalog-ota: %r tried to carry %s — a remote pack is "
                        "data only, those were dropped",
                        pack_id, ", ".join(dropped))
        target = state / pack_id
        target.mkdir(parents=True, exist_ok=True)
        # Atomic, like every other writer here: a pack.json caught half-written
        # is a pack the loader refuses at the next boot.
        tmp = target / "pack.json.gamecore-tmp"
        tmp.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(target / "pack.json")
        written.append(pack_id)

    if rejected:
        log.warning("catalog-ota: refused pack id(s) %s — an id decides a "
                    "directory name", ", ".join(map(repr, rejected)))
    if not written:
        raise ValueError("the catalogue carried no pack this box would accept")

    # Last, so a crash mid-write leaves the version behind rather than ahead:
    # re-applying is harmless, believing a half-written catalogue is not.
    tmp = state / (APPLIED_FILE + ".gamecore-tmp")
    tmp.write_text(json.dumps({"version": version, "packs": written},
                              indent=2) + "\n", encoding="utf-8")
    tmp.replace(state / APPLIED_FILE)

    log.info("catalog-ota: applied version %d — %d pack(s): %s",
             version, len(written), ", ".join(written))
    return {"version": version, "packs": written,
            "droppedBlocks": dropped_blocks, "rejected": rejected}
