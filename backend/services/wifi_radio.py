"""The Wi-Fi radio switch: `nmcli radio wifi`, read and set.

The backend is a system unit with no login session of its own. polkit grants
`org.freedesktop.NetworkManager.enable-disable-wifi` to it only because its user
also owns the box's active seat session (autologin); without one, nmcli answers
"Not authorized" and that sentence is what the player is shown.
"""
from __future__ import annotations

import asyncio
import logging

from .errors import ServiceError

log = logging.getLogger(__name__)

# nmcli answers from NetworkManager's state, so anything slower is a hung
# daemon; the process is killed rather than left holding a D-Bus call.
NMCLI_SECS = 10.0


async def _nmcli(*args: str) -> tuple[int, str]:
    """(returncode, stdout + stderr). Raises TimeoutError after killing nmcli."""
    proc = await asyncio.create_subprocess_exec(
        "nmcli", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), NMCLI_SECS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, (out + err).decode(errors="replace").strip()


def parse_radio(text: str) -> bool | None:
    """`WIFI-HW:WIFI` from `nmcli -t -f WIFI-HW,WIFI radio` → on, off, or None.

    None means there is no radio to switch (no Wi-Fi hardware, or an answer
    this cannot read), so the UI draws no switch. A hardware or BIOS block
    reads as off: turning it on from here cannot change it.
    """
    hw, sep, sw = text.strip().partition(":")
    if not sep or hw not in ("enabled", "disabled"):
        return None
    return hw == "enabled" and sw == "enabled"


async def radio_enabled() -> bool | None:
    """Whether the Wi-Fi radio is on. None when it cannot be told."""
    try:
        code, out = await _nmcli("-t", "-f", "WIFI-HW,WIFI", "radio")
    except asyncio.TimeoutError:
        log.warning("wifi: radio state did not answer in %ss", NMCLI_SECS)
        return None
    if code != 0:
        log.warning("wifi: radio state unreadable: %s", out)
        return None
    return parse_radio(out)


async def set_radio(enabled: bool) -> dict:
    """Turn the radio on or off. Returns `{"enabled": <state read back>}`."""
    word = "on" if enabled else "off"
    try:
        code, out = await _nmcli("radio", "wifi", word)
    except asyncio.TimeoutError:
        log.warning("wifi: radio %s timed out after %ss", word, NMCLI_SECS)
        raise ServiceError(504, "NetworkManager did not answer. Try again.") from None
    if code != 0:
        log.warning("wifi: radio %s failed: %s", word, out)
        raise ServiceError(502, out or f"Could not turn Wi-Fi {word}.")
    state = await radio_enabled()
    if enabled and state is False:
        # nmcli accepts "on" under an rfkill hard block and nothing changes.
        raise ServiceError(409, "Wi-Fi is blocked by a hardware switch or the BIOS.")
    log.info("wifi: radio turned %s", word)
    return {"enabled": state}
