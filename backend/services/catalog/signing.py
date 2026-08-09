"""Ed25519 verification for the catalogue OTA channel.

Read this before touching `ota.py`. The remote catalogue decides which
application a box installs and which one it launches. An unsigned channel is
not a convenience feature with a security gap to close later — it is a remote
code execution primitive with a nice API, and whoever controls the endpoint,
the DNS or the TLS terminator controls every box in the fleet.

So verification is not a step `ota.py` performs. It is the only way to get a
parsed catalogue out of this module at all: `verify()` returns the payload or
raises, and there is no function that parses without verifying. A future caller
cannot forget the check, because there is nothing to forget.

Design notes, each with a reason
--------------------------------
**Verify only.** No signing here. The private key never touches a box, never
touches CI, and never touches this repository — see `scripts/sign-catalog.py`,
which is run by a human on a machine of their choosing and takes the key by
path. `.gitignore` refuses the obvious filenames, but that is a safety net for
an accident, not a control.

**The signature covers the exact bytes.** Not the re-serialised object. JSON
round-trips are not byte-stable — key order, unicode escaping and float
formatting all vary between writers — so verifying a re-encoding would verify
something nobody signed. The envelope carries the payload as base64 for that
reason and no other.

**Rollback is an attack.** An old catalogue is a validly signed catalogue: an
adversary who can serve bytes can replay yesterday's, putting back the dead app
id that today's fixes. The version check lives in `ota.py`, where the currently
applied version is known, and it is as much a part of this than the maths here.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Shipped in the repository, replaced only by a release. A box trusts exactly
# what its installed version trusts.
PUBLIC_KEY_NAME = "catalog-signing.pub"


class SignatureError(Exception):
    """The bundle is not something this box will act on. Never subclassed by
    "the network was slow" — a caller must be able to treat this as hostile."""


def load_public_key(path: Path):
    """The trusted key, as an Ed25519PublicKey.

    Stored base64 (44 chars for 32 raw bytes) rather than PEM: one line, no
    parser, and nothing that could be mistaken for a private key at a glance.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as e:                        # pragma: no cover - dep is pinned
        raise SignatureError(
            "the cryptography package is missing — the catalogue OTA channel "
            "cannot verify anything and is therefore refused entirely") from e

    try:
        raw = base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True)
    except (OSError, ValueError, binascii.Error) as e:
        raise SignatureError(f"{path}: unreadable public key — {e}") from e
    if len(raw) != 32:
        raise SignatureError(
            f"{path}: {len(raw)} bytes, expected 32 — an Ed25519 public key is "
            f"32 raw bytes, base64-encoded")
    return Ed25519PublicKey.from_public_bytes(raw)


def verify(envelope_bytes: bytes, public_key_path: Path) -> dict:
    """The signed catalogue inside `envelope_bytes`, or `SignatureError`.

    The envelope is::

        {"payload": "<base64 of the catalogue JSON>", "sig": "<base64 Ed25519>"}

    Every failure below is deliberately the same class of answer — refuse — and
    deliberately a distinct message. "Refused" with no reason is what makes an
    operator disable the check to get their fix out.
    """
    try:
        from cryptography.exceptions import InvalidSignature
    except ImportError as e:                        # pragma: no cover - dep is pinned
        raise SignatureError("the cryptography package is missing") from e

    key = load_public_key(public_key_path)

    try:
        envelope = json.loads(envelope_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise SignatureError(f"the bundle is not JSON — {e}") from e
    if not isinstance(envelope, dict):
        raise SignatureError("the bundle is not a JSON object")

    missing = [k for k in ("payload", "sig") if k not in envelope]
    if missing:
        raise SignatureError(f"the bundle has no {' and no '.join(missing)}")

    try:
        payload = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["sig"], validate=True)
    except (TypeError, ValueError, binascii.Error) as e:
        raise SignatureError(f"payload or signature is not valid base64 — {e}") from e

    try:
        key.verify(signature, payload)
    except InvalidSignature as e:
        raise SignatureError(
            "the signature does not match the payload — this bundle was not "
            "produced by the holder of the catalogue signing key, or it was "
            "modified in transit") from e

    # AFTER verification, never before. Parsing attacker-controlled JSON to
    # decide whether to check its signature is the check happening second.
    try:
        catalogue = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise SignatureError(f"the signed payload is not JSON — {e}") from e
    if not isinstance(catalogue, dict):
        raise SignatureError("the signed payload is not a JSON object")
    return catalogue
