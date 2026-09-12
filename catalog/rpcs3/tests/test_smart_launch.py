from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import urllib.error

import pytest

HERE = Path(__file__).resolve().parent
MOD_PATH = HERE.parent / "files" / "rpcs3-smart-sync.py"
spec = importlib.util.spec_from_file_location("rpcs3_smart", MOD_PATH)
smart = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(smart)


def config_payload(*serials: str) -> bytes:
    return json.dumps({
        "return_code": 0,
        "games": {s: {"config": "Video:\n  Write Color Buffers: true\n"} for s in serials},
    }).encode()


def patch_response(content: str, version: str = "1.2", code: int = 0) -> bytes:
    return json.dumps({
        "return_code": code,
        "version": version,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "patch": content,
    }).encode()


def test_policy_defaults():
    p = smart.load_policy(None)
    assert p["profile"] == "recommended-original"
    assert p["syncHours"] == 6
    assert p["autoPatch"] == {"mode":"exact-whitelist","approved":[]}


def test_policy_bad_json_fails_safe(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{bad")
    assert smart.load_policy(p)["autoPatch"]["approved"] == []


def test_policy_bad_autopatch_fails_closed(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({
        "version":1,
        "syncHours":-20,
        "networkTimeoutSeconds":500,
        "autoPatch":{"mode":"guess-by-name","approved":["*"]},
    }))
    got = smart.load_policy(p)
    assert got["syncHours"] == 1
    assert got["networkTimeoutSeconds"] == 30
    assert got["autoPatch"] == {"mode":"exact-whitelist","approved":[]}


@pytest.mark.parametrize("appid", ["net.rpcs3.RPCS3","org.example.App","a"])
def test_valid_appids(appid):
    assert smart.validate_app_id(appid) == appid


@pytest.mark.parametrize("appid", ["","../evil","a/b","a b","x;touch nope","@APPID@"])
def test_bad_appids(appid):
    with pytest.raises(ValueError):
        smart.validate_app_id(appid)


def test_runtime_prefers_existing_native_binary(tmp_path):
    home = tmp_path / "home"
    gc = tmp_path / "GameCore"
    (gc / "lib").mkdir(parents=True)
    (gc / "lib/rpcs3").write_text("native")
    kind, root = smart.runtime_root(home, gc, "net.rpcs3.RPCS3")
    assert kind == "native"
    assert root == home / ".config/rpcs3"


def test_runtime_uses_flatpak_when_native_is_absent(tmp_path):
    home = tmp_path / "home"
    gc = tmp_path / "GameCore"
    gc.mkdir()
    kind, root = smart.runtime_root(home, gc, "net.rpcs3.RPCS3")
    assert kind == "flatpak"
    assert root == home / ".var/app/net.rpcs3.RPCS3/config/rpcs3"


def test_non_https_redirect_is_refused():
    h = smart.HTTPSOnlyRedirectHandler()
    with pytest.raises(urllib.error.HTTPError, match="non-HTTPS"):
        h.redirect_request(None, None, 302, "Found", {}, "http://example.invalid/db")


def test_https_redirect_is_allowed_to_default_handler(monkeypatch):
    # We only own the downgrade check. The superclass still decides ordinary
    # redirect mechanics, so reaching it (rather than our HTTPError) is enough.
    h = smart.HTTPSOnlyRedirectHandler()
    monkeypatch.setattr(
        smart.urllib.request.HTTPRedirectHandler,
        "redirect_request",
        lambda self, req, fp, code, msg, headers, newurl: "ok",
    )
    assert h.redirect_request(None, None, 302, "Found", {}, "https://example.invalid/db") == "ok"


def test_config_db_validation():
    assert smart.validate_config_database(config_payload("BLES00932"))["usable"] == 1


@pytest.mark.parametrize("payload", [
    b"x", json.dumps([]).encode(),
    json.dumps({"return_code":-1,"games":{}}).encode(),
    json.dumps({"return_code":0,"games":{}}).encode(),
    json.dumps({"return_code":0,"games":{"BLES00000":{"config":3}}}).encode(),
])
def test_bad_config_db_rejected(payload):
    with pytest.raises(ValueError):
        smart.validate_config_database(payload)


def test_patch_envelope_sha256_integrity_check():
    y = 'Version: 1.2\nPPU-a:\n  "Fix": {}\n'
    assert smart.decode_patch_database_response(patch_response(y), "1.2") == y.encode()


def test_patch_return_code_one_is_current():
    assert smart.decode_patch_database_response(json.dumps({"return_code":1}).encode(), "1.2") is None


def test_patch_bad_checksum_rejected():
    y = 'Version: 1.2\nPPU-a:\n  "Fix": {}\n'
    d = json.loads(patch_response(y)); d["sha256"] = "0"*64
    with pytest.raises(ValueError, match="checksum"):
        smart.decode_patch_database_response(json.dumps(d).encode(), "1.2")


def test_patch_wrong_version_rejected():
    y = 'Version: 9.9\nPPU-a:\n  "Fix": {}\n'
    with pytest.raises(ValueError, match="does not match"):
        smart.decode_patch_database_response(patch_response(y, "9.9"), "1.2")


def test_atomic_write(tmp_path):
    p = tmp_path / "a/b"
    smart._atomic_write(p,b"1"); smart._atomic_write(p,b"2")
    assert p.read_bytes() == b"2"


def test_config_sync_exact_path(tmp_path, monkeypatch):
    monkeypatch.setattr(smart, "_fetch", lambda *a, **k: config_payload("BLES00932"))
    assert smart.sync_config_database(tmp_path, smart.load_policy(None), force=True) == "updated:1"
    assert (tmp_path / "GuiConfigs/config_database.dat").is_file()


def test_patch_sync_writes_yaml_not_json_envelope(tmp_path, monkeypatch):
    y = 'Version: 1.2\nPPU-a:\n  "Fix": {}\n'
    monkeypatch.setattr(smart, "_fetch", lambda *a, **k: patch_response(y))
    assert smart.sync_patch_database(tmp_path, smart.load_policy(None), force=True) == "updated"
    assert (tmp_path / "patches/patch.yml").read_text() == y


def test_fresh_cache_skips_network(tmp_path, monkeypatch):
    db = tmp_path / "GuiConfigs/config_database.dat"; db.parent.mkdir(); db.write_bytes(b"x")
    pp = tmp_path / "patches/patch.yml"; pp.parent.mkdir(); pp.write_bytes(b"x")
    monkeypatch.setattr(smart, "_fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert smart.safe_sync(tmp_path, smart.load_policy(None), offline=False, force=False) == {
        "configDatabase":"fresh","patchDatabase":"fresh"
    }


def test_network_failure_preserves_old_files(tmp_path, monkeypatch):
    db = tmp_path / "GuiConfigs/config_database.dat"; db.parent.mkdir(); db.write_bytes(b"old")
    pp = tmp_path / "patches/patch.yml"; pp.parent.mkdir(); pp.write_bytes(b"oldp")
    os.utime(db,(1,1)); os.utime(pp,(1,1))
    monkeypatch.setattr(smart, "_fetch", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    out = smart.safe_sync(tmp_path, smart.load_policy(None), offline=False, force=True)
    assert out["configDatabase"].startswith("error:")
    assert out["patchDatabase"].startswith("error:")
    assert db.read_bytes() == b"old" and pp.read_bytes() == b"oldp"


def test_offline_zero_network(tmp_path, monkeypatch):
    monkeypatch.setattr(smart, "_fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert smart.safe_sync(tmp_path, smart.load_policy(None), offline=True, force=True) == {
        "configDatabase":"offline","patchDatabase":"offline"
    }


def test_empty_whitelist_enables_nothing():
    assert smart.auto_patch_status(smart.load_policy(None)) == "none-approved"


def test_nonempty_whitelist_fails_closed():
    p = smart.load_policy(None); p["autoPatch"]["approved"] = [{"x":1}]
    assert smart.auto_patch_status(p) == "approvals-present-but-writer-disabled"


@pytest.mark.parametrize("native", [False, True])
def test_main_writes_selected_runtime_state_offline(tmp_path, native):
    home = tmp_path / "home"
    gc = tmp_path / "gc"; gc.mkdir()
    if native:
        (gc / "lib").mkdir(); (gc / "lib/rpcs3").write_text("x")
    rc = smart.main([
        "--gamecore-path", str(gc), "--home", str(home), "--offline"
    ])
    assert rc == 0
    state = json.loads((home / ".local/share/gamecore/rpcs3-smart/state.json").read_text())
    assert state["runtime"] == ("native" if native else "flatpak")
    assert state["configDatabase"] == "offline"


def test_main_rejects_bad_appid_before_writes(tmp_path):
    home = tmp_path / "home"; gc = tmp_path / "gc"; gc.mkdir()
    assert smart.main([
        "--gamecore-path",str(gc),"--home",str(home),"--app-id","../evil","--offline"
    ]) == 2
    assert not (home / ".local/share/gamecore/rpcs3-smart/state.json").exists()
