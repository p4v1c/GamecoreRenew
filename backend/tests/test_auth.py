"""Unit tests for the LAN login helpers (services.auth).

Mostly about the anti-bruteforce state: the per-IP block has to bite, and the
global circuit breaker must not turn into a denial of service anyone on the LAN
can trigger against the owner.

Run under pytest:  pytest backend/tests/test_auth.py
Or directly:       python backend/tests/test_auth.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.services import auth


@pytest.fixture(autouse=True)
def clean_auth_state(tmp_path, monkeypatch):
    """Fresh failure counters, and credentials written somewhere disposable."""
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / "auth_secret")
    auth._fails.clear()
    auth._global.update({"fails": 0, "until": 0.0})
    yield
    auth._fails.clear()
    auth._global.update({"fails": 0, "until": 0.0})


def test_global_breaker_does_not_lock_out_innocent_ip():
    """25 failures from anywhere used to 429 a caller with the right password."""
    auth.set_password("correcthorse")
    for i in range(30):
        auth.register_failure(f"10.0.0.{i}")
    assert auth._global["until"] > time.time(), "the breaker really did trip"
    assert auth.blocked_for("192.168.1.77") == 0, "an IP never seen → not blocked"


def test_global_breaker_still_applies_to_an_ip_that_has_failed():
    """It has to keep costing something, or it is not a breaker at all."""
    for i in range(30):
        auth.register_failure(f"10.0.0.{i}")
    assert auth.blocked_for("10.0.0.0") > 0


def test_repeated_failures_block_the_offending_ip():
    ip = "10.1.2.3"
    for _ in range(auth._MAX_FREE_FAILS - 1):
        auth.register_failure(ip)
    assert auth.blocked_for(ip) == 0, "les premiers essais sont gratuits"

    auth.register_failure(ip)
    assert auth.blocked_for(ip) > 0, "at the threshold, the IP is blocked"


def test_a_success_clears_the_block():
    ip = "10.1.2.4"
    for _ in range(auth._MAX_FREE_FAILS + 2):
        auth.register_failure(ip)
    assert auth.blocked_for(ip) > 0

    auth.register_success(ip)
    assert auth.blocked_for(ip) == 0, "one success forgets the IP's history"


def test_a_typo_does_not_pin_a_client_to_the_global_breaker_forever():
    # One wrong password, then the spray trips the breaker: the client waits,
    # but the wait is bounded and a success takes them out of _fails entirely.
    auth.register_failure("192.168.1.77")
    for i in range(30):
        auth.register_failure(f"10.0.0.{i}")
    assert auth.blocked_for("192.168.1.77") <= 61

    auth.register_success("192.168.1.77")
    assert auth.blocked_for("192.168.1.77") == 0


# ── credentials on disk ──────────────────────────────────────────────────────

def test_password_round_trip():
    auth.set_password("correcthorse")
    assert auth.verify_password("correcthorse")
    assert not auth.verify_password("batterystaple")


def test_a_corrupt_auth_file_does_not_take_the_whole_lan_down():
    """_auth() must swallow anything on that path — every LAN request calls it.

    A non-UTF-8 auth.json raised UnicodeDecodeError straight out of read_text(),
    which 500'd every request behind Caddy, /login included: no way back in
    short of SSH.
    """
    auth.set_password("correcthorse")
    auth.AUTH_FILE.write_bytes(b"\xff\xfe\x00not utf-8 at all")
    assert auth._auth() is None
    assert not auth.verify_password("correcthorse")
    assert auth.make_cookie() is None
    assert not auth.check_cookie("1.1.deadbeef")


if __name__ == "__main__":
    import tempfile

    for fn in (
        test_global_breaker_does_not_lock_out_innocent_ip,
        test_global_breaker_still_applies_to_an_ip_that_has_failed,
        test_repeated_failures_block_the_offending_ip,
        test_a_success_clears_the_block,
        test_a_typo_does_not_pin_a_client_to_the_global_breaker_forever,
        test_password_round_trip,
        test_a_corrupt_auth_file_does_not_take_the_whole_lan_down,
    ):
        saved = (auth.AUTH_FILE, auth.SECRET_FILE)
        with tempfile.TemporaryDirectory() as tmp:
            auth.AUTH_FILE = Path(tmp) / "auth.json"
            auth.SECRET_FILE = Path(tmp) / "auth_secret"
            auth._fails.clear()
            auth._global.update({"fails": 0, "until": 0.0})
            try:
                fn()
            finally:
                auth.AUTH_FILE, auth.SECRET_FILE = saved
        print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")
