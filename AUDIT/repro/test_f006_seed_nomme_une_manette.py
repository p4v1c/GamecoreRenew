"""F-006 — un seed livré épingle une manette précise, et rien ne l'interdit.

Famille : contrats du catalogue.

Le catalogue a un champ pour exactement ce défaut, et le schéma dit pourquoi :

    seedMustNotContain — "A seed that names a device pins the grid to one
    controller model; CI fails on a hit."

Le générateur dolphin raconte l'incident qui l'a fait naître :

    "That seed used to pin `Device = SDL/0..3/PS4 Controller`, which is dead
     input on any box without a DualShock 4 […] the seed now names no device
     and check-catalog.py fails the build if one comes back."

La garde est **déclarative** : elle ne protège que les packs qui la déclarent.
Cinq packs sur dix la déclarent. Un des cinq autres livre un seed qui porte un
GUID SDL brut désignant une manette réelle.

Ce test n'épingle aucun pack : il balaie les seeds du catalogue et décode chaque
GUID de 32 hex avec le même `vidpid_of()` que la production, puis demande à la
base SDL si ce vendor:product désigne une manette connue. Un pack qui prendrait
la même maladie demain est couvert sans qu'on touche à ce fichier.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.configgen.controllers import (                # noqa: E402
    SDL3_FALLBACK_NAMES, db_name_for, vidpid_of,
)

CATALOG = ROOT / "catalog"

# Le même motif que snapshots._ANY_GUID_RE : un GUID SDL de 32 hex où qu'il
# apparaisse. Pas de \b — il ne se déclencherait pas après un `_`, et c'est
# ainsi que Cemu écrit le sien (`0_0500…`).
_ANY_GUID_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32})(?![0-9a-fA-F])")

# Les seeds binaires sont copiés tels quels et jamais substitués ; les scanner
# produit du bruit. Même liste que scripts/check-catalog.py.
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".sqlite3", ".db", ".bin", ".dat"}


def _seed_files():
    """(pack_id, fichier) pour chaque fichier texte de chaque seed livré."""
    out = []
    for pack_dir in sorted(CATALOG.iterdir()):
        if pack_dir.name.startswith("_"):
            continue
        seed = pack_dir / "seed"
        if not seed.is_dir():
            continue
        for f in sorted(seed.rglob("*")):
            if f.is_file() and f.suffix.lower() not in BINARY_SUFFIXES:
                out.append((pack_dir.name, f))
    return out


SEED_FILES = _seed_files()
assert SEED_FILES, "aucun seed texte trouvé — le catalogue a bougé"


def _named_pads(text: str):
    """Les GUID du texte qui désignent une manette que SDL sait nommer.

    Un GUID dont le vendor:product n'est dans aucune table n'est pas retenu :
    ce serait du bruit (un hash, un identifiant de session), pas un pad épinglé.
    """
    hits = []
    for guid in _ANY_GUID_RE.findall(text):
        vendor, product = vidpid_of(guid)
        name = (SDL3_FALLBACK_NAMES.get((vendor, product))
                or db_name_for(vendor, product))
        if name:
            hits.append((guid, vendor, product, name))
    return hits


def test_le_decodeur_reconnait_bien_un_guid_de_manette_reelle():
    """Garde-fou : sans lui, un `_named_pads` cassé rendrait toujours [] et
    tous les tests de ce fichier seraient verts en ne vérifiant rien."""
    ds4 = "05008fe54c050000cc09000000006800"
    hits = _named_pads(f"device0={ds4}\n")
    assert hits, "le décodeur ne reconnaît plus un GUID de DualShock 4"
    assert hits[0][1:3] == ("054c", "09cc")


def test_un_texte_sans_guid_ne_declenche_rien():
    """Garde-fou symétrique : pas de faux positif sur du hex quelconque."""
    assert _named_pads("Volume = 100\nhash = " + "0" * 32 + "\n") == []


@pytest.mark.parametrize("pack_id,path", SEED_FILES,
                         ids=[f"{p}/{f.name}" for p, f in SEED_FILES])
def test_aucun_seed_ne_nomme_une_manette_precise(pack_id, path):
    """LE CONSTAT — rouge sur main.

    Un seed est ce que reçoit une boîte NEUVE. Y épingler un GUID, c'est
    livrer une config qui ne décrit la manette de personne sauf celle de la
    machine où le seed a été récolté.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        pytest.skip(f"{path.name} n'est pas du texte lisible")

    hits = _named_pads(text)
    assert not hits, (
        f"catalog/{pack_id}/seed/{path.relative_to(CATALOG / pack_id / 'seed')} "
        f"porte {len(hits)} GUID de manette réelle : "
        + ", ".join(f"{g} = {v}:{p} ({n})" for g, v, p, n in hits)
        + ". Le champ `controllers.seedMustNotContain` existe pour ça — le "
        "schéma dit « A seed that names a device pins the grid to one "
        "controller model; CI fails on a hit » — mais il est DÉCLARATIF : "
        "check-catalog.py ne vérifie que les motifs que le pack déclare, et "
        "ce pack n'en déclare aucun. Sur une boîte neuve avec une autre "
        "manette, cette config décrit un périphérique qui n'existe pas.")
