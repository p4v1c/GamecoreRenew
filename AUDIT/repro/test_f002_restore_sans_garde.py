"""F-002 — `block_disagrees` garde `capture()` mais pas `restore()`.

Famille : écriture sans inverse.

`snapshots.capture()` refuse d'enregistrer un bloc dont le GUID nomme une autre
manette. Cette garde a été ajoutée après un incident que le docstring de
`snapshots.py` raconte lui-même :

    "the box ended up with cemu/045e_02fd.snap byte-identical to
     cemu/054c_09cc.snap — both the DualShock 4's config, because 'Scan mapping'
     was pressed with the Xbox pad connected while the file still held the DS4."

La garde empêche d'en créer un NOUVEAU. Elle ne fait rien contre celui qui est
déjà sur le disque : `restore()` ne l'appelle jamais. Et il n'existe aucun geste
pour supprimer un snapshot — `backend/routers/controllers.py` n'expose que
`POST /controllers/scan-mapping`, il n'y a pas de DELETE.

Donc un snapshot empoisonné est réappliqué à chaque connexion, pour toujours,
et écrase le mapping que le propriétaire refait à la main dans l'émulateur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.configgen import snapshots                    # noqa: E402
from backend.services.configgen.controllers import vidpid_of        # noqa: E402

CATALOG = ROOT / "catalog"


def _snapshot_packs():
    """Les packs dont la stratégie déclarée passe par un snapshot.

    Dérivé du catalogue : un pack qui adopte la stratégie demain est couvert
    sans qu'on touche à ce fichier.
    """
    out = []
    for pack_dir in sorted(CATALOG.iterdir()):
        meta_path = pack_dir / "pack.json"
        if pack_dir.name.startswith("_") or not meta_path.is_file():
            continue
        ctl = (json.loads(meta_path.read_text()).get("controllers") or {})
        if not str(ctl.get("strategy", "")).startswith("snapshot"):
            continue
        target = ctl.get("target")
        seed = pack_dir / "seed" / target if target else None
        if seed is None or not seed.is_file():
            continue
        out.append((pack_dir.name, seed))
    return out


SNAPSHOT_PACKS = _snapshot_packs()
assert SNAPSHOT_PACKS, "aucun pack snapshot livrant un seed — le catalogue a bougé"


def _load(pack_id):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"audit_{pack_id}", CATALOG / pack_id / "generator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Deux manettes réelles du harnais de caractérisation. Le GUID est celui que le
# SDL2 embarqué rapporte pour la DualShock 4 ; on l'enregistre sous le
# vendor:product de la Xbox — exactement l'accident décrit dans snapshots.py.
DS4_GUID = "03008fe54c050000cc09000000006800"
XBOX_VENDOR, XBOX_PRODUCT = "045e", "02fd"


def test_le_guid_du_ds4_ne_designe_pas_la_xbox():
    """Garde-fou de la fixture elle-même : si ce GUID décodait vers la Xbox,
    les deux tests suivants ne prouveraient rien."""
    assert vidpid_of(DS4_GUID) == ("054c", "09cc")


@pytest.mark.parametrize("pack_id,seed", SNAPSHOT_PACKS,
                         ids=[p[0] for p in SNAPSHOT_PACKS])
def test_capture_refuse_un_bloc_qui_nomme_une_autre_manette(tmp_path, pack_id, seed):
    """Garde-fou : la protection existe bien côté capture.

    Sans ce test, celui d'après pourrait être vert pour la mauvaise raison.
    """
    module = _load(pack_id)
    cfg = tmp_path / Path(seed).name
    # Le seed ne porte volontairement aucun GUID (check-catalog l'impose) : on
    # en injecte un pour simuler la config que le propriétaire vient de faire.
    cfg.write_text(seed.read_text() + f"\n# guid:{DS4_GUID}\n")

    if snapshots.block_disagrees(module.extract(cfg.read_text()),
                                 XBOX_VENDOR, XBOX_PRODUCT) is None:
        pytest.skip(f"{pack_id}: extract() ne remonte pas le GUID injecté — "
                    f"ce pack ne peut pas porter la démonstration")

    with pytest.raises(snapshots.Refused):
        snapshots.capture(tmp_path / "snaps", pack_id, cfg, module.extract,
                          XBOX_VENDOR, XBOX_PRODUCT)


@pytest.mark.parametrize("pack_id,seed", SNAPSHOT_PACKS,
                         ids=[p[0] for p in SNAPSHOT_PACKS])
def test_restore_refuse_un_snapshot_qui_nomme_une_autre_manette(tmp_path, pack_id, seed):
    """LE CONSTAT — rouge sur main.

    Le snapshot empoisonné est déjà sur le disque (c'est le cas décrit dans le
    docstring de snapshots.py, et aucune API ne permet de l'effacer).
    `restore()` l'applique sans jamais appeler `block_disagrees`, écrasant le
    mapping que le propriétaire vient de refaire pour la Xbox.
    """
    module = _load(pack_id)
    snap_dir = tmp_path / "snaps"

    poisoned = module.extract(seed.read_text() + f"\n# guid:{DS4_GUID}\n")
    if snapshots.block_disagrees(poisoned, XBOX_VENDOR, XBOX_PRODUCT) is None:
        pytest.skip(f"{pack_id}: extract() ne remonte pas le GUID injecté — "
                    f"ce pack ne peut pas porter la démonstration")

    snap = snapshots.snap_path(snap_dir, pack_id, XBOX_VENDOR, XBOX_PRODUCT)
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(poisoned)

    # Ce que le propriétaire vient de mapper à la main pour sa Xbox.
    cfg = tmp_path / Path(seed).name
    owner_text = seed.read_text()
    cfg.write_text(owner_text)

    snapshots.restore(snap_dir, pack_id, cfg, module.extract, module.replace,
                      XBOX_VENDOR, XBOX_PRODUCT)

    assert cfg.read_text() == owner_text, (
        f"{pack_id}: restore() a écrasé la config de la Xbox avec un snapshot "
        f"dont le GUID {DS4_GUID} désigne {vidpid_of(DS4_GUID)}. "
        f"block_disagrees() garde capture() et pas restore(), et aucune route "
        f"ne permet d'effacer un snapshot : une fois empoisonné, réappliqué à "
        f"chaque connexion, pour toujours.")
