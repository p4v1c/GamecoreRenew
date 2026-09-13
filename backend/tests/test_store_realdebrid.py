"""The Real-Debrid acquisition provider, against recorded answers and nothing else.

**No test here reaches the network.** Every request is served by an
`httpx.MockTransport` handler that answers from a literal in this file, so the
whole suite runs on a box with the cable out, and a regression that started
making a real request would fail rather than quietly spend somebody's account.

**No real credential appears anywhere.** The API root is `realdebrid.invalid`,
which cannot resolve by RFC 2606, the token is a row of zeros, and every host
in every fixture is `.invalid` too.

**Nothing downloads.** Acquiring *resolves*: it answers an `AcquiredTarget` and
moves no bytes. There is no file in this suite's `tmp_path` at the end of any
test that was not there at the start, and `test_store_jobs.py` holds the
data-tree guard that says so for the whole queue.

What is pinned, in the order it matters:

  · **an unconfigured box has no acquisition provider** — no
    `config/store-realdebrid.json` means `jobs.acquisition_provider()` answers
    `None` and every job fails with `NO_PROVIDER`, exactly as it did before
    this file existed. That is the property every other decision here was made
    around;
  · **the token stays on this side** — it travels as an `Authorization` header,
    never in a URL, never in a raised exception, never on a job's reason;
  · **an unrestricted URL is a credential too** — it is what Real-Debrid
    answers, anyone holding one spends the owner's bandwidth, and it appears in
    no journal line and on no row;
  · **every failure says which one it was** — a token refused, a release
    nothing supports, a wait that ran out and an answer that made no sense are
    four different sentences on the job, and each is true.
"""
from __future__ import annotations

import asyncio
import json
import logging
import stat
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import paths                                  # noqa: E402
from backend.services.store import jobs, resolve                    # noqa: E402
from backend.services.store.realdebrid import (                     # noqa: E402
    CONFIG_FILENAME, RealDebridAcquisition, RealDebridConfig, RealDebridError,
    config_file, load_config, save_config)

#: Reserved by RFC 2606 — it cannot resolve, so a test that started making a
#: real request fails instead of reaching Real-Debrid with a real token.
FAKE_API = "https://realdebrid.invalid/rest/1.0"
#: Obviously not a token. Distinctive enough to grep a request or a message for.
FAKE_TOKEN = "0000000000000000000000000000dead"
#: 40 hex, and plainly not a real release.
HASH = "a1" * 20
SOURCE = f"prowlarr://3/https://tracker.invalid/details/1#btih:{HASH}"


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A box with a data root of its own and no Real-Debrid configured."""
    monkeypatch.setattr(paths, "GAMECORE_DATA", tmp_path)
    (tmp_path / "config").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def configured(box):
    """…and now it is, against a host that cannot resolve."""
    save_config(RealDebridConfig(api_key=FAKE_TOKEN, api_url=FAKE_API, wait=0))
    return box


def _job(**over) -> jobs.Job:
    """One queue row, as `jobs.enqueue` would have written it."""
    row = dict(
        id="0" * 32, system_id="gopher64", roms_dir="emu/n64",
        title="The Legend of Zelda - Ocarina of Time (USA)",
        filename="Zelda.z64", format="z64", size=32 * 1024 * 1024,
        provider="prowlarr", source=SOURCE, state="running", reason="",
        queued_at="2026-09-13T00:00:00+00:00",
        started_at="2026-09-13T00:00:01+00:00", ended_at="")
    row.update(over)
    return jobs.Job(**row)


# ── the recorded conversation ──────────────────────────────────────────────

def _rd(*, files=None, status="downloaded", links=None, add=None,
        unrestrict=None, capture=None, overrides=None):
    """A Real-Debrid that behaves, unless a test says otherwise.

    One handler for the whole five-step conversation, because the steps are
    only meaningful in sequence: a test that stubbed `unrestrict` alone would
    not notice that nothing ever selected a file.

    `overrides` maps a path fragment onto an `httpx.Response`, which is how
    each failure test breaks exactly one step and leaves the rest honest.
    """
    files = [{"id": 1, "path": "/Zelda.z64", "bytes": 32 * 1024 * 1024,
              "selected": 0}] if files is None else files
    links = ["https://real-debrid.invalid/d/ABCDEF"] if links is None else links

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        path = request.url.path
        for fragment, response in (overrides or {}).items():
            if fragment in path:
                return response
        if path.endswith("/torrents/addMagnet"):
            return httpx.Response(201, json=add if add is not None else {
                "id": "TORRENTID", "uri": "https://realdebrid.invalid/t/1"})
        if "/torrents/info/" in path:
            return httpx.Response(200, json={
                "id": "TORRENTID", "filename": "Zelda.z64",
                "hash": HASH, "status": status, "progress": 100,
                "files": files, "links": links})
        if "/torrents/selectFiles/" in path:
            return httpx.Response(204)
        if path.endswith("/unrestrict/link"):
            return httpx.Response(200, json=unrestrict if unrestrict is not None
                                  else {"filename": "Zelda.z64",
                                        "filesize": 33554432,
                                        "download": "https://dl.invalid/x/Zelda.z64"})
        return httpx.Response(404, json={"error": "unknown endpoint"})
    return handler


def _provider(handler) -> RealDebridAcquisition:
    return RealDebridAcquisition(transport=httpx.MockTransport(handler))


def _acquire(handler, job=None) -> jobs.AcquiredTarget:
    return asyncio.run(_provider(handler).acquire(job or _job()))


def _step(request: httpx.Request) -> str:
    """`POST /torrents/addMagnet` — the method and the endpoint, no ids.

    The torrent id is minted by the service, so a test that compared whole
    paths would be asserting the fixture's own literal back at itself. What
    matters is the sequence of *steps*.
    """
    path = request.url.path.removeprefix("/rest/1.0")
    for endpoint in ("/torrents/info", "/torrents/selectFiles"):
        if path.startswith(endpoint):
            path = endpoint
            break
    return f"{request.method} {path}"


# ── an unconfigured box is exactly what it was ─────────────────────────────

def test_a_box_with_no_configuration_has_no_acquisition_provider(box):
    """The property the whole step was built around.

    Nothing about adding a real provider may change what a box that has not
    configured one does. Every job still fails with `NO_PROVIDER`, which is the
    honest answer and the one the screen already draws.
    """
    assert not config_file().exists()
    assert load_config() is None
    assert RealDebridAcquisition.configured() is False
    assert jobs.acquisition_provider() is None


def test_configuring_it_is_what_turns_it_on(configured):
    """No environment variable, no unit to edit, no OTA to survive.

    The file *is* the switch, exactly as `store-prowlarr.json` is the switch
    for searching. `config/` is excluded from the OTA rsync, so it survives an
    update by itself.
    """
    provider = jobs.acquisition_provider()
    assert provider is not None
    assert provider.name == "realdebrid"


@pytest.mark.parametrize("body", [
    "{}", '{"apiKey": ""}', '{"apiKey": "   "}', '[]', "not json at all", "",
])
def test_an_incomplete_file_leaves_the_box_with_no_provider(box, body):
    """Absent, malformed and incomplete are one answer and not a red screen.

    All four end the same way — no provider, and jobs that fail saying so. A
    Store that threw because a file nobody has ever created is unusable would
    be a broken-looking box with nothing actually wrong with it.
    """
    config_file().write_text(body)
    assert load_config() is None
    assert jobs.acquisition_provider() is None


def test_the_file_is_written_private_and_atomically(box):
    path = save_config(RealDebridConfig(api_key=FAKE_TOKEN, api_url=FAKE_API))
    assert path == config_file()
    assert path.name == CONFIG_FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # `os.replace` over a private temp file, the way auth.py writes a secret —
    # so no half-written file is ever left behind for a reader to parse.
    assert not list(path.parent.glob("*.tmp"))


def test_it_lives_beside_the_other_secrets_in_config(box):
    from backend.services.store.prowlarr import config_file as prowlarr_file
    assert config_file().parent == prowlarr_file().parent == box / "config"


def test_both_spellings_of_every_key_are_accepted(box):
    """The file is typed by hand over SSH; a capital letter is not a reason to
    refuse it."""
    config_file().write_text(json.dumps({
        "api_key": FAKE_TOKEN, "api_url": FAKE_API,
        "timeout_seconds": 9, "wait_seconds": 30}))
    cfg = load_config()
    assert cfg.api_key == FAKE_TOKEN and cfg.api_url == FAKE_API
    assert cfg.timeout == 9 and cfg.wait == 30


def test_a_token_pasted_into_the_url_is_dropped_before_it_can_be_sent(box):
    """A URL is what proxies log and what exceptions print."""
    config_file().write_text(json.dumps(
        {"apiKey": FAKE_TOKEN,
         "apiUrl": f"https://realdebrid.invalid/rest/1.0?auth_token={FAKE_TOKEN}"}))
    cfg = load_config()
    assert cfg.api_url == "https://realdebrid.invalid/rest/1.0"
    assert FAKE_TOKEN not in cfg.api_url


@pytest.mark.parametrize("written,expected", [
    (0, 1.0), (9999, 120.0), ("nonsense", 20.0),
])
def test_the_timeout_is_clamped_to_something_a_television_can_wait_for(
        box, written, expected):
    config_file().write_text(json.dumps({"apiKey": FAKE_TOKEN,
                                         "timeout": written}))
    assert load_config().timeout == expected


def test_a_world_readable_file_is_reported_and_still_used(box, caplog):
    """Loud, and not a refusal — the same trade `prowlarr.py` makes.

    A hand-made file is 0644 under a default umask. A box that silently had no
    acquisition provider because of a permission bit looks broken with no way
    to find out why.
    """
    save_config(RealDebridConfig(api_key=FAKE_TOKEN, api_url=FAKE_API))
    config_file().chmod(0o644)
    from backend.services.store import realdebrid
    realdebrid._warned.clear()
    with caplog.at_level(logging.WARNING):
        assert load_config() is not None
    assert "chmod 600" in caplog.text
    assert FAKE_TOKEN not in caplog.text


# ── the credential stays on this side ──────────────────────────────────────

def test_the_token_travels_in_a_header_and_never_in_the_url(configured):
    seen: list[httpx.Request] = []
    _acquire(_rd(capture=seen))
    assert seen, "no request was made at all"
    for request in seen:
        assert request.headers.get("Authorization") == f"Bearer {FAKE_TOKEN}"
        assert FAKE_TOKEN not in str(request.url)
        assert FAKE_TOKEN not in (request.url.query or b"").decode()


def test_redirects_are_not_followed_so_the_token_goes_nowhere_else(configured):
    """A redirect would hand `Authorization` to whatever host it named — a
    token given to a third party by somebody else's misconfiguration."""
    moved = httpx.Response(302, headers={
        "Location": "https://elsewhere.invalid/collect"})
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(overrides={"addMagnet": moved}))
    assert "302" in str(e.value)
    assert "elsewhere.invalid" not in str(e.value)


def test_the_unrestricted_url_never_reaches_a_log_line_or_a_reason(
        configured, caplog):
    """The URL Real-Debrid answers is itself a credential.

    It is minted against the owner's account and anyone holding it spends
    their bandwidth. So it is on no journal line, and `Job` has no field to put
    it on at all — the target is handed to the materializer in memory and
    nowhere else.
    """
    secret = "https://dl.invalid/x/AAAA-secret-BBBB/Zelda.z64"
    with caplog.at_level(logging.DEBUG):
        target = _acquire(_rd(unrestrict={"filename": "Zelda.z64",
                                          "filesize": 12, "download": secret}))
    assert target.url == secret               # the caller gets it…
    assert secret not in caplog.text          # …and the journal does not
    assert "AAAA-secret-BBBB" not in target.redacted()
    assert not hasattr(jobs.Job, "url")


# ── the success path ───────────────────────────────────────────────────────

def test_a_magnet_becomes_a_direct_link_and_nothing_is_downloaded(configured,
                                                                  box):
    """The whole conversation, end to end, writing nothing.

    Five requests in order: add the magnet, ask what is in it, select the one
    file, confirm it is ready, unrestrict the link. What comes back is a URL
    and what it takes to check the bytes — not the bytes.
    """
    before = sorted(p.relative_to(box).as_posix() for p in box.rglob("*"))
    seen: list[httpx.Request] = []
    target = _acquire(_rd(capture=seen))

    assert [_step(r) for r in seen] == [
        "POST /torrents/addMagnet",
        "GET /torrents/info",
        "POST /torrents/selectFiles",
        "GET /torrents/info",
        "POST /unrestrict/link",
    ]
    assert isinstance(target, jobs.AcquiredTarget)
    assert target.url == "https://dl.invalid/x/Zelda.z64"
    assert target.filename == "Zelda.z64"
    assert target.size == 33554432
    assert target.info_hash == HASH
    assert target.provider == "realdebrid"
    # Resolving is not downloading.
    assert sorted(p.relative_to(box).as_posix() for p in box.rglob("*")) == before


def test_the_magnet_sent_is_the_hash_and_nothing_else(configured):
    """Trackerless on purpose.

    A magnet an indexer answers can carry a private tracker's passkey in its
    `tr=` parameters, and that is a credential belonging to the owner's
    account. Only the hash survives the trip through `resolve.py`.
    """
    seen: list[httpx.Request] = []
    _acquire(_rd(capture=seen))
    body = seen[0].content.decode()
    assert f"btih%3A{HASH}" in body or f"btih:{HASH}" in body
    assert "tr=" not in body and "passkey" not in body


def test_the_file_the_player_chose_is_the_file_selected(configured):
    """A release is often a folder: a ROM, a NFO, a cover and a readme.

    The row the player looked at named one file, so that is the one asked for —
    by name, not by position and not by size.
    """
    seen: list[httpx.Request] = []
    _acquire(_rd(capture=seen, files=[
        {"id": 1, "path": "/Release/readme.txt", "bytes": 100},
        {"id": 7, "path": "/Release/Zelda.z64", "bytes": 32 * 1024 * 1024},
        {"id": 9, "path": "/Release/cover.png", "bytes": 900_000_000},
    ]))
    select = next(r for r in seen if "selectFiles" in r.url.path)
    assert "files=7" in select.content.decode()


def test_when_no_file_matches_the_biggest_one_wins(configured):
    """Not a guess about *what* the file is — matrix §5.1 decides that from the
    bytes — only about which of several is the payload. The biggest file in a
    ROM release is not the readme."""
    seen: list[httpx.Request] = []
    _acquire(_rd(capture=seen, files=[
        {"id": 1, "path": "/readme.txt", "bytes": 100},
        {"id": 4, "path": "/Some Other Name.z64", "bytes": 40_000_000},
    ]))
    select = next(r for r in seen if "selectFiles" in r.url.path)
    assert "files=4" in select.content.decode()


def test_real_debrid_may_correct_the_name_and_the_size(configured):
    """What the indexer claimed is a claim; what the service answers is
    measured. The larger truth wins, and `size` is never a guess."""
    target = _acquire(_rd(unrestrict={
        "filename": "Zelda (USA).z64", "filesize": 12345,
        "download": "https://dl.invalid/x/y"}))
    assert target.filename == "Zelda (USA).z64"
    assert target.size == 12345


# ── the failures, one sentence each ────────────────────────────────────────

@pytest.mark.parametrize("status,expected", [
    (401, "refused the API token"),
    (403, "refused the API token"),
    (503, "does not support this release"),
    (500, "HTTP 500"),
])
def test_every_failure_is_named_and_carries_no_secret(configured, status,
                                                      expected):
    """Four different things going wrong, four different sentences.

    Each goes onto the job row verbatim — `jobs._settle` copies the text — so
    each has to be both true and safe to show a player.
    """
    broken = httpx.Response(status, json={"error": "some upstream detail"})
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(overrides={"addMagnet": broken}))
    message = str(e.value)
    assert expected in message
    assert FAKE_TOKEN not in message


def test_a_release_with_no_hash_is_refused_before_anything_is_asked(configured):
    """The commonest "unsupported link" there is, and it costs no request.

    A usenet release has no info hash and neither does a torznab row that
    published none. `resolve.py` refuses it by name, and the message says what
    is missing rather than blaming a service that was never contacted.
    """
    seen: list[httpx.Request] = []
    with pytest.raises(resolve.UnresolvableSource) as e:
        _acquire(_rd(capture=seen), _job(source="prowlarr://3/some-guid"))
    assert "without a torrent hash" in str(e.value)
    assert seen == [], "a source that cannot resolve must cost no request"


def test_a_demo_row_says_so_rather_than_blaming_real_debrid(configured):
    """The demo provider's rows are invented and the banner says so. A job made
    from one is a player trying to download a game that does not exist, and the
    sentence they read has to say that and not "Real-Debrid failed"."""
    with pytest.raises(resolve.UnresolvableSource) as e:
        _acquire(_rd(), _job(source="demo://nes/whatever"))
    assert "examples, not real games" in str(e.value)


@pytest.mark.parametrize("state,expected", [
    ("magnet_error", "could not read this release's magnet"),
    ("error", "could not fetch this release"),
    ("virus", "refused this release as unsafe"),
    ("dead", "nobody is sharing this release"),
])
def test_a_release_real_debrid_will_not_serve_says_which_it_was(
        configured, state, expected):
    """A dead torrent is not a rejected file and neither is a broken magnet.
    One reason each, because the player's next move differs."""
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(status=state))
    assert expected in str(e.value)


def test_a_wait_that_runs_out_says_so_and_leaves_the_torrent_alone(configured):
    """Real-Debrid keeps fetching after this box gives up, on purpose.

    The account has already started the work and paid for it, so tearing it
    down would throw that away. The message says to come back, because coming
    back is what actually works: the second attempt finds it cached.
    """
    seen: list[httpx.Request] = []
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(capture=seen, status="downloading"))
    assert "still fetching" in str(e.value) and "downloading" in str(e.value)
    assert "queue it again" in str(e.value)
    # Nothing was deleted: this box does not manage the owner's torrent list.
    assert not any(r.method == "DELETE" for r in seen)


def test_a_status_nobody_here_knows_is_reported_as_itself(configured):
    """Not assumed fatal and not assumed to be progress.

    Real-Debrid's vocabulary is theirs to extend, and a box that treated an
    unknown word as success would report `done` for a download that never
    happened.
    """
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(status="reticulating_splines"))
    assert "reticulating_splines" in str(e.value)


@pytest.mark.parametrize("override,expected", [
    ({"addMagnet": httpx.Response(200, json={"nope": 1})}, "named no torrent"),
    ({"unrestrict": httpx.Response(200, json={"filename": "x"})},
     "did not answer a usable download link"),
    ({"unrestrict": httpx.Response(200, text="<html>maintenance</html>")},
     "not JSON"),
])
def test_an_answer_that_is_not_the_expected_shape_is_a_failure_not_a_crash(
        configured, override, expected):
    """Somebody else's service, answering something new.

    Each of these would be an `AttributeError` or a `KeyError` in a client that
    trusted the shape, and a traceback is not a sentence a player can read.
    """
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(overrides=override))
    assert expected in str(e.value)


def test_a_release_with_no_files_in_it_is_a_failure(configured):
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd(files=[]))
    assert "no files" in str(e.value)


def test_a_timeout_says_how_long_it_waited(configured):
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)
    with pytest.raises(RealDebridError) as e:
        _acquire(slow)
    message = str(e.value)
    assert "did not answer within" in message
    assert "realdebrid.invalid" in message
    assert FAKE_TOKEN not in message


def test_a_service_that_cannot_be_reached_does_not_print_the_request(
        configured):
    """httpx puts the full request URL in some of these, and the token is in
    the headers of the request being described."""
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)
    with pytest.raises(RealDebridError) as e:
        _acquire(down)
    assert "could not be reached" in str(e.value)
    assert "ConnectError" in str(e.value)
    assert FAKE_TOKEN not in str(e.value)


def test_the_credentials_disappearing_mid_flight_is_a_failure_not_a_crash(
        configured):
    config_file().unlink()
    with pytest.raises(RealDebridError) as e:
        _acquire(_rd())
    assert CONFIG_FILENAME in str(e.value)


# ── the two joined together ────────────────────────────────────────────────

def test_a_failure_reaches_the_job_row_as_its_reason(configured, monkeypatch):
    """The end-to-end property the whole "safe to show" contract exists for.

    A provider's sentence is copied onto a row a player reads after a reboot,
    so this walks the worker rather than asserting the exception alone.
    """
    from backend.tests.test_store_jobs import _memory_db, _no_worker, _queue

    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        monkeypatch.setattr(
            jobs, "acquisition_provider",
            lambda: _provider(_rd(status="dead")))
        try:
            job = await _queue(source=SOURCE)
            await jobs.drain()
            after = await jobs.get(job.id)
            assert after.state == "failed"
            assert after.reason == "nobody is sharing this release any more"
            assert FAKE_TOKEN not in after.reason
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_a_job_that_resolves_still_fails_because_nothing_stores_it(
        configured, monkeypatch):
    """The real box, with a real token, today.

    Acquisition works and the job still ends `failed` — with `NO_MATERIALIZER`,
    not `NO_PROVIDER`, because those are different facts and the player who
    reads the second one would go and check an account that is fine.
    """
    from backend.tests.test_store_jobs import _memory_db, _no_worker, _queue

    async def scenario():
        conn = await _memory_db(monkeypatch)()
        _no_worker(monkeypatch)
        monkeypatch.setattr(jobs, "acquisition_provider",
                            lambda: _provider(_rd()))
        try:
            assert jobs.materializer() is None
            job = await _queue(source=SOURCE)
            await jobs.drain()
            after = await jobs.get(job.id)
            assert after.state == "failed"
            assert after.reason == jobs.NO_MATERIALIZER
        finally:
            await conn.close()

    asyncio.run(scenario())


# ── the manual check ───────────────────────────────────────────────────────

def test_the_manual_resolve_check_exists_and_says_it_is_manual():
    """`scripts/realdebrid-resolve-check.py`, pinned but never run.

    It needs a real Prowlarr, a real Real-Debrid account and the credentials of
    both, so it cannot be a gate — this file is the gate. What is asserted is
    that it exists, that it is honest about what it needs, and that it says in
    its own header that it reads no configuration file, writes nothing and
    downloads nothing. **The suite never executes it**: doing so would need
    somebody's paid account.
    """
    script = ROOT / "scripts/realdebrid-resolve-check.py"
    assert script.is_file(), "the manual resolve check is gone"
    header = script.read_text()[:6000]

    # Manual, and why it cannot be automated.
    assert "Run by hand, never in CI" in header
    assert "REALDEBRID_API_KEY" in header
    # It touches neither of the box's credential files.
    assert "config/store-realdebrid.json" in header
    assert "reads and writes nothing" in header.lower()
    assert "downloads nothing" in header.lower()
    # And it is pointed at the gates that do run.
    assert "backend/tests/test_store_realdebrid.py" in header


def test_the_manual_check_reads_no_credential_file_from_disk():
    """It takes every credential from the environment, and nothing else.

    A laptop that ran it must not end up configured as though it were the box,
    and the box's own files must not be read by a script somebody runs as
    themselves. Asserted against the source because running it is what this
    test exists to avoid.
    """
    body = (ROOT / "scripts/realdebrid-resolve-check.py").read_text()
    assert "os.environ" in body
    for forbidden in ("save_config(", "load_config()", "write_text(",
                      "config_file(", "open("):
        assert forbidden not in body, (
            f"the manual check must not {forbidden} — it reads the environment")
