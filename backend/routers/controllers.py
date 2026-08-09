"""Controller mapping — the "Scan mapping" action, and the mapping wizard.

Two mechanisms, deliberately distinct, because they answer two different
questions and confusing them is how a box ends up with a mapping it cannot
explain.

**Scan mapping** (`/controllers/scan-mapping`) is for configs the owner has
ALREADY made by hand. Four emulators (3DS/azahar, DS/melonDS, GBA/mgba,
Wii U/Cemu) bind a pad by a device GUID plus raw button indices; the owner
configures the pad once inside each emulator's own input UI, then presses this,
and their work is remembered per controller and restored on every future
connect.

Ryujinx used to be listed there and never was: it has no snapshot adapter, and
it does not need one. Its GUID is read live from SDL2 and converted exactly
(controller_profiles.ryu_guid_from_sdl2), and its bindings are role names that
carry from one controller to the next.

An emulator whose current config plainly describes a DIFFERENT controller is
refused rather than filed under the connected one, and comes back in
`refused` — the box already holds a Cemu snapshot named for an Xbox pad that
contains a DualShock 4's config, saved when this returned a flat "ok".

That same snapshot is why DELETE exists. `restore()` now refuses to apply a
snapshot whose GUID names another pad, and a refusal with no way to act on it
is only a nicer dead end: the file sits in a directory no one can reach from a
sofa. Scan and forget are the two halves of one gesture, so they live on one
path and differ by verb.

**The wizard** (`/controllers/mapping/*`) is for the case Scan mapping cannot
help with at all: a pad SDL does not know. There is no hand-made config to
remember, because the owner cannot make one — the emulator's input UI will not
bind a device its SDL never enumerated. So the pad is mapped HERE, once,
button by button, and the result is written as an SDL mapping line that every
SDL-based emulator on the box reads at startup. One gesture, thirteen systems.

The two meet in `snapshots.py`: a pad the wizard has just described is a pad
whose raw indices are finally known, which is what lets the GUID-bound
emulators be written from a capture instead of demanding a manual pass.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..services import controller_capture, controller_profiles, usb_devices
from ..services.configgen import mapping_db

router = APIRouter(tags=["controllers"])


@router.get("/controllers/devices")
def usb_peripherals():
    """The declared peripherals that are not SDL pads, present or absent.

    The player slots above this list answer "who is player 2". They cannot
    answer "is the GameCube adapter plugged in", because an adapter Dolphin
    drives over raw libusb has no evdev node and therefore never enters the
    roster at all. Without this list the two failure modes — not plugged in,
    and plugged in but not seen — look identical from a sofa, and only one of
    them is fixed by touching the cable.
    """
    return {"ok": True, "devices": usb_devices.report()}


@router.post("/controllers/scan-mapping")
def scan_mapping():
    return controller_profiles.scan_mapping()


@router.delete("/controllers/scan-mapping")
def forget_mapping():
    return controller_profiles.forget_mapping()


# ── the wizard ───────────────────────────────────────────────────────────────

class CommitBody(BaseModel):
    """What the wizard collected.

    `bindings` is SDL field name → SDL token (`a` → `b0`, `lefttrigger` →
    `+a4`). The BACKEND does not track which step the UI is on: skipping a
    button, going back and re-recording one are things the player does with the
    pad in their hands, and a session that had to stay in step with them would
    turn every dropped WebSocket frame into a wrong binding. The UI sends what
    it ended up with.
    """
    bindings: dict[str, str] = Field(default_factory=dict)
    name: str = ""


@router.post("/controllers/mapping/start")
def mapping_start():
    return controller_capture.start()


@router.post("/controllers/mapping/commit")
def mapping_commit(body: CommitBody):
    return controller_capture.commit(body.bindings, body.name)


@router.post("/controllers/mapping/cancel")
def mapping_cancel():
    return {"ok": True, "closed": controller_capture.cancel()}


@router.get("/controllers/mapping/saved")
def mapping_saved():
    """The mappings captured on this box, for the settings screen.

    Read straight from the user file rather than from a cache: it is the thing
    that survives an OTA, so it is also the only thing that can be trusted to
    describe what the box will still know tomorrow.
    """
    saved = []
    for line in mapping_db.read_user():
        parsed = mapping_db.parse(line)
        if parsed:
            guid, name, _bindings = parsed
            saved.append({"guid": guid, "name": name, "line": line})
    return {"ok": True, "saved": saved, "file": str(mapping_db.USER_DB)}


class ForgetBody(BaseModel):
    guid: str


@router.post("/controllers/mapping/forget")
def mapping_forget(body: ForgetBody):
    """Drop a captured mapping. A POST with a body rather than a DELETE with a
    path parameter, so the cross-origin guard in main.py covers it the same way
    it covers every other write that matters."""
    return {"ok": True, "forgotten": mapping_db.remove(body.guid)}


@router.websocket("/ws/controllers/mapping")
async def mapping_events(websocket: WebSocket):
    """Push every press on the pad being mapped, as an SDL token.

    The origin check is the same one `main.py` applies to `/ws`, repeated
    rather than shared because a WebSocket does not pass through the HTTP
    middleware — a page we do not serve must not be able to watch the owner's
    controller, which is a keylogger with extra steps.
    """
    from ..main import _origin_ok

    if not _origin_ok(websocket.headers):
        await websocket.close(code=1008)          # policy violation
        return

    session = controller_capture.current()
    if session is None:
        await websocket.accept()
        await websocket.send_json({"event": "error",
                                   "data": {"error": "no capture session is open"}})
        await websocket.close()
        return

    await websocket.accept()
    await websocket.send_json({"event": "ready",
                               "data": {"session": session.id,
                                        "nodes": session.nodes}})
    try:
        async for event in controller_capture.events(session):
            await websocket.send_json({"event": "input", "data": event})
    except WebSocketDisconnect:
        pass
    except Exception:
        # Never propagate: a pad unplugged mid-wizard closes its nodes, and the
        # player must get a socket that ends rather than a backend traceback.
        try:
            await websocket.send_json({"event": "ended", "data": {}})
        except Exception:
            pass
