"""The Real-Debrid acquisition provider — one account, owned by somebody else.

**Real-Debrid is external, always**, and for the same reasons Prowlarr is.
GameCore does not install it, does not manage it, does not update it and does
not remove it. The box owner has their own account, pays for it themselves, and
this file knows one thing about it: an API token.

── Why a debrid service at all, and what it buys ──────────────────────────
Because it is what lets this box download a torrent **without being a torrent
client**. Real-Debrid takes a magnet — or a `.torrent` file — fetches the
content on its own machines, and answers with a plain HTTPS URL. What arrives
on the box is therefore an ordinary `GET` over the connection it already has.

The alternative is the one this avoids, and it is worth naming because it is
the obvious design and it is much worse. A torrent client on the box means a
daemon with its own service unit, a listening port on the LAN — the thing
[`docs/SECURITY.md`](../../../docs/SECURITY.md) spent the whole hardening pass
reducing to Caddy on `:8443` — a second piece of software GameCore owns the
uptime of, connections to strangers from a machine in somebody's living room,
and an uninstaller that has to know how to take all of it away again. One token
in one file buys all of that back, and the day the owner stops paying, the file
goes and the box is exactly what it was.

── Two ways in, one way on ────────────────────────────────────────────────
An indexer row names its payload one of two ways, and both end at the same
torrent id:

  · a **magnet**, when the row published an info hash — `POST
    /torrents/addMagnet`, the original path, unchanged;
  · a **`.torrent` file**, when it did not — `PUT /torrents/addTorrent`, whose
    body is the file itself. On the box this was written for that is *every*
    row: 0 of 8 for `mario kart`, one indexer, all `protocol=torrent`. The file
    is fetched by [`prowlarr.fetch_torrent`](prowlarr.py), because that is
    where the Prowlarr key lives, and it is never written to a disk.

Which one is decided by `ResolvedSource.by_hash` and nowhere else. After it,
steps 3 to 5 are identical and do not know which happened.

── Acquiring is resolving. It downloads nothing ───────────────────────────
`acquire()` answers an `AcquiredTarget` and moves no bytes. See that class in
[`jobs.py`](jobs.py) for why the split is where it is; the consequence here is
that this whole file can be read as "what does this release become", and a
reader looking for the code that writes a file will correctly find none — the
`.torrent`, when there is one, is `bytes` that are hashed and dropped.

── The credential, and where it is not ────────────────────────────────────
`config/store-realdebrid.json`, mode 0600, written the way
[`services/auth.py`](../auth.py) writes `auth.json` — atomically, private from
the first byte, through `save_config()` and never a `write_text()`. `config/`
is excluded from the OTA rsync, so it survives an update;
`install/uninstall.sh` names it, so it does not survive a removal, and
`backend/tests/test_store_secret_removal.py` pins that.

The token travels as an `Authorization: Bearer` **header** and never in a URL,
because a URL is what ends up in a proxy log and in an exception message.
Redirects are not followed, because following one would hand the header to
whatever host the redirect named. And nothing lifted out of a response is ever
logged or put on a job's `reason`: Real-Debrid answers **unrestricted download
URLs**, which are credentials in their own right — anyone holding one spends
the owner's bandwidth — so `AcquiredTarget.redacted()` is the only spelling of
one that reaches a journal.

── Absent or incomplete is not an error ───────────────────────────────────
No file, no token, unreadable, malformed: all one answer, `None`, and the box
carries on with no acquisition provider — which is the state every box is in
until its owner configures one. Jobs keep failing honestly with
`jobs.NO_PROVIDER`. A Store that threw a red screen because a file nobody has
ever created is missing would be a broken-looking box with nothing wrong with
it.

── What it does not do ────────────────────────────────────────────────────
It does not add a torrent to the owner's account and walk away, it does not
delete one, and it does not manage their torrent list. It adds the release,
selects the one file this job is about, waits a bounded time for Real-Debrid to
have it, and asks for a link. A torrent that is still caching when the wait runs
out is left alone on purpose: Real-Debrid keeps fetching it, so queueing the
same game again in a few minutes finds it ready. Tearing it down would throw
away work the owner has already paid for.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..paths import config_dir
from . import prowlarr, resolve, torrentfile
from .jobs import AcquiredTarget, Job

log = logging.getLogger(__name__)

#: Beside `auth.json` and `store-prowlarr.json`, and namespaced the same way:
#: `config/` is a directory the whole box shares, and "which part of GameCore
#: owns this file" is otherwise a guess.
CONFIG_FILENAME = "store-realdebrid.json"

#: Real-Debrid's public REST root. A default and not a constant: every test in
#: this repository overrides it with a `.invalid` host, so a regression that
#: dropped the mock transport fails instead of reaching a real service with a
#: real token.
DEFAULT_API_URL = "https://api.real-debrid.com/rest/1.0"

#: Seconds, per request. Same shape and same clamp as the Prowlarr client's.
DEFAULT_TIMEOUT = 20.0
_MIN_TIMEOUT, _MAX_TIMEOUT = 1.0, 120.0

#: Seconds to wait, in total, for Real-Debrid to actually have the content.
#: A torrent the service has cached is ready in one round trip; one it has
#: never seen has to be fetched from the swarm, which takes as long as it
#: takes. This is not a download timeout — nothing is downloading here — it is
#: how long a job may sit `running` before the box says so rather than holding
#: the queue behind it for ever.
DEFAULT_WAIT = 120.0
_MIN_WAIT, _MAX_WAIT = 0.0, 900.0

#: How often to ask again while waiting. Not configurable: it is a poll against
#: somebody else's service and a knob whose only possible use is to hammer it.
_POLL_EVERY = 3.0

#: Real-Debrid's torrent states, split by what they mean for one job.
#: `downloaded` is the only one that produces links. The rest are either a
#: reason to keep waiting or a reason to stop, and naming them here is what
#: lets a failure say which happened instead of "it did not work".
_READY = "downloaded"
_WORKING = ("magnet_conversion", "queued", "downloading", "compressing",
            "uploading", "waiting_files_selection")
#: Terminal failures, mapped to the sentence the player reads. Each is true and
#: each is different: a dead torrent is not a rejected file and neither is an
#: account that ran out of traffic.
#: `magnet_error` is Real-Debrid's own name for the state, and it is reached
#: from `addTorrent` as well as from `addMagnet` — so the sentence says what
#: happened rather than naming the way in, which the player did not choose.
_DEAD = {
    "magnet_error": "Real-Debrid could not make sense of this release",
    "error": "Real-Debrid could not fetch this release",
    "virus": "Real-Debrid refused this release as unsafe",
    "dead": "nobody is sharing this release any more",
}


class RealDebridError(RuntimeError):
    """Real-Debrid did not answer usefully.

    Raised with a message that is safe to put on a job row and in front of a
    player: no token, no unrestricted URL, no query string. `jobs._settle()`
    copies the text onto the row verbatim, so that is a contract and not a
    style preference.
    """


# ── configuration ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RealDebridConfig:
    """`config/store-realdebrid.json`, validated.

    ``api_key``   My Account → API token, in the owner's own Real-Debrid
                  account. The only required field: unlike Prowlarr there is no
                  URL to configure, because there is one Real-Debrid and it is
                  not the owner's to move.
    ``api_url``   overridable anyway, so that the tests can point at a host
                  that cannot resolve and so that a box behind a proxy is not
                  stuck. Path, query and fragment of whatever is written are
                  kept for the path and dropped for the rest.
    ``timeout``   seconds per request, clamped to [1, 120].
    ``wait``      seconds to wait in total for the content, clamped to
                  [0, 900]. `0` means "only if it is already cached", which is
                  a reasonable thing for an owner to want.
    """

    api_key: str
    api_url: str = DEFAULT_API_URL
    timeout: float = DEFAULT_TIMEOUT
    wait: float = DEFAULT_WAIT


def config_file() -> Path:
    """Resolved on every call, never at import — as `prowlarr.config_file()`
    is, and for the same reason: a test that moves the data root moves this
    with it, and so does a box whose `GAMECORE_DATA` is set after the unit is
    written."""
    return config_dir() / CONFIG_FILENAME


#: Paths already complained about, so the warning below is one line in the
#: journal rather than one per job.
_warned: set[str] = set()


def _warn_if_world_readable(path: Path) -> None:
    """Say so, and read it anyway — `prowlarr._warn_if_world_readable`'s twin.

    Not a refusal. This file is written by hand and a default umask makes it
    0644 without the owner doing anything wrong. A Store that silently had no
    acquisition provider because of a permission bit is a box that looks broken
    with no way to tell why.
    """
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if not mode & (stat.S_IRGRP | stat.S_IROTH):
        return
    key = f"{path}:{stat.S_IMODE(mode):o}"
    if key in _warned:
        return
    _warned.add(key)
    log.warning("store: %s is readable by other accounts (mode %o) — it holds "
                "an API token; chmod 600 it", path, stat.S_IMODE(mode))


def _clean_url(raw: object) -> str:
    """`https://host/rest/1.0`, or `""` when that is not what was written.

    Keeps the path — unlike the Prowlarr loader, because a REST root *is* a
    path here — and drops query and fragment, which is where a token pasted
    into the URL would sit.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return urlunsplit((parts.scheme, parts.netloc,
                       parts.path.rstrip("/"), "", ""))


def _pick(data: dict, *names: str) -> object:
    """The first spelling that is present — `apiKey` and `api_key` both work.

    The file has no editor behind it; somebody types it at midnight over SSH,
    and refusing it over a capital letter is a support question this repository
    would then have to answer.
    """
    for name in names:
        if name in data:
            return data[name]
    return None


def _number(raw: object, fallback: float, low: float, high: float) -> float:
    try:
        return min(max(float(raw), low), high)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def load_config() -> RealDebridConfig | None:
    """The configuration, or `None` when there is not a usable one.

    `None` covers absent, unreadable, malformed and present-but-incomplete, and
    they are one answer on purpose: the caller's behaviour is the same for all
    four — no acquisition provider, and jobs that fail saying exactly that. A
    missing file is the *normal* state of a box and is not logged above debug;
    a file that exists and cannot be used is a warning, because somebody meant
    it to work.
    """
    path = config_file()
    try:
        raw = path.read_text()
    except FileNotFoundError:
        log.debug("store: no %s — this box acquires nothing", CONFIG_FILENAME)
        return None
    except (OSError, UnicodeDecodeError) as e:
        # UnicodeDecodeError for the reason `auth._auth()` lists it:
        # `read_text()` raises that, not a JSON error, on a half-written file.
        log.warning("store: %s cannot be read — %s", CONFIG_FILENAME, e)
        return None
    _warn_if_world_readable(path)

    try:
        data = json.loads(raw)
    except ValueError as e:
        log.warning("store: %s is not valid JSON — %s", CONFIG_FILENAME, e)
        return None
    if not isinstance(data, dict):
        log.warning("store: %s is not a JSON object", CONFIG_FILENAME)
        return None

    api_key = _pick(data, "apiKey", "api_key", "token")
    api_key = api_key.strip() if isinstance(api_key, str) else ""
    if not api_key:
        # Named without its value. "apiKey" is safe to print; the token is not.
        log.warning("store: %s is incomplete (apiKey) — this box acquires "
                    "nothing", CONFIG_FILENAME)
        return None

    api_url = _clean_url(_pick(data, "apiUrl", "api_url", "url")) or DEFAULT_API_URL
    return RealDebridConfig(
        api_key=api_key,
        api_url=api_url,
        timeout=_number(_pick(data, "timeout", "timeoutSeconds",
                              "timeout_seconds"),
                        DEFAULT_TIMEOUT, _MIN_TIMEOUT, _MAX_TIMEOUT),
        wait=_number(_pick(data, "wait", "waitSeconds", "wait_seconds"),
                     DEFAULT_WAIT, _MIN_WAIT, _MAX_WAIT),
    )


def save_config(cfg: RealDebridConfig) -> Path:
    """Write it the way `auth.py` writes a credential: atomically, 0600.

    There is no settings screen behind this yet — the file is created by hand
    today. It exists so that when one arrives it does not invent a second way
    to write a secret, and so that the tests build their fixtures through the
    same code a box would use rather than through a `write_text()` that leaves
    a world-readable token behind.
    """
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "apiKey": cfg.api_key,
        "apiUrl": cfg.api_url,
        "timeout": cfg.timeout,
        "wait": cfg.wait,
    }, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(payload)
    os.replace(tmp, path)
    return path


def _where(cfg: RealDebridConfig) -> str:
    """The address, for a message — scheme, host and path, never a token.

    `_clean_url` has already dropped any query string, so this is belt and
    braces. It is here because every sentence this module raises can end up on
    a job row that a player reads, and a module that formats its own addresses
    in one place cannot grow a second one that formats them wrong.
    """
    parts = urlsplit(cfg.api_url)
    return f"{parts.scheme}://{parts.netloc}"


# ── the provider ───────────────────────────────────────────────────────────


class RealDebridAcquisition:
    """A magnet in, a direct HTTPS URL out. Nothing in between touches a disk."""

    name = "realdebrid"
    label = "Real-Debrid"

    def __init__(self, transport: httpx.BaseTransport | None = None,
                 prowlarr_transport: httpx.BaseTransport | None = None) -> None:
        # Tests only, and the only seams this class has — `ProwlarrSearchProvider`
        # has the same one for the same reason: the alternative is a test that
        # either reaches a real service with a real token or patches httpx
        # globally. `jobs.acquisition_provider()` never passes either.
        #
        # Two of them rather than one, because the `.torrent` path talks to two
        # different services with two different keys, and a single transport
        # would let a test that meant to stub Prowlarr silently answer for
        # Real-Debrid as well.
        self._transport = transport
        self._prowlarr_transport = prowlarr_transport

    @classmethod
    def configured(cls) -> bool:
        """Whether this box has a token. `jobs.acquisition_provider()` asks
        before constructing one, so an unconfigured box has no acquisition
        provider at all rather than one that can only fail."""
        return load_config() is not None

    async def acquire(self, job: Job) -> AcquiredTarget:
        """The job's source, resolved into something fetchable.

        Five steps, each of which can fail with its own sentence:

          1. read the source — `resolve.py`, and the only step that touches no
             network. A row the indexer published with neither an info hash nor
             a torrent file stops here, which is what "unsupported link" means
             in practice;
          2. hand Real-Debrid the release. **Two ways in, one way on**, chosen
             by `ResolvedSource.by_hash` — a magnet when the indexer published
             a hash, the `.torrent` itself when it published a file. Both
             answer the same torrent id, so steps 3 to 5 do not know which
             happened;
          3. ask what is in it, and pick the one file this job is about;
          4. select that file, and wait — bounded — for the service to have it;
          5. unrestrict the link into a direct URL.

        Returns an `AcquiredTarget` and writes nothing anywhere — the
        `.torrent`, when there is one, is bytes in memory and never a file.
        """
        cfg = load_config()
        if cfg is None:
            # Only reachable if the file went away between `configured()` and
            # here, or if something constructed this provider directly.
            raise RealDebridError(f"no usable {CONFIG_FILENAME}")

        # Raises `UnresolvableSource`, which is a `ValueError` carrying a
        # sentence written for a player. Let it through as it is rather than
        # wrapping it in a Real-Debrid message: the fault is the indexer's row,
        # not the service, and saying "Real-Debrid" here would send somebody to
        # check an account that is working.
        found = resolve.resolve(job.source)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(cfg.timeout),
            # Never followed. A redirect would carry the `Authorization`
            # header to whatever host it named — a token handed to a third
            # party by somebody else's misconfiguration.
            follow_redirects=False,
            transport=self._transport,
            headers={"Authorization": f"Bearer {cfg.api_key}",
                     "Accept": "application/json"},
        ) as client:
            if found.by_hash:
                info_hash = found.info_hash
                torrent_id = await self._add_magnet(client, cfg, found)
            else:
                torrent_id, info_hash = await self._add_torrent(
                    client, cfg, found)
            file_id, filename, size = await self._choose_file(
                client, cfg, torrent_id, job)
            await self._select(client, cfg, torrent_id, file_id)
            link = await self._wait_for_link(client, cfg, torrent_id)
            return await self._unrestrict(client, cfg, link, info_hash,
                                          filename, size)

    # ── the five steps ─────────────────────────────────────────────────────

    async def _add_magnet(self, client: httpx.AsyncClient,
                          cfg: RealDebridConfig,
                          found: resolve.ResolvedSource) -> str:
        """Step 2 — the magnet goes in, an id comes back."""
        body = await self._call(client, cfg, "POST", "/torrents/addMagnet",
                                data={"magnet": found.magnet})
        if not isinstance(body, dict) or not isinstance(body.get("id"), str):
            raise RealDebridError(
                f"{_where(cfg)} accepted the release but named no torrent")
        return body["id"]

    async def _add_torrent(self, client: httpx.AsyncClient,
                           cfg: RealDebridConfig,
                           found: resolve.ResolvedSource) -> tuple[str, str]:
        """Step 2, the other way — the file goes in, an id and a hash come out.

        **Why a file at all, and why this endpoint.** Real-Debrid publishes
        `PUT /torrents/addTorrent` beside `POST /torrents/addMagnet`, and its
        reference declares *no body parameter for it* — only an optional `host`
        in the query string — where `addMagnet` declares `POST magnet *`. That
        is the documentation saying the torrent **is** the request body, and it
        answers the same `201` with the same `{id, uri}` that `addMagnet`
        answers. So the four steps after this one do not change, which is the
        whole reason this path is worth having rather than a second pipeline.

        **Why not compute the hash and reuse `addMagnet`.** It was the stated
        fallback and it is genuinely worse here, for a reason specific to what
        this box downloads. `ResolvedSource.magnet` is trackerless on purpose,
        so a magnet made from a hash alone gives Real-Debrid nothing but 20
        bytes: it has to find the metadata itself, which is the
        `magnet_conversion` state, and for a release that lives on a **private**
        tracker there is no public swarm to find it in. The `.torrent` carries
        the piece hashes and the file list, so that step is simply not needed.
        The file is the better input wherever there is one.

        The hash is computed anyway to identify the torrent and check
        Real-Debrid's torrent answer. It is not a checksum of the unrestricted
        file — BitTorrent hashes metadata and pieces — so the materializer uses
        the resolved byte length for transfer completeness. Computing it also
        establishes that these bytes are a torrent at all, before the owner's
        account is asked anything and before a login page can be mistaken for
        a release.
        """
        try:
            blob = await prowlarr.fetch_torrent(
                found.indexer_id, found.torrent_token,
                transport=self._prowlarr_transport)
        except prowlarr.ProwlarrError as e:
            # Passed through as it is. The fault is this box's Prowlarr or the
            # indexer behind it, and saying "Real-Debrid" here would send
            # somebody to check an account that is working.
            raise RealDebridError(str(e)) from None

        # Before the account is touched: a login page that came back with a
        # 200 is not a release, and finding that out here costs nothing and
        # tells the truth. `NotATorrent` is a `ValueError` with a sentence
        # written for a player, so it is re-raised as one.
        try:
            info_hash = torrentfile.info_hash_of(blob)
        except torrentfile.NotATorrent as e:
            raise RealDebridError(str(e)) from None

        body = await self._call(client, cfg, "PUT", "/torrents/addTorrent",
                                content=blob)
        if not isinstance(body, dict) or not isinstance(body.get("id"), str):
            raise RealDebridError(
                f"{_where(cfg)} accepted the release but named no torrent")
        return body["id"], info_hash

    async def _choose_file(self, client: httpx.AsyncClient,
                           cfg: RealDebridConfig, torrent_id: str,
                           job: Job) -> tuple[int, str, int]:
        """Step 3 — which of the files in this release is the game.

        A release is often one ROM and sometimes a folder of them plus a NFO, a
        cover and a readme. Two rules, in order:

          · the file whose name is exactly the one the search result named.
            That is the row the player looked at and chose;
          · failing that, the largest. It is not a guess about *what* the file
            is — that is matrix §5.1's, from the bytes — only about which of
            several is the payload, and the biggest file in a ROM release is
            not the readme.

        Selecting all of them instead would answer several links and leave the
        same choice to be made one step later with less to make it on.
        """
        body = await self._call(client, cfg, "GET",
                                f"/torrents/info/{torrent_id}")
        if not isinstance(body, dict):
            raise RealDebridError(
                f"{_where(cfg)} answered something unexpected about this "
                "release")
        state = str(body.get("status") or "")
        if state in _DEAD:
            raise RealDebridError(_DEAD[state])

        files = body.get("files")
        usable: list[tuple[int, str, int]] = []
        for entry in files if isinstance(files, list) else []:
            if not isinstance(entry, dict):
                continue
            try:
                fid = int(entry["id"])
            except (KeyError, TypeError, ValueError):
                continue
            path = entry.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            try:
                nbytes = max(0, int(entry.get("bytes") or 0))
            except (TypeError, ValueError):
                nbytes = 0
            # Real-Debrid answers a path inside the torrent (`/Folder/rom.z64`).
            # Only the last segment is a name, and it is compared, never joined
            # onto anything — nothing here builds a path.
            usable.append((fid, path.rsplit("/", 1)[-1], nbytes))

        if not usable:
            raise RealDebridError(
                "Real-Debrid found no files in this release")
        wanted = job.filename.strip().lower()
        for fid, name, nbytes in usable:
            if name.lower() == wanted:
                return fid, name, nbytes
        return max(usable, key=lambda f: f[2])

    async def _select(self, client: httpx.AsyncClient, cfg: RealDebridConfig,
                      torrent_id: str, file_id: int) -> None:
        """Step 4a — tell the service which file, which is what starts it."""
        await self._call(client, cfg, "POST",
                         f"/torrents/selectFiles/{torrent_id}",
                         data={"files": str(file_id)})

    async def _wait_for_link(self, client: httpx.AsyncClient,
                             cfg: RealDebridConfig, torrent_id: str) -> str:
        """Step 4b — wait, bounded, for the service to actually have it.

        A torrent Real-Debrid has cached is `downloaded` on the first ask. One
        it has never seen is fetched from the swarm while this polls, and if
        that outlasts `cfg.wait` the job fails saying what it was doing —
        **and the torrent is left alone**, still fetching, so asking again in a
        few minutes finds it ready. `asyncio.sleep` is what makes a cancel
        arrive promptly: `jobs._interrupt` cancels the task and the sleep is
        where it lands.
        """
        deadline = asyncio.get_running_loop().time() + cfg.wait
        state = "unknown"
        while True:
            body = await self._call(client, cfg, "GET",
                                    f"/torrents/info/{torrent_id}")
            if not isinstance(body, dict):
                raise RealDebridError(
                    f"{_where(cfg)} answered something unexpected about this "
                    "release")
            state = str(body.get("status") or "unknown")
            if state in _DEAD:
                raise RealDebridError(_DEAD[state])
            if state == _READY:
                links = body.get("links")
                first = links[0] if isinstance(links, list) and links else None
                if not isinstance(first, str) or not first.strip():
                    raise RealDebridError(
                        "Real-Debrid has this release but offered no link "
                        "for it")
                return first.strip()
            if state not in _WORKING:
                # An unknown status is not assumed to be fatal and not assumed
                # to be progress: it is reported as itself. The name is
                # Real-Debrid's own vocabulary and carries nothing private.
                raise RealDebridError(
                    f"Real-Debrid says this release is {state!r}, which this "
                    "box does not know how to wait for")
            if asyncio.get_running_loop().time() >= deadline:
                raise RealDebridError(
                    f"Real-Debrid is still fetching this release "
                    f"({state}) — queue it again in a few minutes")
            await asyncio.sleep(_POLL_EVERY)

    async def _unrestrict(self, client: httpx.AsyncClient,
                          cfg: RealDebridConfig, link: str, info_hash: str,
                          filename: str, size: int) -> AcquiredTarget:
        """Step 5 — the account's link becomes a URL anything can `GET`."""
        body = await self._call(client, cfg, "POST", "/unrestrict/link",
                                data={"link": link})
        if not isinstance(body, dict):
            raise RealDebridError(
                f"{_where(cfg)} answered something unexpected for this link")
        url = body.get("download")
        if not isinstance(url, str) or not url.lower().startswith("https://"):
            # Not interpolated into the message. This is the field that holds
            # the credential, and a message saying what it was would print it.
            raise RealDebridError(
                "Real-Debrid did not answer a usable download link")

        named = body.get("filename")
        if isinstance(named, str) and named.strip():
            filename = named.strip()
        try:
            size = max(0, int(body.get("filesize") or 0)) or size
        except (TypeError, ValueError):
            pass
        return AcquiredTarget(url=url, filename=filename, size=size,
                              info_hash=info_hash, provider=self.name)

    # ── the one request, and every way it can fail ─────────────────────────

    async def _call(self, client: httpx.AsyncClient, cfg: RealDebridConfig,
                    method: str, path: str, data: dict | None = None,
                    content: bytes | None = None) -> object:
        """Every branch raises `RealDebridError` with a message safe to show.

        That is the half of the contract that lives here: `jobs._settle()`
        copies the text onto a row a player reads, precisely because the text
        *could* carry a token or an unrestricted URL, and it is this function's
        job that it never does.

        `data` is a form body, which is what every documented endpoint here
        takes; `content` is a raw one, which only `PUT /torrents/addTorrent`
        does. They are mutually exclusive and the caller picks — a function
        that guessed from the method would be one more thing to be wrong about.
        """
        headers = {"Content-Type": "application/x-bittorrent"} if content \
            is not None else None
        try:
            r = await client.request(method, f"{cfg.api_url}{path}", data=data,
                                     content=content, headers=headers)
        except httpx.TimeoutException:
            raise RealDebridError(
                f"{_where(cfg)} did not answer within {cfg.timeout:g}s"
            ) from None
        except httpx.HTTPError as e:
            # Message deliberately not interpolated: httpx puts the full
            # request URL in some of these, and the token is in the headers of
            # the request it is describing.
            raise RealDebridError(
                f"{_where(cfg)} could not be reached "
                f"({type(e).__name__})") from None

        if r.status_code in (401, 403):
            raise RealDebridError(
                f"{_where(cfg)} refused the API token (HTTP {r.status_code}) — "
                "check it is current and the account is active")
        if r.status_code == 404:
            raise RealDebridError(
                f"{_where(cfg)} has no {path.split('/')[1]} endpoint — is that "
                "URL the Real-Debrid REST root?")
        if r.status_code == 503:
            # What Real-Debrid answers for a link or a hoster it will not
            # serve. Its own `error` text is a short English phrase and carries
            # nothing private, so it is shown when there is one.
            raise RealDebridError(
                f"Real-Debrid does not support this release"
                f"{self._detail(r)}")
        if r.status_code >= 300:
            # 3xx included: redirects are not followed, so one arriving here is
            # a misconfiguration rather than a step on the way somewhere.
            raise RealDebridError(
                f"{_where(cfg)} answered HTTP {r.status_code}{self._detail(r)}")

        if r.status_code == 204 or not r.content:
            # `selectFiles` answers 204 with an empty body, and that is success.
            return {}
        try:
            return r.json()
        except ValueError:
            raise RealDebridError(
                f"{_where(cfg)} answered something that is not JSON") from None

    @staticmethod
    def _detail(r: httpx.Response) -> str:
        """Real-Debrid's own one-line `error`, when it sent one.

        Capped and stripped of anything that is not plain text. The body of an
        error response is the one place a service can be relied on to be terse,
        but it is still a stranger's string on its way to a database row and a
        television screen.
        """
        try:
            body = r.json()
        except ValueError:
            return ""
        if not isinstance(body, dict):
            return ""
        text = body.get("error")
        if not isinstance(text, str) or not text.strip():
            return ""
        clean = " ".join(text.split())[:120]
        return f" — {clean}" if clean else ""
