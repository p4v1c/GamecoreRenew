#!/usr/bin/env python3
"""Passe 5 — réintroduit un défaut, lance la ligne de base, restaure.

    python3 AUDIT/repro/mutations.py            # toutes
    python3 AUDIT/repro/mutations.py rpcs3-toujours-lie

Une mutation qui laisse la suite VERTE est la preuve qu'aucun test ne garde ce
comportement. C'est la seule forme de preuve possible pour cette famille : le
code de production est correct sur main, donc un « test rouge sur main » ne peut
pas exister — c'est son ABSENCE qui est le constat, et une mutation survivante
est la façon exécutable de la montrer.

**N'utilise jamais `git checkout`** pour restaurer : il détruirait le travail non
commité. Chaque fichier est copié dans un répertoire temporaire avant mutation et
recopié après, y compris si pytest échoue ou si l'utilisateur interrompt.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTEST = [str(ROOT / ".venv/bin/python3"), "-m", "pytest",
          "backend/tests", "catalog", "-q", "-m", "not network",
          "--no-header", "-p", "no:cacheprovider"]

# (nom, fichier, motif à remplacer, remplacement)
MUTATIONS: list[tuple[str, str, str, str]] = [
    # ── survivantes : le constat ───────────────────────────────────────────
    ("rpcs3-toujours-lie",
     "catalog/rpcs3/generator.py",
     'def _is_bound(block: str) -> bool:\n    """',
     'def _is_bound(block: str) -> bool:\n    return True\n    """'),

    ("maxplayers-ignore",
     "backend/services/configgen/__init__.py",
     '        if player_index > ctl.get("maxPlayers", 4):\n            continue',
     '        if False:\n            continue'),

    ("atomic-write-non-atomique",
     "backend/services/configgen/helpers/base.py",
     '    tmp = p.with_name(p.name + ".gamecore-tmp")',
     '    p.write_text(text); return\n    tmp = p.with_name(p.name + ".gamecore-tmp")'),

    ("seed-deploy-reecrit-tout",
     "backend/services/configgen/seed.py",
     '        if target.is_file() and target.read_bytes() == payload:\n            continue',
     '        if False:\n            continue'),

    # ── témoins : la suite les attrape, donc le harnais fonctionne ─────────
    ("multitap-jamais-ecrit",
     "backend/services/configgen/helpers/tier0.py",
     'if multitap and player_index >= multitap["fromPlayer"]:',
     'if False and multitap and player_index >= multitap["fromPlayer"]:'),

    ("gcpad-toujours-sain",
     "catalog/dolphin/generator.py",
     'def _gcpad_is_real(body: str | None) -> bool:\n    """',
     'def _gcpad_is_real(body: str | None) -> bool:\n    return True\n    """'),

    ("block-disagrees-aveugle",
     "backend/services/configgen/snapshots.py",
     'def block_disagrees(block: str, vendor: str, product: str) -> str | None:\n    """',
     'def block_disagrees(block: str, vendor: str, product: str) -> str | None:\n    return None\n    """'),

    ("pack-file-sans-garde-de-chemin",
     "backend/services/installer/applier.py",
     '    if not target.is_relative_to(root):',
     '    if False and not target.is_relative_to(root):'),

    ("event-sort-lexicographique",
     "backend/services/gamepad_monitor.py",
     '    head = path.rstrip("0123456789")',
     '    return (path, 0)\n    head = path.rstrip("0123456789")'),

    ("ordre-de-profilage-alphabetique",
     "backend/services/configgen/__init__.py",
     'key=lambda p: (p.data["controllers"].get("order", 10_000), p.id))',
     'key=lambda p: p.id)'),
]


def run_one(name: str, rel: str, old: str, new: str, bak_dir: Path) -> bool | None:
    src = ROOT / rel
    text = src.read_text()
    if old not in text:
        print(f"  {name}: MOTIF ABSENT dans {rel} — le code a bougé, mutation ignorée")
        return None

    bak = bak_dir / rel.replace("/", "_")
    shutil.copy2(src, bak)
    try:
        src.write_text(text.replace(old, new, 1))
        r = subprocess.run(PYTEST, cwd=ROOT, capture_output=True, text=True,
                           timeout=1800)
        summary = next((ln for ln in reversed(r.stdout.splitlines())
                        if "passed" in ln or "failed" in ln), "?")
        failed = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        survived = r.returncode == 0
        verdict = "SURVIT (aucun test ne garde ça)" if survived else "attrapée"
        print(f"  {name}: {verdict}\n      {summary}")
        for f in failed[:2]:
            print(f"      {f}")
        return survived
    finally:
        shutil.copy2(bak, src)          # toujours, même sur exception


def main() -> int:
    only = set(sys.argv[1:])
    survivors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gamecore-audit-bak-") as tmp:
        bak_dir = Path(tmp)
        for name, rel, old, new in MUTATIONS:
            if only and name not in only:
                continue
            if run_one(name, rel, old, new, bak_dir):
                survivors.append(name)

    print(f"\nMutations survivantes : {len(survivors)}")
    for s in survivors:
        print(f"  · {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
