"""window_focus._window_pid: the X server's word over the window's own claim.

Measured on the box: inside a Flatpak sandbox the app is process 2, and it
writes that into `_NET_WM_PID`; only the X server knows its host pid.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services import window_focus as wf

pytest.importorskip("Xlib")

PID_MASK = wf.xres.LocalClientPIDMask


class Disp:
    def __init__(self, xres_pid=None, fail=False):
        self.xres_pid, self.fail = xres_pid, fail

    def intern_atom(self, name):
        return name

    def res_query_client_ids(self, specs):
        if self.fail:
            raise AttributeError("no X-Resource")
        ids = [] if self.xres_pid is None else [
            SimpleNamespace(spec=SimpleNamespace(client=specs[0]["client"], mask=PID_MASK),
                            value=[self.xres_pid])]
        return SimpleNamespace(ids=ids)


class Win:
    id = 0x1800007

    def __init__(self, net_wm_pid):
        self.net_wm_pid = net_wm_pid

    def get_full_property(self, atom, kind):
        return SimpleNamespace(value=[self.net_wm_pid]) if self.net_wm_pid else None


def test_a_flatpak_window_is_found_by_its_host_pid_not_its_sandbox_pid():
    # Ryujinx in its sandbox: _NET_WM_PID 2, the host process 51234.
    assert wf._window_pid(Disp(xres_pid=51234), Win(net_wm_pid=2)) == 51234


def test_without_x_resource_the_window_property_still_answers():
    assert wf._window_pid(Disp(fail=True), Win(net_wm_pid=4321)) == 4321
    assert wf._window_pid(Disp(xres_pid=None), Win(net_wm_pid=4321)) == 4321


def test_nothing_known_is_zero():
    assert wf._window_pid(Disp(fail=True), Win(net_wm_pid=0)) == 0
