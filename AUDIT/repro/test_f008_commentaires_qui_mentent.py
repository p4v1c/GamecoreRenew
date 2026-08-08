"""F-008 et F-009 — deux commentaires qui affirment le contraire du code.

Famille : commentaires et docs qui mentent.

Un commentaire faux coûte plus cher qu'un commentaire absent : il oriente le
lecteur suivant dans le mur. Les deux ci-dessous sont au présent de l'indicatif
et décrivent un état de fait, pas une intention.

F-008 — `process_manager.py` affirme que GameCore tourne dans une session
openbox. Le CHANGELOG dit qu'openbox n'est plus installé et n'est plus la cible
d'auto-login ; `install/arch.sh` installe `plasma-desktop` et
`plasma-x11-session`, et le mot openbox n'apparaît plus que dans des
commentaires qui racontent le passé.

F-009 — `defaults.tsx` décrit les sous-pages de réglages comme « des fragments,
pas des modales », à envelopper dans `SettingsOverlay`.
`docs/themes/README.md` dit l'inverse : « The pages already carry their own
overlay — render them bare ». C'est la doc qui a raison : les huit pages
rendent toutes leur propre `<Overlay>`. Suivre le commentaire revient donc à
emboîter une Overlay dans une Overlay — c'est-à-dire à produire exactement le
symptôme (largeur, marges et défilement cassés) qu'il prétend éviter.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

ARCH_SH = ROOT / "install" / "arch.sh"
PROCESS_MANAGER = ROOT / "backend" / "services" / "process_manager.py"
DEFAULTS_TSX = ROOT / "frontend" / "src" / "components" / "defaults.tsx"
THEMES_README = ROOT / "docs" / "themes" / "README.md"
SETTINGS_DIR = ROOT / "frontend" / "src" / "components" / "modals" / "settings"


# ── F-008 : la session openbox ─────────────────────────────────────────────

def _installed_packages() -> set[str]:
    """Ce que `install/arch.sh` installe réellement : le tableau PKGS et les
    `pacman_optional`. Lu, jamais recopié."""
    text = ARCH_SH.read_text()
    pkgs: set[str] = set()
    block = re.search(r"^PKGS=\(\n(.*?)^\)", text, re.S | re.M)
    if block:
        for line in block.group(1).splitlines():
            pkgs.update(w for w in line.split("#", 1)[0].split() if w)
    pkgs.update(re.findall(r"^\s*pacman_optional\s+(\S+)", text, re.M))
    return pkgs


def test_l_installateur_installe_bien_une_session_x11():
    """Garde-fou : si le lecteur de PKGS ne trouvait rien, le test suivant
    serait vert en ne vérifiant rien."""
    pkgs = _installed_packages()
    assert "plasma-desktop" in pkgs, f"PKGS mal lu — trouvé : {sorted(pkgs)[:12]}"


def test_l_installateur_n_installe_plus_openbox():
    """Garde-fou : établit le fait que le commentaire contredit."""
    assert "openbox" not in _installed_packages()


def test_aucun_commentaire_n_affirme_tourner_sous_openbox():
    """LE CONSTAT F-008 — rouge sur main.

    Les mentions historiques (« It used to be a bare openbox session ») sont
    légitimes et ne sont pas visées : le test ne cherche que les affirmations
    au présent sur ce que GameCore FAIT.
    """
    text = PROCESS_MANAGER.read_text()
    lying = [f"{PROCESS_MANAGER.name}:{i}: {line.strip()}"
             for i, line in enumerate(text.splitlines(), 1)
             if re.search(r"runs in an X11 openbox session", line)]

    assert not lying, (
        "commentaire au présent contredit par l'installateur :\n  "
        + "\n  ".join(lying)
        + "\n\nopenbox n'est plus installé (absent de PKGS dans install/arch.sh) "
        "et n'est plus la cible d'auto-login ; le CHANGELOG l'annonce sous "
        "« The kiosk is hosted on the machine's own X11 desktop session ». "
        "La ligne de code qu'il justifie (`env.pop('WAYLAND_DISPLAY')`) reste "
        "correcte — c'est la RAISON donnée qui est fausse, et c'est elle que le "
        "prochain lecteur utilisera pour décider si la ligne peut partir.")


# ── F-009 : fragments ou modales ? ─────────────────────────────────────────

def _settings_pages():
    """Les composants de sous-pages, lus depuis le dossier plutôt que listés."""
    return sorted(p for p in SETTINGS_DIR.glob("*Page.tsx") if p.is_file())


PAGES = _settings_pages()
assert PAGES, "aucune sous-page de réglages trouvée — l'arborescence a bougé"


def test_la_doc_des_themes_dit_bien_que_les_pages_portent_leur_overlay():
    """Garde-fou : le constat est une CONTRADICTION entre deux textes. Si l'un
    des deux disparaissait, il n'y aurait plus de contradiction à signaler."""
    assert "already carry their own overlay" in THEMES_README.read_text()


def test_defaults_tsx_les_decrit_bien_comme_des_fragments():
    """Garde-fou : l'autre moitié de la contradiction."""
    assert "They are fragments, not" in DEFAULTS_TSX.read_text()


@pytest.mark.parametrize("page", PAGES, ids=[p.stem for p in PAGES])
def test_chaque_page_de_reglages_rend_sa_propre_overlay(page):
    """La mesure qui tranche : ce sont des modales, pas des fragments.

    Ce test est VERT. Il n'est pas le constat, il est la preuve que c'est
    `defaults.tsx` qui a tort et `docs/themes/README.md` qui a raison.
    """
    assert "<Overlay" in page.read_text(), (
        f"{page.name} ne rend pas d'Overlay — si plusieurs pages étaient dans "
        f"ce cas, ce serait `defaults.tsx` qui aurait raison et le constat "
        f"F-009 devrait être réécrit dans l'autre sens")


def test_les_deux_textes_ne_se_contredisent_pas():
    """LE CONSTAT F-009 — rouge sur main.

    Deux sources décrivent la même chose et se contredisent. Un thème est
    écrit à partir de l'une ou de l'autre.
    """
    says_fragment = "They are fragments, not" in DEFAULTS_TSX.read_text()
    says_self_contained = ("already carry their own overlay"
                           in THEMES_README.read_text())
    wrapping_pages = sum("<Overlay" in p.read_text() for p in PAGES)

    assert not (says_fragment and says_self_contained), (
        f"frontend/src/components/defaults.tsx dit que les sous-pages sont "
        f"« des fragments, pas des modales » et qu'il faut les envelopper dans "
        f"`SettingsOverlay` ; docs/themes/README.md dit « The pages already "
        f"carry their own overlay — render them bare ». Mesure : "
        f"{wrapping_pages}/{len(PAGES)} pages rendent leur propre <Overlay>, "
        f"donc c'est la doc qui est juste. Un auteur de thème qui suit le "
        f"commentaire emboîte une Overlay dans une Overlay et obtient "
        f"précisément la largeur, les marges et le défilement cassés que ce "
        f"même commentaire dit vouloir éviter — les deux textes racontent le "
        f"même bug Wi-Fi avec des conclusions opposées.")
