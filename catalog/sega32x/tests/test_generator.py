from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tested_sega32x", HERE / "generator.py")
g = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(g)

def test_pack_identity_and_ports():
    assert g.EMU_ID == 'sega32x'
    assert g.PORTS == 2
    assert 1 <= g.PORTS <= 4

def test_shared_contract_is_delegated():
    assert g.extract.__module__ == g.__name__
    assert callable(g.generate) and callable(g.release) and callable(g.replace)
