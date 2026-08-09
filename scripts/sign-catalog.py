#!/usr/bin/env python3
"""Build and sign a catalogue bundle for the OTA channel.

    scripts/sign-catalog.py --new-key ~/gamecore-catalog.key
    scripts/sign-catalog.py --key ~/gamecore-catalog.key --out catalog.bundle.json

Run by a human, on a machine of their choosing. Never by CI, never on a box.

The private key is taken by PATH and is never written into, read from or
defaulted to anywhere inside this repository. That is not a style preference:
the catalogue decides which application every box installs and which one it
launches, so whoever holds this key holds the fleet. `.gitignore` refuses the
obvious filenames as a safety net against an accident — it is not the control.

The bundle
----------
One JSON envelope::

    {"payload": "<base64 of the catalogue JSON>", "sig": "<base64 Ed25519>"}

The signature covers the payload BYTES, so the envelope carries them base64'd
rather than as a nested object. JSON is not byte-stable across writers — key
order, unicode escaping, float formatting — and verifying a re-serialisation
would verify something nobody signed.

The payload is `{"version": N, "packs": {...}}`, where N comes from
`catalog/CATALOG_VERSION`. A box refuses a bundle whose version is not strictly
greater than the one it already applied: an old bundle is a validly signed
bundle, and replaying it is how an adversary who can serve bytes puts back the
app id the new one fixes. **Bump CATALOG_VERSION before signing**, or every box
will correctly refuse the result.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CATALOG = ROOT / "catalog"


def _require_cryptography():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        sys.exit("sign-catalog: needs `pip install cryptography`")
    return ed25519


def new_key(path: Path) -> int:
    ed25519 = _require_cryptography()
    if path.exists():
        sys.exit(f"sign-catalog: {path} already exists — refusing to overwrite a "
                 f"signing key")
    if _inside_repo(path):
        sys.exit(f"sign-catalog: {path} is inside the repository. A signing key "
                 f"there is one `git add -A` from being published; keep it "
                 f"somewhere else entirely.")

    private = ed25519.Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    raw_priv = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    raw_pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)

    # 0600 before a byte is written, not after: a key that is world-readable
    # for the microsecond between two syscalls has been world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        f.write(base64.b64encode(raw_priv).decode() + "\n")

    pub_path = CATALOG / "_ota" / "catalog-signing.pub"
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_text(base64.b64encode(raw_pub).decode() + "\n", encoding="utf-8")

    print(f"sign-catalog: private key  {path}  (0600, never commit this)")
    print(f"sign-catalog: public key   {pub_path.relative_to(ROOT)}  (commit this)")
    print("sign-catalog: every box trusts the public key its release shipped, so "
          "rotating means cutting a release.")
    return 0


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def build_payload() -> dict:
    """The packs, as the boxes will read them.

    Read from `catalog/` directly rather than through `load_catalog()`: the
    loader merges in whatever is on THIS machine — a local pack in
    `config/catalog.d/`, a previously applied OTA tier — and signing that would
    push one developer's local state to the whole fleet.
    """
    from backend.services.catalog.ota import FORBIDDEN_BLOCKS, shipped_version

    version = shipped_version(CATALOG)
    if version <= 0:
        sys.exit(f"sign-catalog: {CATALOG / 'CATALOG_VERSION'} is missing or not "
                 f"a positive integer")

    packs = {}
    for directory in sorted(CATALOG.iterdir()):
        if not directory.is_dir() or directory.name.startswith(("_", ".")):
            continue
        manifest = directory / "pack.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        carried = sorted(set(data) & set(FORBIDDEN_BLOCKS))
        if carried:
            # Dropped here as well as on the box. A bundle that visibly carries
            # blocks the receiver will silently discard is a bundle whose author
            # thinks they shipped something they did not.
            print(f"sign-catalog: {directory.name}: dropping {', '.join(carried)} "
                  f"— a remote pack is data only")
            data = {k: v for k, v in data.items() if k not in FORBIDDEN_BLOCKS}
        packs[directory.name] = data

    return {"version": version, "packs": packs}


def sign(key_path: Path, out: Path) -> int:
    ed25519 = _require_cryptography()
    try:
        raw = base64.b64decode(key_path.read_text(encoding="utf-8").strip(),
                               validate=True)
    except (OSError, ValueError) as e:
        sys.exit(f"sign-catalog: cannot read {key_path} — {e}")
    if len(raw) != 32:
        sys.exit(f"sign-catalog: {key_path} is {len(raw)} bytes, expected a raw "
                 f"32-byte Ed25519 private key")
    private = ed25519.Ed25519PrivateKey.from_private_bytes(raw)

    payload = json.dumps(build_payload(), indent=2, ensure_ascii=False,
                         sort_keys=True).encode("utf-8")
    envelope = {
        "payload": base64.b64encode(payload).decode(),
        "sig": base64.b64encode(private.sign(payload)).decode(),
    }
    out.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    version = json.loads(payload)["version"]
    print(f"sign-catalog: wrote {out} — catalogue version {version}, "
          f"{len(json.loads(payload)['packs'])} pack(s)")
    print("sign-catalog: a box refuses anything not strictly newer than what it "
          "already applied — bump catalog/CATALOG_VERSION if this is a re-sign.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new-key", type=Path, metavar="PATH",
                    help="generate a keypair; writes the public half into catalog/_ota/")
    ap.add_argument("--key", type=Path, help="the private key to sign with")
    ap.add_argument("--out", type=Path, default=ROOT.parent / "catalog.bundle.json",
                    help="where to write the signed bundle (default: beside the repo)")
    args = ap.parse_args()

    if args.new_key:
        return new_key(args.new_key)
    if not args.key:
        ap.error("give --key to sign, or --new-key to generate one")
    return sign(args.key, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
