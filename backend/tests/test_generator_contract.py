"""Every generator must expose what its declared strategy makes the dispatcher call.

This is the test that was missing. The refactor moved melonDS's `extract` and
`replace` out of the central `_SNAP_EMUS` table and into the pack, and simply
forgot to re-export them. Nothing caught it:

  · the characterisation suite replays the SYNTHESIS path, and melonDS only
    reaches the snapshot path when a snapshot for that pad already exists;
  · test_configgen_snapshots.py loads azahar, mgba, cemu and gopher64 by name
    and never had melonds in the list;
  · the pack schema validates data, and a missing function is not data.

So it shipped, and on the box every pad connect raised

    AttributeError: module 'gamecore_generator_melonds' has no attribute 'extract'

which apply_profile catches and logs — melonDS was silently left unconfigured,
and "Scan mapping" skipped it outright (`hasattr(module, "extract")`).

The fix for the instance is two lines in the pack. The fix for the CLASS is
here: derive what to check from `controllers.strategy` in pack.json, so a pack
added later is covered the moment it declares a strategy, without anyone
remembering to add it to a list.
"""
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CATALOG = ROOT / "catalog"

# strategy → names apply_profile / scan_mapping read off the module object.
# Keep this table next to the dispatcher's behaviour, not next to a pack list.
REQUIRED = {
    "snapshot-restore":     ("generate", "extract", "replace"),
    "snapshot-or-synth":    ("generate", "extract", "replace"),
    "rewrite-player-block": ("generate",),
    "rewrite-device-line":  ("generate",),
    "sdl-index-clone":      ("generate",),
    "guid-rebind":          ("generate",),
}


def _packs():
    out = []
    for pack_dir in sorted(CATALOG.iterdir()):
        if pack_dir.name.startswith("_") or not (pack_dir / "pack.json").is_file():
            continue
        meta = json.loads((pack_dir / "pack.json").read_text())
        strategy = (meta.get("controllers") or {}).get("strategy", "none")
        if strategy == "none" or not (pack_dir / "generator.py").is_file():
            continue
        out.append((pack_dir.name, strategy, meta))
    return out


PACKS = _packs()
assert PACKS, "no profilable pack found — the catalogue is not where this test thinks"


def _load(pack_id):
    spec = importlib.util.spec_from_file_location(
        f"contract_{pack_id}", CATALOG / pack_id / "generator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("pack_id,strategy,_meta", PACKS,
                         ids=[p[0] for p in PACKS])
def test_generator_exposes_its_strategy_surface(pack_id, strategy, _meta):
    module = _load(pack_id)
    assert strategy in REQUIRED, (
        f"{pack_id} declares strategy '{strategy}', which the dispatcher does "
        f"not implement — add it to REQUIRED and to apply_profile together")
    for name in REQUIRED[strategy]:
        fn = getattr(module, name, None)
        assert fn is not None, (
            f"catalog/{pack_id}/generator.py has no '{name}', but its strategy "
            f"'{strategy}' makes the dispatcher call it — this is the melonDS bug")
        assert callable(fn), f"catalog/{pack_id}/generator.py: '{name}' is not callable"


@pytest.mark.parametrize("pack_id,strategy,_meta",
                         [p for p in PACKS if p[1].startswith("snapshot")],
                         ids=[p[0] for p in PACKS if p[1].startswith("snapshot")])
def test_snapshot_helpers_take_the_arity_restore_uses(pack_id, strategy, _meta):
    """snapshots.restore calls extract(text) and replace(text, block); capture
    calls extract(text). A helper with the wrong arity fails at runtime only,
    inside the try/except that turns it into a log line."""
    module = _load(pack_id)
    assert len(inspect.signature(module.extract).parameters) == 1, \
        f"{pack_id}.extract must take exactly (text)"
    assert len(inspect.signature(module.replace).parameters) == 2, \
        f"{pack_id}.replace must take exactly (text, block)"


def _packs_with_a_release():
    """The packs that ship an inverse. Selected here rather than skipped inside
    the test: a skip reads as "not checked" in the run summary, and this is a
    pack having nothing to un-write, which is a fact about the pack."""
    return [p for p in PACKS if hasattr(_load(p[0]), "release")]


RELEASING = _packs_with_a_release()
assert RELEASING, ("no generator exposes release() — release_profile would be "
                   "a no-op and the stale slots are back")


@pytest.mark.parametrize("pack_id,strategy,_meta", RELEASING,
                         ids=[p[0] for p in RELEASING])
def test_release_takes_the_arity_the_dispatcher_calls(pack_id, strategy, _meta):
    """A pack that ships a `release()` must take (player_index, opts, occupied).

    `occupied` was added when the multitap proved a slot index cannot decide
    everything a release has to decide: whether the PS1/PS2 tap is still needed
    depends on the rest of the roster, not on the slot being freed. A generator
    left on the old two-argument form raises TypeError inside release_profile's
    try/except, which turns it into one log line and an un-freed slot — the
    same shape as the melonDS bug this file exists for.
    """
    fn = _load(pack_id).release
    params = list(inspect.signature(fn).parameters)
    assert params[:3] == ["player_index", "opts", "occupied"], (
        f"catalog/{pack_id}/generator.py: release{inspect.signature(fn)} — "
        f"release_profile calls release(player_index, opts, occupied)")


@pytest.mark.parametrize("pack_id,strategy,meta",
                         [p for p in PACKS if p[1].startswith("snapshot")],
                         ids=[p[0] for p in PACKS if p[1].startswith("snapshot")])
def test_extract_and_replace_round_trip_on_the_pack_seed(pack_id, strategy, meta):
    """The invariant snapshots.restore leans on: after writing a block back,
    reading it out again yields the same block. That is how restore decides
    "already applied" and skips a pointless rewrite — if it does not hold, the
    config is rewritten on every single connect.

    The fixture is the pack's own seed, so this exercises the real file format
    rather than a hand-made string that could drift from it.
    """
    target = (meta.get("controllers") or {}).get("target")
    seed = CATALOG / pack_id / "seed" / target if target else None
    if seed is None or not seed.is_file():
        pytest.skip(f"{pack_id} ships no seed at seed/{target} — nothing to read")

    module = _load(pack_id)
    text = seed.read_text()
    block = module.extract(text)
    if not block.strip():
        pytest.skip(f"{pack_id}: the seed holds no controller block to round-trip")

    again = module.extract(module.replace(text, block))
    assert again.strip() == block.strip(), (
        f"{pack_id}: extract(replace(text, block)) != block — restore() would "
        f"rewrite the config on every connect instead of detecting it is applied")
