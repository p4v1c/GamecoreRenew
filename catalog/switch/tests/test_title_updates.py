"""Updates and DLC chosen before Ryujinx's first start, from the tickets' names.

Without them the first launch ran Mario Kart 8 in v1.0.0 and it rewrote the
imported v3.0.4 save (measured on the reference box).
"""
import importlib.util
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("test_switch_title_updates",
                                              ROOT / "catalog/switch/title_updates.py")
tu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tu)

MK8, MK8_UPDATE, MK8_DLC = 0x0100152000022000, 0x0100152000022800, 0x0100152000023001


def _nsp(path: Path, names: list[str]) -> Path:
    """A PFS0 header with these file names and no data: all the reader looks at."""
    table, entries = b"", b""
    for name in names:
        entries += struct.pack("<QQII", 0, 0, len(table), 0)
        table += name.encode() + b"\0"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PFS0" + struct.pack("<III", len(names), len(table), 0) + entries + table)
    return path


def _ryujinx(tmp_path, content: Path) -> Path:
    ryujinx = tmp_path / "Ryujinx"
    ryujinx.mkdir()
    (ryujinx / "Config.json").write_text(json.dumps({"autoload_dirs": [str(content)]}))
    return ryujinx


def test_an_update_and_a_dlc_are_written_in_ryujinxs_format(tmp_path):
    content = tmp_path / "Switch DLC & Updates"
    upd = _nsp(content / "MK8 v3.0.4.nsp", ["a.nca", "b.cnmt.nca", f"{MK8_UPDATE:016x}000000000000000b.tik"])
    dlc = _nsp(content / "pack/MK8 BCP.nsp", ["a3e0.nca", "1fa7.cnmt.nca", f"{MK8_DLC:016x}000000000000000b.tik"])
    ryujinx = _ryujinx(tmp_path, content)

    notes = tu.write_missing(ryujinx)

    games = ryujinx / "games" / f"{MK8:016x}"
    assert json.loads((games / "updates.json").read_text()) == {"selected": str(upd), "paths": [str(upd)]}
    assert json.loads((games / "dlc.json").read_text()) == [{"path": str(dlc), "dlc_nca_list": [
        {"path": "/a3e0.nca", "title_id": MK8_DLC, "is_enabled": True}]}]
    assert len(notes) == 2


def test_a_choice_ryujinx_already_made_is_kept(tmp_path):
    content = tmp_path / "content"
    _nsp(content / "u.nsp", [f"{MK8_UPDATE:016x}000000000000000b.tik"])
    ryujinx = _ryujinx(tmp_path, content)
    own = ryujinx / "games" / f"{MK8:016x}" / "updates.json"
    own.parent.mkdir(parents=True)
    own.write_text('{"selected": "", "paths": []}')
    assert tu.write_missing(ryujinx) == []
    assert own.read_text() == '{"selected": "", "paths": []}'


def test_unclear_files_are_left_to_ryujinx(tmp_path):
    content = tmp_path / "content"
    _nsp(content / "two-updates-a.nsp", [f"{MK8_UPDATE:016x}000000000000000b.tik"])
    _nsp(content / "two-updates-b.nsp", [f"{MK8_UPDATE:016x}000000000000000c.tik"])
    _nsp(content / "no-ticket.nsp", ["a.nca"])
    (content / "not-an-nsp.nsp").write_bytes(b"garbage")
    assert tu.write_missing(_ryujinx(tmp_path, content)) == []
