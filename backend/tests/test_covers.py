"""End-to-end tests for the cover pipeline, using synthetic game files.

Builds: a fake PS3 game folder (PARAM.SFO + ICON0.PNG), a fake PS4 folder,
a synthetic PSP ISO (ICON0 + PARAM.SFO inside ISO9660), synthetic PS1 (.bin,
raw 2352 MODE2) and PS2 (.iso, 2048) images with SYSTEM.CNF, and a fake
GameCube ISO header. Then exercises local_media directly and the FastAPI
endpoints via TestClient.

Run from anywhere:  python backend/tests/test_covers.py
The GameTDB/xlenore checks need internet; everything else is offline.
"""
import os
import shutil
import struct
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(tempfile.mkdtemp(prefix="gamecore-test-")) / "fake_root"

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fakepngdata" * 20


# ── Builders ──────────────────────────────────────────────────────────────────

def build_sfo(pairs: dict) -> bytes:
    keys = b""
    data = b""
    entries = b""
    offsets = []
    for k, v in pairs.items():
        koff = len(keys)
        keys += k.encode() + b"\x00"
        doff = len(data)
        raw = v.encode() + b"\x00"
        data += raw
        offsets.append((koff, 0x0204, len(raw), len(raw), doff))
    key_tbl = 20 + 16 * len(pairs)
    data_tbl = key_tbl + len(keys)
    out = struct.pack("<4sIIII", b"\x00PSF", 0x101, key_tbl, data_tbl, len(pairs))
    for koff, fmt, ln, mx, doff in offsets:
        out += struct.pack("<HHIII", koff, fmt, ln, mx, doff)
    return out + keys + data


def drec(name: bytes, extent: int, size: int, flags: int) -> bytes:
    n = len(name)
    rec_len = 33 + n + ((33 + n) % 2)
    rec = bytearray(rec_len)
    rec[0] = rec_len
    struct.pack_into("<I", rec, 2, extent)
    struct.pack_into(">I", rec, 6, extent)
    struct.pack_into("<I", rec, 10, size)
    struct.pack_into(">I", rec, 14, size)
    rec[25] = flags
    struct.pack_into("<H", rec, 28, 1)
    struct.pack_into(">H", rec, 30, 1)
    rec[32] = n
    rec[33:33 + n] = name
    return bytes(rec)


def build_iso(files: dict[str, bytes]) -> bytes:
    """Single-level-or-two-level ISO9660: files = {"SYSTEM.CNF": b"..", "PSP_GAME/ICON0.PNG": b".."}."""
    S = 2048
    # Layout: 16 PVD, 17 terminator, 18 root dir, 19 subdir (if any), 20+ file data
    tree: dict[str, dict] = {"": {}}
    for path, content in files.items():
        parts = path.split("/")
        if len(parts) == 1:
            tree[""][parts[0]] = content
        else:
            tree.setdefault(parts[0], {})[parts[1]] = content

    subdirs = [d for d in tree if d]
    root_lba, sub_lba = 18, 19
    data_lba = 19 + len(subdirs)

    # Assign extents for file contents
    extents: dict[tuple, tuple] = {}
    lba = data_lba
    for d, entries in tree.items():
        for name, content in entries.items():
            extents[(d, name)] = (lba, len(content))
            lba += max(1, (len(content) + S - 1) // S)
    total = lba

    img = bytearray(total * S)

    def put(lba_, data):
        img[lba_ * S: lba_ * S + len(data)] = data

    # Root directory
    root = drec(b"\x00", root_lba, S, 2) + drec(b"\x01", root_lba, S, 2)
    for i, d in enumerate(subdirs):
        root += drec(d.encode(), sub_lba + i, S, 2)
    for name, _ in tree[""].items():
        e, s = extents[("", name)]
        root += drec(name.encode() + b";1", e, s, 0)
    put(root_lba, root)

    # Subdirectories
    for i, d in enumerate(subdirs):
        sub = drec(b"\x00", sub_lba + i, S, 2) + drec(b"\x01", root_lba, S, 2)
        for name, _ in tree[d].items():
            e, s = extents[(d, name)]
            sub += drec(name.encode() + b";1", e, s, 0)
        put(sub_lba + i, sub)

    # File data
    for (d, name), (e, s) in extents.items():
        put(e, tree[d][name])

    # PVD + terminator
    pvd = bytearray(S)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[156:156 + 34] = drec(b"\x00", root_lba, S, 2)[:34]
    put(16, pvd)
    term = bytearray(S)
    term[0] = 255
    term[1:6] = b"CD001"
    put(17, term)
    return bytes(img)


def to_raw_2352(iso: bytes, mode: int = 2) -> bytes:
    """Wrap 2048-byte sectors into raw 2352 sectors (like a PS1 .bin dump)."""
    head = 16 if mode == 1 else 24
    out = bytearray()
    for i in range(0, len(iso), 2048):
        sector = bytearray(2352)
        sector[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"  # sync
        sector[head:head + 2048] = iso[i:i + 2048].ljust(2048, b"\x00")
        out += sector
    return bytes(out)


# ── Fixture setup ────────────────────────────────────────────────────────────

def setup_root():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / "config").mkdir(parents=True)

    # PS3 game folder — named by serial, like real dumps
    ps3 = ROOT / "emu/rpcs3/BLUS30443"
    (ps3 / "PS3_GAME").mkdir(parents=True)
    (ps3 / "PS3_GAME/ICON0.PNG").write_bytes(FAKE_PNG)
    (ps3 / "PS3_GAME/PARAM.SFO").write_bytes(build_sfo({
        "TITLE": "Demon's  Souls", "TITLE_ID": "BLUS30443", "CATEGORY": "DG",
    }))

    # PS4 game folder
    ps4 = ROOT / "emu/shadps4/CUSA00552"
    (ps4 / "sce_sys").mkdir(parents=True)
    (ps4 / "sce_sys/icon0.png").write_bytes(FAKE_PNG)
    (ps4 / "sce_sys/param.sfo").write_bytes(build_sfo({
        "TITLE": "Bloodborne", "TITLE_ID": "CUSA00552",
    }))

    # PSP ISO with embedded icon + sfo
    psp_dir = ROOT / "emu/ppsspp"
    psp_dir.mkdir(parents=True)
    (psp_dir / "SomePspGame.iso").write_bytes(build_iso({
        "PSP_GAME/ICON0.PNG": FAKE_PNG,
        "PSP_GAME/PARAM.SFO": build_sfo({"TITLE": "Crisis Core", "DISC_ID": "ULUS10336"}),
    }))

    # PS2 ISO with SYSTEM.CNF
    ps2_dir = ROOT / "emu/pcsx2"
    ps2_dir.mkdir(parents=True)
    (ps2_dir / "MyPs2Game.iso").write_bytes(build_iso({
        "SYSTEM.CNF": b"BOOT2 = cdrom0:\\SLUS_209.46;1\r\nVER = 1.00\r\n",
    }))

    # PS1 raw .bin with SYSTEM.CNF (MODE2 2352)
    ps1_dir = ROOT / "emu/duckstation"
    ps1_dir.mkdir(parents=True)
    (ps1_dir / "MyPs1Game.bin").write_bytes(to_raw_2352(build_iso({
        "SYSTEM.CNF": b"BOOT = cdrom:\\SCUS_949.00;1\r\nTCB = 4\r\n",
    })))

    # GameCube ISO header (just the ID6)
    gc_dir = ROOT / "emu/dolphin"
    gc_dir.mkdir(parents=True)
    (gc_dir / "Melee.iso").write_bytes(b"GALE01" + b"\x00" * 100)

    # systems.json pointing at the fake root
    import json
    systems = [
        {"id": "rpcs3", "name": "PS3", "romsPath": "emu/rpcs3/", "extensions": [], "scanDirs": True, "path": "/bin/true"},
        {"id": "shadps4", "name": "PS4", "romsPath": "emu/shadps4/", "extensions": [], "scanDirs": True, "path": "/bin/true"},
        {"id": "ppsspp", "name": "PSP", "romsPath": "emu/ppsspp/", "extensions": ["*.iso"], "path": "/bin/true"},
        {"id": "pcsx2", "name": "PS2", "romsPath": "emu/pcsx2/", "extensions": ["*.iso"], "path": "/bin/true"},
        {"id": "duckstation", "name": "PS1", "romsPath": "emu/duckstation/", "extensions": ["*.bin"], "path": "/bin/true"},
        {"id": "dolphin", "name": "GC", "romsPath": "emu/dolphin/", "extensions": ["*.iso"], "path": "/bin/true"},
    ]
    (ROOT / "config/systems.json").write_text(json.dumps(systems))
    (ROOT / "config/apps.json").write_text("[]")


# ── Tests ─────────────────────────────────────────────────────────────────────

failures = []

def check(name, cond, detail=""):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def main():
    os.environ["GAMECORE_PATH"] = str(ROOT)
    setup_root()
    sys.path.insert(0, str(REPO))

    from backend.services import local_media, sfo
    from backend.services.iso9660 import Iso9660

    # sfo
    meta = sfo.parse(ROOT / "emu/rpcs3/BLUS30443/PS3_GAME/PARAM.SFO")
    check("sfo.parse TITLE", meta.get("TITLE") == "Demon's  Souls", str(meta))

    # iso9660 direct
    iso = Iso9660.open(ROOT / "emu/ppsspp/SomePspGame.iso")
    check("iso9660 open 2048", iso is not None)
    data = iso.read_file("PSP_GAME/ICON0.PNG") if iso else None
    check("iso9660 nested file", data == FAKE_PNG)
    if iso:
        iso.close()

    # local titles
    check("PS3 title", local_media.get_title("rpcs3", ROOT / "emu/rpcs3/BLUS30443") == "Demon's Souls")
    check("PS4 title", local_media.get_title("shadps4", ROOT / "emu/shadps4/CUSA00552") == "Bloodborne")
    check("PSP title", local_media.get_title("ppsspp", ROOT / "emu/ppsspp/SomePspGame.iso") == "Crisis Core")

    # disc ids
    check("PS3 disc_id", local_media.disc_id("rpcs3", ROOT / "emu/rpcs3/BLUS30443") == ("ps3", "BLUS30443"))
    check("PS2 serial", local_media.disc_id("pcsx2", ROOT / "emu/pcsx2/MyPs2Game.iso") == ("ps2", "SLUS-20946"))
    check("PS1 serial (raw bin)", local_media.disc_id("duckstation", ROOT / "emu/duckstation/MyPs1Game.bin") == ("psx", "SCUS-94900"))
    check("GC id6", local_media.disc_id("dolphin", ROOT / "emu/dolphin/Melee.iso") == ("wii", "GALE01"))

    # icon extraction
    dest = ROOT / "out.png"
    check("PS3 icon extract", local_media.extract_icon("rpcs3", ROOT / "emu/rpcs3/BLUS30443", dest) and dest.read_bytes() == FAKE_PNG)
    dest.unlink()
    check("PSP icon extract", local_media.extract_icon("ppsspp", ROOT / "emu/ppsspp/SomePspGame.iso", dest) and dest.read_bytes() == FAKE_PNG)

    # ── API end-to-end ────────────────────────────────────────────────────────
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/systems/rpcs3/games")
        check("GET games rpcs3 200", r.status_code == 200, r.text)
        games = r.json()
        check("rpcs3 real title in list", games and games[0]["display_name"] == "Demon's Souls", str(games))
        check("rpcs3 filename preserved", games and games[0]["filename"] == "BLUS30443", str(games))

        r = client.get("/api/covers/rpcs3/BLUS30443")
        check("PS3 cover 200 (local ICON0)", r.status_code == 200 and r.content == FAKE_PNG)
        check("PS3 cover cached per-system", (ROOT / "emu/covers/rpcs3/BLUS30443.png").is_file())

        r = client.get("/api/covers/ppsspp/SomePspGame.iso")
        check("PSP cover 200 (embedded ICON0)", r.status_code == 200 and r.content == FAKE_PNG)

        # GC: no local icon → disc-ID lookup on GameTDB (needs network)
        r = client.get("/api/covers/dolphin/Melee.iso")
        check("GC cover via GameTDB id6", r.status_code == 200 and r.headers["content-type"] == "image/png" and len(r.content) > 10000,
              f"status={r.status_code} len={len(r.content)}")

        # PS2: xlenore by serial (needs network)
        r = client.get("/api/covers/pcsx2/MyPs2Game.iso")
        check("PS2 cover via xlenore serial", r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and len(r.content) > 10000,
              f"status={r.status_code} len={len(r.content)}")

        # PS1: xlenore by serial (needs network)
        r = client.get("/api/covers/duckstation/MyPs1Game.bin")
        check("PS1 cover via xlenore serial", r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and len(r.content) > 10000,
              f"status={r.status_code} len={len(r.content)}")

        # Unknown game on a system with nothing local → 404 + .miss marker
        (ROOT / "emu/ppsspp/Unknown_Game_zzz.iso").write_bytes(b"not an iso")
        r = client.get("/api/covers/ppsspp/Unknown_Game_zzz.iso")
        check("unknown game 404", r.status_code == 404)
        check("negative cache written", (ROOT / "emu/covers/ppsspp/Unknown_Game_zzz.miss").is_file())
        # second hit must be served from the negative cache (no network) — just re-check 404
        r = client.get("/api/covers/ppsspp/Unknown_Game_zzz.iso")
        check("negative cache 404 again", r.status_code == 404)

        # refresh=1 clears cache and re-resolves
        r = client.get("/api/covers/rpcs3/BLUS30443?refresh=1")
        check("refresh re-resolves", r.status_code == 200 and r.content == FAKE_PNG)

        # legacy flat cache migration
        legacy = ROOT / "emu/covers/OldGame.png"
        legacy.write_bytes(FAKE_PNG)
        (ROOT / "emu/mgba").mkdir(parents=True, exist_ok=True)

    print()
    if failures:
        print(f"{len(failures)} FAILURES: {failures}")
        sys.exit(1)
    print("All tests passed.")


if __name__ == "__main__":
    main()
