"""RPCS3 controller generator."""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("gen_rpcs3", ROOT / "catalog/rpcs3/generator.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def test_rpcs3_not_installed_is_not_reported_unconfigured(tmp_path):
    """No input config means RPCS3 is not set up on this box. That is not a
    pad the owner has to fix, whatever SDL3 can say about its name."""
    pad = types.SimpleNamespace(vendor="1209", product="0002",
                                evdev_name="libvirtualhid Keyboard",
                                name=types.SimpleNamespace(source="evdev"))
    assert gen.generate(2, pad, {"target": tmp_path / "Default.yml"}) is None
