"""F-007 — le schéma autorise une LISTE de cibles, le répartiteur n'en passe qu'une.

Famille : contrats du catalogue.

`catalog/_schema/pack.schema.json` déclare :

    "target": { "type": ["string", "array"], "items": { "type": "string" } }

`generator_opts()` la réduit sans un mot :

    target = ctl.get("target")
    if isinstance(target, list):
        target = target[0]                    # ← les autres disparaissent
    return {... "target": config_dir / target if target else config_dir, ...}

Aujourd'hui c'est sans conséquence, et pour une raison qui tient du hasard : le
seul pack déclarant une liste est aussi le seul des dix dont le générateur ne
lit JAMAIS `opts["target"]` — il code ses deux noms de fichiers en dur. Les deux
défauts se masquent l'un l'autre.

Le piège est pour le pack suivant. Un générateur qui déclare deux cibles et
fait ce que font neuf générateurs sur dix — lire `opts["target"]` — n'en
recevra qu'une, et écrira la moitié de ce qu'il déclare. Sans erreur, sans
journal, et avec un pack.json qui affirme le contraire.

Ce test interroge le catalogue, il ne nomme aucun pack.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.catalog import load_catalog                   # noqa: E402
from backend.services.configgen import generator_opts               # noqa: E402

CATALOG = ROOT / "catalog"


def _packs_declaring_several_targets():
    """Les packs dont `controllers.target` est une liste de plus d'un élément."""
    out = []
    for pack_dir in sorted(CATALOG.iterdir()):
        meta_path = pack_dir / "pack.json"
        if pack_dir.name.startswith("_") or not meta_path.is_file():
            continue
        ctl = (json.loads(meta_path.read_text()).get("controllers") or {})
        target = ctl.get("target")
        if isinstance(target, list) and len(target) > 1:
            out.append((pack_dir.name, target))
    return out


MULTI_TARGET = _packs_declaring_several_targets()


def test_le_schema_autorise_bien_une_liste_de_cibles():
    """Garde-fou : le constat porte sur un écart entre le schéma et le
    répartiteur. Si le schéma cessait d'autoriser la liste, il n'y aurait plus
    d'écart et ce fichier devrait disparaître."""
    schema = json.loads((CATALOG / "_schema" / "pack.schema.json").read_text())
    target = schema["properties"]["controllers"]["properties"]["target"]
    assert "array" in target["type"], (
        "le schéma n'autorise plus une liste de cibles — le constat F-007 est "
        "peut-être résolu, revérifier avant de le traiter")


def test_au_moins_un_pack_declare_plusieurs_cibles():
    """Garde-fou : sans un tel pack, le test suivant serait vide."""
    assert MULTI_TARGET, (
        "aucun pack ne déclare plus d'une cible — le constat n'a plus de "
        "porteur dans le catalogue, mais l'écart schéma/répartiteur demeure")


@pytest.mark.parametrize("pack_id,declared", MULTI_TARGET,
                         ids=[p[0] for p in MULTI_TARGET])
def test_toutes_les_cibles_declarees_sont_transmises(tmp_path, pack_id, declared):
    """LE CONSTAT — rouge sur main.

    Ce que le pack déclare et ce que le générateur reçoit doivent coïncider.
    """
    pack = load_catalog()[pack_id]
    opts = generator_opts(pack, tmp_path, tmp_path / "snaps")
    assert opts is not None, f"{pack_id}: pas de bloc `config`, rien à vérifier"

    handed = {p.name for p in opts.values() if isinstance(p, Path)}
    missing = [t for t in declared if Path(t).name not in handed]

    assert not missing, (
        f"{pack_id} déclare {len(declared)} cibles {declared} et "
        f"generator_opts() n'en transmet qu'une : `opts['target']` vaut "
        f"{opts['target'].name!r}. Les autres ({missing}) ne sont dans aucune "
        f"clé de opts — `target = target[0]` les jette sans journal. "
        f"Aujourd'hui c'est masqué parce que le générateur de ce pack code ses "
        f"noms de fichiers en dur et ne lit jamais opts['target'] ; les neuf "
        f"autres générateurs du catalogue, eux, le lisent. Le pack suivant qui "
        f"déclarera deux cibles et suivra la convention majoritaire en écrira "
        f"une seule, en silence.")
