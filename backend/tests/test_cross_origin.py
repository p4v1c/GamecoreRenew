"""The core's cross-origin guard (main._origin_ok and the middleware around it).

The core has no login on loopback and the box runs browsers that can reach it,
so a page in the Firefox kiosk or in Stremio must not be able to POST to it. The
awkward part is that the guard also has to stay out of the way of the two
clients that are allowed: the Electron UI on localhost, and a LAN browser whose
requests arrive through Caddy from an address nobody can predict.

Run under pytest:  pytest backend/tests/test_cross_origin.py
Or directly:       python backend/tests/test_cross_origin.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from starlette.datastructures import Headers

from backend import main
from backend.config import BACKEND_PORT


def ok(**headers):
    return main._origin_ok(Headers({k.replace("_", "-"): v for k, v in headers.items()}))


# ── allowed ──────────────────────────────────────────────────────────────────

def test_a_request_with_no_origin_is_allowed():
    """curl, the addon CLI, the install scripts. A browser always sends Origin
    on a cross-origin write, so nothing we defend against arrives without one."""
    assert ok(host=f"127.0.0.1:{BACKEND_PORT}")


def test_the_electron_ui_is_allowed():
    assert ok(origin=f"http://localhost:{BACKEND_PORT}", host=f"localhost:{BACKEND_PORT}")


def test_localhost_and_127_are_the_same_machine():
    # Electron may say localhost where the socket reports 127.0.0.1.
    assert ok(origin=f"http://localhost:{BACKEND_PORT}", host=f"127.0.0.1:{BACKEND_PORT}")
    assert ok(origin=f"http://127.0.0.1:{BACKEND_PORT}", host=f"localhost:{BACKEND_PORT}")


def test_a_lan_client_through_caddy_is_allowed():
    """/login and /api/auth/* are proxied from https://<any address>:8443.

    The box has no fixed name — the Caddyfile mints certs on demand for whatever
    the client used — so this can only be same-origin, never an allowlist.
    """
    assert ok(origin="https://10.189.1.233:8443", host="10.189.1.233:8443")
    assert ok(origin="https://gamecore.local:8443", host="gamecore.local:8443")
    assert ok(origin="https://100.64.0.3:8443", host="100.64.0.3:8443")


def test_ipv6_loopback_is_allowed():
    assert ok(origin=f"http://[::1]:{BACKEND_PORT}", host=f"[::1]:{BACKEND_PORT}")


# ── refused ──────────────────────────────────────────────────────────────────

def test_a_page_on_another_site_is_refused():
    assert not ok(origin="http://evil.example", host=f"127.0.0.1:{BACKEND_PORT}")
    assert not ok(origin="https://evil.example", host="10.189.1.233:8443")


def test_another_local_app_is_not_the_ui():
    """A blanket loopback pass would let anything else on the box drive the core."""
    assert not ok(origin="http://localhost:9999", host=f"127.0.0.1:{BACKEND_PORT}")


def test_sec_fetch_site_cross_site_is_refused_on_its_own():
    assert not ok(sec_fetch_site="cross-site", host=f"127.0.0.1:{BACKEND_PORT}")


def test_a_lookalike_host_is_refused():
    assert not ok(origin="http://localhost.evil.example", host=f"127.0.0.1:{BACKEND_PORT}")
    assert not ok(origin="http://127.0.0.1.evil.example", host=f"127.0.0.1:{BACKEND_PORT}")


def test_a_malformed_origin_is_refused():
    assert not ok(origin="not-a-url", host=f"127.0.0.1:{BACKEND_PORT}")


# ── through the app ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def test_kill_is_refused_from_a_cross_origin_form(client):
    # The scenario: an auto-submitting <form action=".../api/games/kill"> on a
    # page open in the kiosk browser. It killed the running game, save included.
    r = client.post("/api/games/kill", headers={
        "Origin": "http://evil.example",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    assert r.status_code == 403, r.text


def test_kill_still_works_from_the_ui(client):
    r = client.post("/api/games/kill", headers={"Origin": f"http://localhost:{BACKEND_PORT}",
                                                "Host": f"localhost:{BACKEND_PORT}"})
    assert r.status_code != 403, r.text


def test_reads_are_never_blocked(client):
    r = client.get("/api/systems", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200


def test_websocket_refuses_a_cross_origin_page(client):
    # WebSocket handshakes are GETs and ignore CORS entirely: without this check
    # any page could open ws://127.0.0.1:8765/ws and read every UI event.
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises((WebSocketDisconnect, Exception)):
        with client.websocket_connect("/ws", headers={"Origin": "http://evil.example"}):
            pass


def test_websocket_accepts_the_ui(client):
    # Host as well as Origin: TestClient defaults Host to "testserver", where
    # Electron sends the address it actually loaded.
    with client.websocket_connect("/ws", headers={
        "Origin": f"http://localhost:{BACKEND_PORT}",
        "Host": f"localhost:{BACKEND_PORT}",
    }):
        pass


def test_websocket_accepts_a_client_with_no_origin(client):
    """A native client (and anything that is not a browser) has no Origin."""
    with client.websocket_connect("/ws"):
        pass


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    unit = [v for k, v in sorted(globals().items())
            if k.startswith("test_") and "client" not in v.__code__.co_varnames]
    for fn in unit:
        fn()
        print(f"[OK ] {fn.__name__}")

    with TestClient(main.app) as c:
        for fn in (test_kill_is_refused_from_a_cross_origin_form,
                   test_kill_still_works_from_the_ui,
                   test_reads_are_never_blocked,
                   test_websocket_refuses_a_cross_origin_page,
                   test_websocket_accepts_the_ui,
                   test_websocket_accepts_a_client_with_no_origin):
            fn(c)
            print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")
