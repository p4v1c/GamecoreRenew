#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
melonds_layout_toggle.py  v2  --  bascule l'affichage de melonDS a la volee
   A = DS normal (2 ecrans, 4:3)
   B = ecran du haut seul, 16:9
sans redimensionner la fenetre, en plein ecran, compatible Wayland natif.

CE QUI A CHANGE EN v2, ET POURQUOI
----------------------------------
v1 avait DEUX dependances a la manette :

  1. le daemon lit le bouton sur /dev/input/event* -> code evdev BTN_THUMBL
     (317). Stable : c'est le kernel qui le fixe, identique sur toute manette.
  2. melonDS devait recevoir LE MEME appui pour declencher son hotkey
     "Swap screen emphasis" -- le seul moyen de lui faire recalculer sa
     geometrie. Or melonDS passe par SDL et retient un COUPLE
     (index de joystick, index de bouton SDL), pas un code evdev.

Brancher/debrancher des manettes renumerote les joysticks SDL, et l'index du
bouton "L3" differe d'un modele a l'autre. Le point 2 casse donc des qu'on
change de manette : le daemon ecrit bien la config, melonDS ne recalcule
jamais, rien ne bouge a l'ecran. C'est le symptome "L3 ne fait plus rien".

v2 supprime cette dependance : le declencheur envoye a melonDS est une TOUCHE
CLAVIER synthetique emise par le daemon via /dev/uinput. Un keycode ne change
jamais, quel que soit le nombre de manettes branchees. Cote melonDS on lie une
bonne fois "Swap screen emphasis" a cette touche (colonne CLAVIER).

v2 corrige aussi, cote entrees, le recyclage des noeuds /dev/input/eventN : en
debranchant la manette 1 puis en connectant la manette 2, le kernel reattribue
souvent le MEME numero. v1 comparait les chemins et gardait donc un descripteur
mort. v2 suit les peripheriques par identite (st_rdev), pas par chemin.

Enfin la localisation memoire ne depend plus d'un offset de vtable code en dur
(qui casse a chaque nouvelle version de melonDS) : voir la section
"LOCALISATION" et --derive.

USAGE
  Diagnostic complet (a lancer en premier si quelque chose cloche) :
      python3 melonds_layout_toggle.py --diag
  Voir en direct ce que le daemon recoit de la manette :
      python3 melonds_layout_toggle.py --watch
  Daemon :
      python3 melonds_layout_toggle.py
  Mode de secours a calibration (methode v1) :
      python3 melonds_layout_toggle.py --mode blob --calibrate

Depends : stdlib uniquement. Meme uid que melonDS,
/proc/sys/kernel/yama/ptrace_scope = 0.
"""

import os
import re
import glob
import json
import time
import fcntl
import errno
import shutil
import struct
import select
import hashlib
import argparse

# ===========================================================================
# CONFIG
# ===========================================================================
# Offsets connus pour melonDS 1.1 (Flathub net.kuribo64.melonDS, commit
# 66752a19). Ce ne sont plus que des PISTES : elles sont validees a l'attache
# et re-derivees automatiquement si elles ne collent plus.
HINT = {"vtable": 0x445790, "sizing": 0x54, "aspect": 0x5C, "numscr": 0x140}

OBJ_WIN = 0x400                    # fenetre d'objet inspectee en re-derivation
BLOB_LO, BLOB_HI = 0x50, 0x120     # mode blob (secours) uniquement

STATE_B = {"sizing": 4, "aspect": 1}     # haut seul 16:9
STATE_A = {"sizing": 0, "aspect": 0}     # DS normal 4:3

# Boutons declencheurs cote daemon (codes evdev : identiques sur toute manette)
KEY_NAMES = {
    "L3": 0x13d,   # BTN_THUMBL
    "R3": 0x13e,   # BTN_THUMBR
    "L1": 0x136,   # BTN_TL
    "R1": 0x137,   # BTN_TR
    "PS": 0x13c,   # BTN_MODE
    "F":  33,      # KEY_F
}
TRIGGER_KEYCODES = {KEY_NAMES["L3"]}

# Touche clavier synthetique envoyee a melonDS (mode recalc "uinput").
# A lier dans melonDS : Config -> Input -> Hotkeys -> "Swap screen emphasis",
# colonne CLAVIER. F12 par defaut ; changer avec --hotkey-key en cas de conflit.
UINPUT_KEYS = {"F9": 67, "F10": 68, "F11": 87, "F12": 88,
               "F13": 183, "F14": 184, "F15": 185,
               "SCROLLLOCK": 70, "PAUSE": 119}
HOTKEY_CODE = UINPUT_KEYS["F12"]

# Valeur Qt de la meme touche, telle que melonDS l'enregistre dans son .toml.
# melonDS stocke `getEventKeyVal()` = QKeyEvent::key() | modificateurs
# (EmuInstanceInput.cpp), relu par `hkKeyMapping[i] = keycfg.GetInt(...)`.
# Sans modificateur, c'est donc la constante Qt::Key_* brute.
QT_KEYS = {67: 0x01000038,   # F9
           68: 0x01000039,   # F10
           87: 0x0100003A,   # F11
           88: 0x0100003B,   # F12
           183: 0x0100003C, 184: 0x0100003D, 185: 0x0100003E,   # F13-F15
           70: 0x01000026,   # ScrollLock
           119: 0x01000008}  # Pause

# Config melonDS : Flatpak d'abord, paquet natif ensuite.
MELONDS_TOMLS = [
    os.path.expanduser("~/.var/app/net.kuribo64.melonDS/config/melonDS/melonDS.toml"),
    os.path.expanduser("~/.config/melonDS/melonDS.toml"),
]
BINDING = "HK_SwapScreenEmphasis"

# ---- cheat widescreen -----------------------------------------------------
# Un code Action Replay "widescreen" fait rendre au jeu un champ de vision 16:9
# dans le meme framebuffer 256x192 ; etire ensuite en 16:9, la geometrie est
# juste au lieu d'etre deformee. Mais en 4:3 ce meme code ECRASE l'image : il ne
# doit donc etre actif QUE dans l'etat B. melonDS relit `code.Enabled` a chaque
# frame (AREngine::RunCheats), c'est donc un simple bool a basculer.
CHEAT_NAME = "WIDESCREEN16_9"      # <= 15 caracteres -> SSO, stocke DANS l'objet

# melonDS::ARCode, disposition libstdc++ x86-64 :
#   +0x00  ARCodeCat* Parent
#   +0x08  std::string Name         (32 o ; tampon SSO a +0x10 de la string)
#   +0x28  std::string Description  (32 o)
#   +0x48  bool Enabled
#   +0x50  std::vector<u32> Code
OFF_NAME, OFF_ENABLED, SSO_OFF = 0x08, 0x48, 0x10

RESCAN_S    = 2.0        # hotplug manette
SCAN_IDLE_S = 3.0        # recherche du pid melonDS
DEBOUNCE_S  = 0.35
SETTLE_S    = 0.30       # marge pour que melonDS traite le hotkey (1 frame ~17 ms)

CALIB_PATH = os.path.expanduser("~/.config/melonds-layout-toggle/calib.json")
CACHE_PATH = os.path.expanduser("~/.cache/melonds-layout-toggle/offsets.json")

# ===========================================================================
IEV     = struct.Struct("llHHi")     # struct input_event (x86-64)
EV_SYN, EV_KEY = 0x00, 0x01

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)


def keyname(code):
    return next((k for k, v in UINPUT_KEYS.items() if v == code), str(code))


def melonds_toml():
    override = os.environ.get("MELONDS_CONFIG")
    if override:
        return override if os.path.isfile(override) else None
    root = os.environ.get("GAMECORE_PATH")
    if root:
        # Match GameCore's launcher choice, not a stale Flatpak config left on
        # disk after switching to its optional lib/melon native executable.
        native = os.path.isfile(os.path.join(root, "lib", "melon"))
        data = os.environ.get("GAMECORE_DATA", root)
        try:
            systems = json.load(open(os.path.join(data, "config", "systems.json")))
            system = next(s for s in systems if s.get("id") == "melonds")
            native = os.path.basename(system["path"]) != "flatpak"
        except (OSError, ValueError, KeyError, StopIteration, TypeError):
            pass
        path = MELONDS_TOMLS[1 if native else 0]
        return path if os.path.isfile(path) else None
    return next((p for p in MELONDS_TOMLS if os.path.isfile(p)), None)


def is_melonds_binary(path):
    path = path.removesuffix(" (deleted)")
    if os.path.basename(path) == "melonDS":
        return True
    root = os.environ.get("GAMECORE_PATH")
    return bool(root and path == os.path.realpath(os.path.join(root, "lib", "melon")))


def read_binding(path=None):
    """(valeur clavier, valeur manette) de HK_SwapScreenEmphasis, ou (None, None)."""
    path = path or melonds_toml()
    if not path:
        return None, None
    vals, sec = {}, None
    try:
        for ln in open(path, encoding="utf-8", errors="replace"):
            t = ln.strip()
            if t.startswith("["):
                sec = t
            elif sec in ("[Instance0.Keyboard]", "[Instance0.Joystick]") and "=" in t:
                k, _, v = t.partition("=")
                if k.strip() == BINDING:
                    vals[sec] = v.strip()
    except OSError:
        return None, None
    return vals.get("[Instance0.Keyboard]"), vals.get("[Instance0.Joystick]")


def ensure_binding(hkcode, verbose=True, cheats=True):
    """Pose 'Swap screen emphasis' sur la touche CLAVIER attendue dans le .toml
    de melonDS, et vide sa liaison MANETTE.

    Pourquoi automatiquement : cette liaison a deja disparu une fois toute
    seule (melonDS a reecrit sa config avec -1 partout), et sans elle la
    bascule ne fait plus rien. La liaison manette, elle, est un index SDL qui
    casse des qu'on change de manette -- on la retire pour de bon.

    N'ecrit JAMAIS pendant que melonDS tourne : il reecrit tout son fichier en
    quittant, l'edition serait perdue.
    """
    path = melonds_toml()
    if not path:
        return False
    if find_pid(force=True) is not None:
        return False
    want_kb = str(QT_KEYS.get(hkcode))
    if hkcode not in QT_KEYS:
        return False
    kb, joy = read_binding(path)
    txt = open(path, encoding="utf-8", errors="replace").read()
    # melonDS ne charge AUCUN cheat si EnableCheats est faux : le drapeau
    # Enabled de notre code widescreen ne servirait alors a rien.
    need_cheats = cheats and re.search(r"^EnableCheats = false$", txt, re.M) is not None
    if kb == want_kb and joy in ("-1", None) and not need_cheats:
        return False                     # deja bon
    out, sec, done = [], None, []
    for ln in open(path, encoding="utf-8", errors="replace").read().splitlines():
        t = ln.strip()
        if t.startswith("["):
            sec = t
        elif need_cheats and t == "EnableCheats = false":
            out.append("EnableCheats = true")
            done.append("EnableCheats -> true (sans quoi aucun cheat n'est charge)")
            continue
        elif "=" in t and t.partition("=")[0].strip() == BINDING:
            if sec == "[Instance0.Keyboard]" and t.partition("=")[2].strip() != want_kb:
                out.append("%s = %s" % (BINDING, want_kb))
                done.append("clavier -> %s (%s)" % (want_kb, keyname(hkcode)))
                continue
            if sec == "[Instance0.Joystick]" and t.partition("=")[2].strip() != "-1":
                out.append("%s = -1" % BINDING)
                done.append("manette -> -1 (liaison SDL retiree)")
                continue
        out.append(ln)
    if not done:
        return False
    try:
        shutil.copy2(path, path + ".bak-mlt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    except OSError as e:
        if verbose:
            log("liaison melonDS : ecriture impossible (%s)" % e)
        return False
    if verbose:
        log("liaison melonDS posee dans %s : %s" % (os.path.basename(path), " ; ".join(done)))
    return True


def expected_numscreens(sizing):
    """TopOnly(4) / BottomOnly(5) -> 1 ecran ; tout le reste -> 2.
    Invariant de melonDS independant du build : sert a valider un candidat."""
    return 1 if sizing in (4, 5) else 2


# ---------- process / maps -------------------------------------------------
SCAN_FULL_S = 10.0       # controle "une instance plus recente est-elle apparue ?"
_pid_cache = {"pid": None, "next_scan": 0.0, "next_full": 0.0, "warned": None}


def _starttime(pid):
    """Champ 22 de /proc/<pid>/stat : date de demarrage, en ticks depuis le boot."""
    try:
        d = open("/proc/%d/stat" % pid).read()
        return int(d[d.rindex(")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return 0


def _all_melonds():
    out = []
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if is_melonds_binary(os.readlink(p + "/exe")):
                out.append(int(os.path.basename(p)))
        except OSError:
            pass
    return out


def find_pid(force=False):
    """PID de melonDS -- la plus RECENTE s'il y en a plusieurs.

    La touche synthetique part vers la fenetre au premier plan, donc vers
    l'instance que l'utilisateur vient d'ouvrir. Ecrire la config d'une AUTRE
    instance ne produit rien : panne parfaitement silencieuse, deja rencontree
    (une instance de test oubliee en arriere-plan captait le daemon pendant que
    le F12 partait vers la vraie partie).

    Balayer tout /proc chaque seconde coute plus cher que tout le reste du
    daemon : tant que le PID connu repond on ne lit qu'un /proc/<pid>/comm, et
    le balayage complet n'a lieu que toutes les SCAN_FULL_S, pour reperer une
    instance plus recente.
    """
    c = _pid_cache
    now = time.time()

    fast = None
    if c["pid"] is not None:
        try:
            if is_melonds_binary(os.readlink("/proc/%d/exe" % c["pid"])):
                fast = c["pid"]
            else:
                c["pid"] = None
        except OSError:
            c["pid"] = None

    if fast is not None and not force and now < c["next_full"]:
        return fast
    if fast is None and not force and now < c["next_scan"]:
        return None

    c["next_scan"] = now + SCAN_IDLE_S
    c["next_full"] = now + SCAN_FULL_S
    pids = _all_melonds()
    if not pids:
        c["pid"] = None
        return None
    best = max(pids, key=_starttime)
    if len(pids) > 1 and c["warned"] != best:
        c["warned"] = best
        log("%d instances de melonDS (%s) -> j'utilise la plus recente : %d"
            % (len(pids), ",".join(str(x) for x in sorted(pids)), best))
    elif len(pids) == 1:
        c["warned"] = None
    c["pid"] = best
    return best


MAP_RE = re.compile(r"^([0-9a-f]+)-([0-9a-f]+) (\S{4}) \S+ \S+ \S+\s*(.*?)\s*$")

def regions(pid):
    out = []
    for ln in open("/proc/%d/maps" % pid):
        m = MAP_RE.match(ln)
        if m:
            out.append({"lo": int(m.group(1), 16), "hi": int(m.group(2), 16),
                        "perms": m.group(3), "path": m.group(4)})
    return out


def module_span(pid, regs=None):
    """(base, lo, hi) des mappings du binaire melonDS -- /app/bin (Flatpak) ou
    /usr/bin (natif). None si absent."""
    regs = regs if regs is not None else regions(pid)
    hits = [r for r in regs if is_melonds_binary(r["path"])]
    if not hits:
        return None
    lo = min(r["lo"] for r in hits)
    return lo, lo, max(r["hi"] for r in hits)


def scan_regions(pid, regs=None):
    """Regions rw- ou chercher des objets. On saute la region rwx de 128 Mo
    (RAM DS emulee + JIT) : rien pour nous et couteuse a lire."""
    regs = regs if regs is not None else regions(pid)
    out = [r for r in regs
           if r["perms"].startswith("rw") and "x" not in r["perms"]
           and (r["hi"] - r["lo"]) <= (256 << 20)]
    out.sort(key=lambda r: (r["path"] != "[heap]", r["lo"]))   # heap d'abord
    return out


def build_fingerprint(mem, base, lo, hi):
    """Identifie le build de melonDS sans dependre du chemin du fichier
    (inaccessible depuis l'hote pour un Flatpak) : empreinte des premiers
    octets mappes + taille du module."""
    head = mem.rd_soft(base, min(1 << 20, hi - lo))
    if head is None:
        return None
    return "%s-%x" % (hashlib.sha256(head).hexdigest()[:16], hi - lo)


# ---------- memoire -------------------------------------------------------
class Mem:
    def __init__(self, pid):
        self.f = open("/proc/%d/mem" % pid, "r+b", 0)

    def close(self):
        try: self.f.close()
        except OSError: pass

    def rd(self, a, n):
        self.f.seek(a)
        b = self.f.read(n)
        if b is None or len(b) != n:
            # /proc/<pid>/mem d'un process mort renvoie 0 octet sans lever
            raise OSError("lecture incomplete a 0x%x (%d/%d octets) - melonDS ferme ?"
                          % (a, 0 if b is None else len(b), n))
        return b

    def rd_soft(self, a, n):
        """Lecture best-effort : None si la plage n'est pas lisible."""
        try:
            self.f.seek(a)
            b = self.f.read(n)
        except OSError:
            return None
        return b if b is not None and len(b) == n else None

    def wr(self, a, b):
        self.f.seek(a); self.f.write(b)

    def ri32(self, a): return struct.unpack("<i", self.rd(a, 4))[0]
    def ri64(self, a): return struct.unpack("<q", self.rd(a, 8))[0]
    def wi32(self, a, v): self.wr(a, struct.pack("<i", int(v)))
    def wi64(self, a, v): self.wr(a, struct.pack("<q", int(v)))


# ===========================================================================
# LOCALISATION  (ce qui rend le fix resistant aux mises a jour)
#
#   noeuds de config toml : par signature texte "ScreenSizing\0" (toml11 range
#     la valeur int64 a +0x18 de la cle). Ne depend pas du build de melonDS,
#     seulement de la disposition d'un noeud toml11 -> stable.
#   objet ScreenPanel : par pointeur de vtable, mais l'offset de vtable n'est
#     PLUS code en dur. Trois niveaux, du moins cher au plus cher :
#       1. offsets en cache pour ce build (empreinte memoire du module)
#       2. offsets "piste" (melonDS 1.1), valides par les invariants
#       3. balayage : tout qword aligne pointant dans le module est candidat
#     Validation d'un candidat = 3 contraintes independantes :
#         obj.screenSizing    == config.ScreenSizing
#         obj.screenAspectTop == config.ScreenAspectTop
#         obj.numScreens      == expected_numscreens(sizing)
#     C'est ce croisement config <-> objet qui remplace la confiance aveugle
#     dans une constante de build.
#   Si la classe elle-meme a bouge (offsets internes differents), --derive
#     retrouve tout par diff A/B et met le resultat en cache.
#
#   Surtout : en mode natif l'objet n'est plus INDISPENSABLE. Il ne sert qu'a
#   verifier qu'une bascule a bien pris. S'il n'est pas retrouve, le daemon
#   continue de fonctionner (sans verification) au lieu de refuser de
#   s'attacher comme en v1.
# ===========================================================================

def find_toml_nodes(mem, regs, key, vmax):
    """Toutes les adresses plausibles de la valeur int64 du noeud `key`.
    Le buffer texte du .toml en RAM contient aussi la chaine, mais avec des
    octets ASCII a +0x18 -> ecarte par le controle 0 <= v <= vmax."""
    needle = key.encode() + b"\x00"
    found = []
    for r in regs:
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is None:
            continue
        i = data.find(needle)
        while i != -1:
            if i + 0x20 <= len(data):
                v = struct.unpack_from("<q", data, i + 0x18)[0]
                if 0 <= v <= vmax:
                    found.append(r["lo"] + i + 0x18)
            i = data.find(needle, i + 1)
    return found


def find_cheat_flags(mem, regs, name):
    """Adresses du bool `Enabled` de chaque copie du cheat `name`.

    Meme principe que les noeuds toml : on cherche le NOM en memoire. Comme il
    fait moins de 16 caracteres, libstdc++ le range dans l'objet lui-meme (SSO),
    donc l'ARCode commence a (chaine - 0x18). On le verifie au lieu de le
    supposer : le pointeur interne du std::string doit pointer sur son propre
    tampon, et sa taille doit valoir celle du nom.

    Il y a normalement DEUX copies -- celle de l'ARCodeFile et celle que
    l'AREngine execute (`nds->AREngine.Cheats = cheatFile->GetCodes()`). On les
    prend toutes, comme pour les noeuds de config.
    """
    needle = name.encode() + b"\x00"
    out = []
    for r in regs:
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is None:
            continue
        i = data.find(needle)
        while i != -1:
            chars = r["lo"] + i
            obj = chars - (OFF_NAME + SSO_OFF)
            try:
                if (mem.ri64(obj + OFF_NAME) == chars
                        and mem.ri64(obj + OFF_NAME + 8) == len(name)
                        and mem.rd(obj + OFF_ENABLED, 1)[0] in (0, 1)):
                    out.append(obj + OFF_ENABLED)
            except OSError:
                pass
            i = data.find(needle, i + 1)
    return out


def _check_obj(buf, off, offs, cfg_s, cfg_a):
    """buf/off = tampon contenant l'objet a l'offset off."""
    try:
        s = struct.unpack_from("<i", buf, off + offs["sizing"])[0]
        a = struct.unpack_from("<i", buf, off + offs["aspect"])[0]
        n = struct.unpack_from("<i", buf, off + offs["numscr"])[0]
    except struct.error:
        return False
    return s == cfg_s and a == cfg_a and n == expected_numscreens(s)


def scan_panel(mem, pid, span, cfg_s, cfg_a, offs, vtable_off=None):
    """Retourne (adresse_objet, vtable_off) ou (None, None).

    vtable_off connu   -> recherche du pointeur exact (rapide).
    vtable_off inconnu -> tout qword aligne pointant dans le module est
                          candidat ; les invariants font le tri.
    """
    base, mlo, mhi = span
    need = struct.pack("<Q", base + vtable_off) if vtable_off is not None else None
    max_off = max(offs[k] for k in ("sizing", "aspect", "numscr")) + 4

    for r in scan_regions(pid):
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is None:
            continue
        if need is not None:
            i = data.find(need)
            while i != -1:
                if i % 8 == 0 and i + max_off <= len(data) and \
                   _check_obj(data, i, offs, cfg_s, cfg_a):
                    return r["lo"] + i, vtable_off
                i = data.find(need, i + 1)
            continue
        end = len(data) - max_off
        for i in range(0, max(0, end), 8):
            p = struct.unpack_from("<Q", data, i)[0]
            if mlo <= p < mhi and _check_obj(data, i, offs, cfg_s, cfg_a):
                return r["lo"] + i, p - base
    return None, None


def load_cache(fp):
    if not fp:
        return None
    try:
        return json.load(open(CACHE_PATH)).get(fp)
    except (OSError, ValueError):
        return None


def save_cache(fp, offs):
    if not fp:
        return
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        try:
            all_ = json.load(open(CACHE_PATH))
        except (OSError, ValueError):
            all_ = {}
        all_[fp] = offs
        json.dump(all_, open(CACHE_PATH, "w"), indent=1)
    except OSError:
        pass


class Target:
    """Une session attachee a un process melonDS."""

    def __init__(self, pid):
        self.pid  = pid
        self.mem  = Mem(pid)
        self.obj  = None
        self.offs = dict(HINT)
        span = module_span(pid)
        if span is None:
            raise RuntimeError("module melonDS absent de /proc/%d/maps" % pid)
        self.span = span
        self.fp   = build_fingerprint(self.mem, *span)

        self.toml_s = self.toml_a = None
        self.toml_s_all = self.toml_a_all = []
        self.cheat_flags, self.cheat_scan = [], 0.0
        if not self.locate_toml():
            raise RuntimeError("noeuds de config ScreenSizing/ScreenAspectTop "
                               "introuvables (melonDS pas encore initialise ?)")
        self.locate_panel()

        log("attache pid=%d module=0x%x panel=%s toml=%dx sizing/%dx aspect build=%s"
            % (pid, span[0], hex(self.obj) if self.obj else "non-localise",
               len(self.toml_s_all), len(self.toml_a_all), self.fp or "?"))
        if self.obj is None:
            log("   panel non localise -> bascule sans verification.")
            log("   (melonDS a peut-etre ete mis a jour : '--derive' le retrouve)")

    # --- config : c'est ce que melonDS relit, donc la source de verite ------
    def locate_toml(self):
        """Garde TOUS les candidats, pas seulement le premier.

        La signature texte "ScreenSizing\0" matche plusieurs fois dans le tas :
        le noeud vivant de [Instance0.Window0], mais aussi des copies mortes
        (autres sections Window materialisees a la lecture, tampons de parsing).
        Mesure sur le boitier : 3 candidats, dont UN SEUL relu par melonDS --
        et l'ordre depend de l'etat du tas, donc prendre "le premier" est un
        coup de des. On les ecrit donc tous : ils restent en phase, et peu
        importe lequel melonDS relit.
        """
        regs = scan_regions(self.pid)
        self.toml_s_all = find_toml_nodes(self.mem, regs, "ScreenSizing", 5)
        self.toml_a_all = find_toml_nodes(self.mem, regs, "ScreenAspectTop", 4)
        self.toml_s = self.toml_s_all[0] if self.toml_s_all else None
        self.toml_a = self.toml_a_all[0] if self.toml_a_all else None
        return self.toml_s is not None and self.toml_a is not None

    # --- cheat widescreen (facultatif : absent pour la plupart des jeux) ---
    def locate_cheat(self):
        """Les ARCode n'existent qu'une fois la ROM chargee -- donc bien apres
        l'attache. On (re)cherche a la demande, avec garde-fou temporel."""
        self.cheat_flags = find_cheat_flags(self.mem, scan_regions(self.pid), CHEAT_NAME)
        self.cheat_scan = time.time()
        return bool(self.cheat_flags)

    def cheat_ready(self, retry_s=30.0):
        if self.cheat_flags:
            try:                                    # toujours valides ?
                self.mem.rd(self.cheat_flags[0], 1)
                return True
            except OSError:
                self.cheat_flags = []
        if time.time() - self.cheat_scan < retry_s:
            return False
        return self.locate_cheat()

    def set_cheat(self, on):
        """Ecrit le drapeau dans TOUTES les copies. Renvoie le nombre ecrit."""
        n = 0
        for a in self.cheat_flags:
            try:
                self.mem.wr(a, b"\x01" if on else b"\x00")
                n += 1
            except OSError:
                pass
        return n

    def refresh(self):
        """Re-localise noeuds de config ET panel.

        Le noeud de config VIVANT et l'objet ScreenPanel sont crees tard, a la
        construction de la fenetre -- `ScreenPanel::loadConfig()` materialise le
        noeud en appelant cfg.GetInt(). S'attacher une seconde apres le
        lancement ne voit donc que des noeuds MORTS (sections Window inutilisees,
        tampons de parsing), dans une region de tas anterieure.

        Symptome exact quand ca arrive : la bascule est annoncee mais rien ne
        bouge, et elle est '(non verifie)' -- puisque le panel manque aussi.
        Le panel est donc le bon signal : tant qu'il manque, on rescanne.
        """
        self.locate_toml()
        return self.locate_panel()

    def cfg(self):
        """Etat courant. Le panel fait foi : c'est ce qui est REELLEMENT
        affiche. Les noeuds de config ne servent de repli que s'il manque."""
        if self.obj is not None:
            st = self.panel_state()
            if st is not None:
                return st[0], st[1]
        return self.mem.ri64(self.toml_s), self.mem.ri64(self.toml_a)

    def write_cfg(self, sizing, aspect):
        wrote = 0
        for nodes, val, vmax in ((self.toml_s_all, sizing, 5),
                                 (self.toml_a_all, aspect, 4)):
            for n in nodes:
                try:
                    if 0 <= self.mem.ri64(n) <= vmax:   # toujours un enum plausible
                        self.mem.wi64(n, val)
                        wrote += 1
                except OSError:
                    pass
        if not wrote:
            raise RuntimeError("noeuds de config invalides -> re-localisation")

    # --- objet ScreenPanel : facultatif, sert a verifier --------------------
    def locate_panel(self):
        # Les invariants comparent l'objet a la config. Comme plusieurs noeuds
        # candidats peuvent porter des valeurs differentes (dont des mortes),
        # on essaie chaque paire de valeurs distinctes, sinon un seul mauvais
        # candidat suffisait a faire echouer toute la localisation.
        pairs, seen = [], set()
        for ns in (self.toml_s_all or [None]):
            for na in (self.toml_a_all or [None]):
                try:
                    v = (self.mem.ri64(ns), self.mem.ri64(na))
                except (OSError, TypeError):
                    continue
                if v not in seen:
                    seen.add(v); pairs.append(v)
        if not pairs:
            pairs = [(0, 0)]
        cached = load_cache(self.fp)
        tries = []
        if cached:
            tries.append((dict(cached), cached.get("vtable")))
        tries.append((dict(HINT), HINT["vtable"]))     # piste melonDS 1.1
        tries.append((dict(HINT), None))               # meme classe, autre build
        for offs, vt in tries:
            obj = vtable = None
            for cfg_s, cfg_a in pairs:
                obj, vtable = scan_panel(self.mem, self.pid, self.span,
                                         cfg_s, cfg_a, offs, vt)
                if obj is not None:
                    break
            if obj is not None:
                self.obj = obj
                self.offs = dict(offs)
                self.offs["vtable"] = vtable
                if not cached or cached.get("vtable") != vtable:
                    save_cache(self.fp, self.offs)
                return True
        self.obj = None
        return False

    def panel_state(self):
        if self.obj is None:
            return None
        try:
            return (self.mem.ri32(self.obj + self.offs["sizing"]),
                    self.mem.ri32(self.obj + self.offs["aspect"]),
                    self.mem.ri32(self.obj + self.offs["numscr"]))
        except OSError:
            return None

    def numscr(self):
        st = self.panel_state()
        return st[2] if st else -1

    # --- mode blob (secours) -----------------------------------------------
    def capture(self):
        s, a = self.cfg()
        return {"blob": self.mem.rd(self.obj + BLOB_LO, BLOB_HI - BLOB_LO).hex(),
                "numscreens": self.numscr(), "sizing": s, "aspect": a}

    def restore(self, snap):
        st = self.panel_state()
        if st is None or not (0 <= st[0] <= 5 and 0 <= st[1] <= 4 and 1 <= st[2] <= 4):
            raise RuntimeError("etat panel implausible -> refus d'ecrire")
        self.mem.wr(self.obj + BLOB_LO, bytes.fromhex(snap["blob"]))
        self.mem.wi32(self.obj + self.offs["numscr"], snap["numscreens"])
        self.write_cfg(snap["sizing"], snap["aspect"])

    def close(self):
        self.mem.close()


# ===========================================================================
# DECLENCHEUR ENVOYE A melonDS
#
# v1 comptait sur le fait que melonDS voie le meme appui manette. C'est
# exactement ce qui casse quand l'ordre des manettes change : melonDS retient
# un index SDL, pas un code evdev. v2 emet une touche CLAVIER synthetique.
# ===========================================================================
UI_SET_EVBIT   = 0x40045564      # _IOW('U', 100, int)
UI_SET_KEYBIT  = 0x40045565      # _IOW('U', 101, int)
UI_DEV_CREATE  = 0x5501          # _IO('U', 1)
UI_DEV_DESTROY = 0x5502          # _IO('U', 2)


class KeyEmitter:
    """Clavier virtuel /dev/uinput a une seule touche."""

    def __init__(self, code):
        self.code = code
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            # struct uinput_user_dev :
            #   char name[80]; struct input_id id (8) ; __u32 ff_effects_max ;
            #   __s32 absmax/absmin/absfuzz/absflat [ABS_CNT=64]
            dev = (b"melonds-layout-toggle".ljust(80, b"\x00")
                   + struct.pack("<HHHH", 0x03, 0x1209, 0x0001, 0x0001)
                   + struct.pack("<I", 0)
                   + b"\x00" * (4 * 64 * 4))
            os.write(self.fd, dev)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        time.sleep(0.15)          # laisse udev creer le noeud

    def _ev(self, t, c, v):
        os.write(self.fd, IEV.pack(0, 0, t, c, v))

    def tap(self):
        self._ev(EV_KEY, self.code, 1); self._ev(EV_SYN, 0, 0)
        time.sleep(0.02)
        self._ev(EV_KEY, self.code, 0); self._ev(EV_SYN, 0, 0)

    def close(self):
        try: fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError: pass
        try: os.close(self.fd)
        except OSError: pass


def uinput_status():
    """(disponible, explication)"""
    if not os.path.exists("/dev/uinput"):
        return False, "absent (sudo modprobe uinput)"
    if not os.access("/dev/uinput", os.W_OK):
        return False, "present mais pas accessible en ecriture (regle udev, cf. README)"
    return True, "OK"


# ===========================================================================
# ENTREES MANETTE
#
# v1 suivait les peripheriques par CHEMIN. En debranchant la manette 1 puis en
# connectant la manette 2, le kernel reattribue le plus petit numero libre :
# souvent le meme /dev/input/eventN. v1 voyait "chemin deja connu", gardait son
# descripteur mort et n'ouvrait jamais la nouvelle manette.
# v2 suit (chemin, st_rdev) : numero de peripherique different = nouvelle
# manette = reouverture immediate.
# ===========================================================================
def EVIOCGBIT(ev, length):  return (2 << 30) | (length << 16) | (ord("E") << 8) | (0x20 + ev)
def EVIOCGNAME(length):     return (2 << 30) | (length << 16) | (ord("E") << 8) | 0x06

KEYBITS_LEN = 96        # KEY_CNT / 8 : couvre les codes jusqu'a 767


def dev_name(fd):
    buf = bytearray(128)
    try:
        fcntl.ioctl(fd, EVIOCGNAME(len(buf)), buf)
    except OSError:
        return "?"
    return buf.split(b"\x00", 1)[0].decode("utf-8", "replace") or "?"


def dev_keybits(fd):
    buf = bytearray(KEYBITS_LEN)
    try:
        fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, KEYBITS_LEN), buf)
    except OSError:
        return None
    return buf


def declares(keybits, codes):
    return any(keybits[c // 8] >> (c % 8) & 1 for c in codes if c // 8 < len(keybits))


class Inputs:
    """Tous les /dev/input/event* qui declarent le bouton declencheur, suivis
    par identite et re-scannes periodiquement (manette Bluetooth = hotplug)."""

    def __init__(self):
        self.devs = {}        # fd -> {"path", "rdev", "name"}
        self.skip = {}        # path -> rdev deja ecarte (evite de rouvrir 23x)
        self.poller = select.poll()
        self.last_scan = 0.0
        self.readable = 0
        self.rescan(force=True)

    def _present(self):
        out = {}
        for path in glob.glob("/dev/input/event*"):
            try:
                out[path] = os.stat(path).st_rdev
            except OSError:
                pass
        return out

    def rescan(self, force=False):
        now = time.time()
        if not force and now - self.last_scan < RESCAN_S:
            return
        self.last_scan = now
        present = self._present()

        # retire ce qui a disparu OU dont le numero de peripherique a change
        for fd, d in list(self.devs.items()):
            if present.get(d["path"]) != d["rdev"]:
                self.drop(fd, "retire/remplace")
        for path, rdev in list(self.skip.items()):
            if present.get(path) != rdev:
                del self.skip[path]

        open_paths = {d["path"] for d in self.devs.values()}
        self.readable = 0
        for path, rdev in sorted(present.items()):
            if path in open_paths or self.skip.get(path) == rdev:
                self.readable += 1
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.readable += 1
            bits = dev_keybits(fd)
            if bits is None or not declares(bits, TRIGGER_KEYCODES):
                # clavier, souris, capteurs de la DS4... : rien pour nous.
                self.skip[path] = rdev
                os.close(fd)
                continue
            self.devs[fd] = {"path": path, "rdev": rdev, "name": dev_name(fd)}
            self.poller.register(fd, select.POLLIN)
            log("entree + %s  [%s]" % (path, self.devs[fd]["name"]))

    def drop(self, fd, why="ferme"):
        d = self.devs.pop(fd, None)
        try: self.poller.unregister(fd)
        except (OSError, KeyError): pass
        try: os.close(fd)
        except OSError: pass
        if d:
            log("entree - %s  [%s] (%s)" % (d["path"], d["name"], why))

    def wait(self, timeout_ms):
        return self.poller.poll(timeout_ms)

    def pressed(self, events):
        """Nom du peripherique ayant envoye un appui declencheur, sinon None.
        POLLHUP/POLLERR sont traites explicitement : en v1 un descripteur mort
        restait 'pret' en permanence -> 100 % de CPU quand une manette
        s'eteignait."""
        hit = None
        for fd, ev in events:
            if fd not in self.devs:
                continue
            if ev & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                self.drop(fd, "deconnecte")
                continue
            try:
                buf = os.read(fd, IEV.size * 64)
            except BlockingIOError:
                continue
            except OSError as e:
                self.drop(fd, "erreur %s" % errno.errorcode.get(e.errno, e.errno))
                continue
            for off in range(0, len(buf) - IEV.size + 1, IEV.size):
                _, _, et, code, val = IEV.unpack_from(buf, off)
                if et == EV_KEY and val == 1 and code in TRIGGER_KEYCODES:
                    hit = self.devs[fd]["name"]
        return hit

    def close(self):
        for fd in list(self.devs):
            self.drop(fd)


# ===========================================================================
# BASCULE
# ===========================================================================
def toggle(tgt, emitter, use_cheat=True):
    """Ecrit l'etat cible dans la config puis demande a melonDS de recalculer.

    En mode uinput c'est NOUS qui declenchons le hotkey : plus de course avec
    melonDS, et plus aucune dependance a la manette de son cote.
    En mode hotkey (v1) on compte sur le meme appui physique.
    Renvoie (libelle, verifie) ; libelle None = melonDS n'a pas suivi.
    """
    cur_s, cur_a = tgt.cfg()
    to_B = (cur_s, cur_a) != (STATE_B["sizing"], STATE_B["aspect"])
    want = STATE_B if to_B else STATE_A
    label = "B (haut seul 16:9)" if to_B else "A (DS normal)"

    tgt.write_cfg(want["sizing"], want["aspect"])
    # Le widescreen n'a de sens qu'en 16:9 : actif en B, coupe en A.
    if use_cheat and tgt.cheat_ready():
        tgt.set_cheat(to_B)
    if emitter is not None:
        emitter.tap()

    time.sleep(SETTLE_S)
    st = tgt.panel_state()
    if st is None:
        tgt.refresh()                    # noeuds peut-etre crees depuis
        return label, False              # pas de panel : rien a verifier
    if (st[0], st[1]) == (want["sizing"], want["aspect"]):
        return label, True

    # melonDS n'a pas recalcule : on remet la config en phase avec l'affichage
    # pour que le prochain appui reparte d'un etat coherent.
    try:
        tgt.write_cfg(cur_s, cur_a)
    except Exception:
        pass
    tgt.locate_toml()
    return None, True


# ===========================================================================
# RE-DERIVATION DES OFFSETS  (survie aux mises a jour de melonDS)
#
# On force melonDS a passer de l'etat courant a l'autre, et on diffe la
# memoire. Les champs cherches sont les seuls a suivre EXACTEMENT la transition
# attendue :
#     sizing     : s0 -> s1
#     aspect     : a0 -> a1
#     numScreens : expected(s0) -> expected(s1)
# et ils appartiennent au meme objet, dont le premier qword pointe dans le
# module (pointeur de vtable) et ne change pas entre les deux instantanes.
# Aucune constante de build n'intervient.
# ===========================================================================
def snapshot(pid, mem):
    out = []
    for r in scan_regions(pid):
        data = mem.rd_soft(r["lo"], r["hi"] - r["lo"])
        if data is not None:
            out.append((r["lo"], data))
    return out


def derive(tgt, emitter, verbose=True):
    base, mlo, mhi = tgt.span
    s0, a0 = tgt.cfg()
    n0 = expected_numscreens(s0)
    other = STATE_B if (s0, a0) != (STATE_B["sizing"], STATE_B["aspect"]) else STATE_A
    s1, a1 = other["sizing"], other["aspect"]
    n1 = expected_numscreens(s1)
    if s0 == s1 or a0 == a1 or n0 == n1:
        if verbose:
            print("  etat de depart inutilisable pour un diff (sizing=%d aspect=%d)" % (s0, a0))
        return None
    if verbose:
        print("  derivation : etat %d/%d -> %d/%d" % (s0, a0, s1, a1))

    snap0 = snapshot(tgt.pid, tgt.mem)
    tgt.write_cfg(s1, a1)
    if emitter is not None:
        emitter.tap()
    time.sleep(max(SETTLE_S, 0.4))
    snap1 = snapshot(tgt.pid, tgt.mem)

    hits = []
    for (lo0, d0), (lo1, d1) in zip(snap0, snap1):
        if lo0 != lo1 or len(d0) != len(d1):
            continue                      # le mapping a bouge, on l'ignore
        end = len(d0) - OBJ_WIN
        for i in range(0, max(0, end), 8):
            p = struct.unpack_from("<Q", d0, i)[0]
            if not (mlo <= p < mhi):
                continue
            if struct.unpack_from("<Q", d1, i)[0] != p:
                continue
            so = ao = no = None
            for k in range(0, OBJ_WIN - 3, 4):
                v0 = struct.unpack_from("<i", d0, i + k)[0]
                v1 = struct.unpack_from("<i", d1, i + k)[0]
                if v0 == v1:
                    continue
                if   (v0, v1) == (s0, s1) and so is None: so = k
                elif (v0, v1) == (a0, a1) and ao is None: ao = k
                elif (v0, v1) == (n0, n1) and no is None: no = k
            if so is not None and ao is not None and no is not None:
                hits.append({"vtable": p - base, "sizing": so, "aspect": ao,
                             "numscr": no, "obj": lo0 + i})

    try:                                   # on remet l'etat de depart
        tgt.write_cfg(s0, a0)
        if emitter is not None:
            emitter.tap()
    except Exception:
        pass

    if not hits:
        return None
    if verbose and len(hits) > 1:
        print("  %d objets candidats, on garde le premier" % len(hits))
    h = hits[0]
    offs = {k: h[k] for k in ("vtable", "sizing", "aspect", "numscr")}
    save_cache(tgt.fp, offs)
    tgt.obj, tgt.offs = h["obj"], dict(offs)
    if verbose:
        print("  objet @ 0x%x" % h["obj"])
        print("  VTABLE_OFF = 0x%x   OFF_SIZING = 0x%x   OFF_ASPECT = 0x%x   "
              "OFF_NUMSCR = 0x%x" % (offs["vtable"], offs["sizing"],
                                     offs["aspect"], offs["numscr"]))
        print("  enregistre dans %s (build %s)" % (CACHE_PATH, tgt.fp))
    return offs


# ===========================================================================
# DAEMON
# ===========================================================================
def load_calib():
    try:
        calib = json.load(open(CALIB_PATH))
    except (OSError, ValueError) as e:
        log("calibration illisible : %s" % e); return None
    if (calib.get("blob_lo"), calib.get("blob_hi")) != (BLOB_LO, BLOB_HI):
        log("calibration incompatible avec cette version -> re-calibrer."); return None
    return calib


def make_emitter(recalc, code, quiet=False):
    """(emitter, mode_effectif).

    `quiet` sert aux tentatives repetees : au demarrage de la machine
    /dev/uinput n'a pas encore l'ACL de session (le service utilisateur part
    avant l'ouverture de session), et rester en repli 'hotkey' pour toujours
    reviendrait a tourner dans le mode qu'on cherche justement a quitter."""
    if recalc == "hotkey":
        return None, "hotkey"
    ok, why = uinput_status()
    if not ok:
        if not quiet:
            log("uinput indisponible : %s" % why)
            log("   -> mode 'hotkey' en attendant ; je retente en boucle.")
        return None, "hotkey"
    try:
        return KeyEmitter(code), "uinput"
    except OSError as e:
        if not quiet:
            log("clavier virtuel impossible (%s) -> mode 'hotkey' en attendant" % e)
        return None, "hotkey"


def do_daemon(mode, recalc, hkcode, use_cheat=True):
    emitter, eff = make_emitter(recalc, hkcode) if mode == "native" else (None, "n/a")
    devs = Inputs()
    if not devs.readable:
        print("Aucun /dev/input/event* lisible. Groupe 'input' requis "
              "(sudo usermod -aG input $USER, puis relogin).")
        return 1

    keylabel = ",".join(sorted(k for k, v in KEY_NAMES.items() if v in TRIGGER_KEYCODES)) \
               or ",".join(str(c) for c in sorted(TRIGGER_KEYCODES))
    log("daemon pret [mode %s / recalc %s]. %d entree(s) avec le bouton, sur %d. touche=%s"
        % (mode, eff, len(devs.devs), devs.readable, keylabel))
    if not devs.devs:
        log("aucune manette avec ce bouton pour l'instant - je l'attends (hotplug)")
    if eff == "uinput":
        kb, joy = read_binding()
        want = str(QT_KEYS.get(hkcode))
        if kb == want:
            log("melonDS : 'Swap screen emphasis' lie a la touche CLAVIER %s  OK"
                % keyname(hkcode))
        else:
            log("melonDS : 'Swap screen emphasis' pas encore sur %s (lu : %s)"
                % (keyname(hkcode), kb))
            log("   -> je le poserai des que melonDS sera ferme.")
    elif eff == "hotkey":
        log("melonDS doit avoir 'Swap screen emphasis' sur le meme bouton MANETTE.")
        log("   Cette liaison est un index SDL : elle casse des que l'ordre des")
        log("   manettes change. Preferer --recalc uinput.")

    calib, calib_mtime = None, None
    tgt = None
    last_fail = None
    last_toggle = last_check = last_emit_try = last_refresh = 0.0
    refresh_wait = 3.0          # espace les rescans si le panel ne vient jamais
    melonds_seen = find_pid() is not None
    if not melonds_seen and eff == "uinput":
        ensure_binding(hkcode, cheats=use_cheat)   # melonDS ferme : bon moment

    def toml_mtime():
        tp = melonds_toml()
        try:
            return os.path.getmtime(tp) if tp else None
        except OSError:
            return None
    cfg_mtime = toml_mtime()
    try:
        while True:
            events = devs.wait(1000)
            now = time.time()

            if now - last_check > 1.0:
                last_check = now
                devs.rescan()

                # uinput pas encore accessible au demarrage de la machine :
                # on retente au lieu de rester bloque en repli 'hotkey'.
                if emitter is None and recalc != "hotkey" and mode == "native" \
                        and now - last_emit_try > 5.0:
                    last_emit_try = now
                    emitter, eff2 = make_emitter(recalc, hkcode, quiet=True)
                    if emitter is not None:
                        eff = eff2
                        log("clavier virtuel disponible -> recalc uinput (touche %s)"
                            % keyname(hkcode))
                        ensure_binding(hkcode, cheats=use_cheat)
                if mode == "blob":
                    try:
                        mtime = os.path.getmtime(CALIB_PATH)
                    except OSError:
                        mtime = None
                    if mtime != calib_mtime:
                        calib_mtime = mtime
                        calib = load_calib() if mtime is not None else None
                        if calib:
                            log("calibration chargee (%s)" % CALIB_PATH)

                # Panel absent = on s'est attache avant que melonDS cree sa
                # fenetre : les noeuds de config vus sont morts, la bascule ne
                # ferait rien. On rescanne jusqu'a le trouver.
                if tgt is not None and tgt.obj is None and now - last_refresh > refresh_wait:
                    last_refresh = now
                    if tgt.refresh():
                        refresh_wait = 3.0
                        log("panel localise apres coup : 0x%x  (%dx sizing/%dx aspect)"
                            % (tgt.obj, len(tgt.toml_s_all), len(tgt.toml_a_all)))
                    else:
                        refresh_wait = min(refresh_wait * 2, 30.0)

                pid = find_pid()
                if pid is None:
                    if tgt:
                        log("melonDS ferme."); tgt.close(); tgt = None
                    if melonds_seen and eff == "uinput":
                        melonds_seen = False
                        ensure_binding(hkcode, cheats=use_cheat)  # il vient de reecrire
                        cfg_mtime = toml_mtime()
                elif not melonds_seen:
                    melonds_seen = True

                # melonDS.toml modifie par quelqu'un d'autre (autoconfig
                # manettes, reinstallation, edition manuelle) : on re-verifie.
                if eff == "uinput" and pid is None:
                    mt = toml_mtime()
                    if mt != cfg_mtime:
                        cfg_mtime = mt
                        ensure_binding(hkcode, cheats=use_cheat)
                elif tgt is None or tgt.pid != pid:
                    if tgt:
                        tgt.close()
                    try:
                        tgt = Target(pid); last_fail = None; refresh_wait = 3.0
                    except Exception as e:
                        tgt = None
                        if last_fail != (pid, str(e)):     # une ligne par cause
                            last_fail = (pid, str(e))
                            log("attache impossible (pid %d): %s" % (pid, e))
                            if isinstance(e, OSError):
                                log("   -> ptrace_scope=%s ; il doit valoir 0"
                                    % open("/proc/sys/kernel/yama/ptrace_scope").read().strip())

            who = devs.pressed(events)
            if not who:
                continue
            if recalc == "uinput" and emitter is None:
                # The pack disables the joystick hotkey. Do not write memory
                # until we can actually ask the emulator to redraw.
                continue
            if now - last_toggle < DEBOUNCE_S:
                continue
            last_toggle = now
            if tgt is None and find_pid(force=True) is None:
                log("bouton recu de [%s] mais melonDS non attache." % who)
                continue
            if tgt is None:
                continue        # melonDS vient de demarrer : attache au prochain tour

            try:
                if mode == "native":
                    label, verified = toggle(tgt, emitter, use_cheat)
                    if label is None:
                        log("melonDS n'a pas reagi au declencheur.")
                        if eff == "uinput":
                            log("   -> 'Swap screen emphasis' est-il bien lie a la")
                            log("      touche CLAVIER attendue (Config -> Input -> Hotkeys) ?")
                        else:
                            log("   -> liaison manette obsolete (changement de manette ?).")
                            log("      Passer en --recalc uinput, ou refaire la liaison.")
                    else:
                        ws = ""
                        if use_cheat and tgt.cheat_flags:
                            ws = "  widescreen %s" % ("ON" if label.startswith("B") else "off")
                        log("bascule -> %s   [%s]%s%s"
                            % (label, who, "" if verified else "  (non verifie)", ws))
                else:
                    if calib is None:
                        log("bouton recu mais pas de calibration (--calibrate)."); continue
                    if tgt.obj is None:
                        log("mode blob : objet ScreenPanel non localise (--derive)."); continue
                    A, B = calib["A"], calib["B"]
                    in_B = tgt.cfg() == (B["sizing"], B["aspect"])
                    snap, label = (A, "A (DS normal)") if in_B else (B, "B (haut seul 16:9)")
                    tgt.restore(snap)
                    time.sleep(0.05)
                    log("bascule -> %s   (numScreens=%d) [%s]" % (label, tgt.numscr(), who))
            except Exception as e:
                log("echec: %s" % e)
                try: tgt.close()
                except Exception: pass
                tgt = None
    finally:
        devs.close()
        if emitter:
            emitter.close()


# ===========================================================================
# OUTILS
# ===========================================================================
def do_watch():
    """Affiche TOUT ce qui arrive des peripheriques d'entree : repond en
    5 secondes a la question 'le daemon voit-il ma manette ?'."""
    print("Peripheriques d'entree (tous, pas seulement ceux qui declarent %s) :"
          % ",".join(hex(c) for c in sorted(TRIGGER_KEYCODES)))
    fds, poller = {}, select.poll()
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            print("  %-22s  NON LISIBLE (%s)" % (path, e.strerror))
            continue
        bits = dev_keybits(fd)
        mark = "   <-- declare le declencheur" if bits and declares(bits, TRIGGER_KEYCODES) else ""
        print("  %-22s  %s%s" % (path, dev_name(fd), mark))
        fds[fd] = path
        poller.register(fd, select.POLLIN)
    if not fds:
        print("\nAucun peripherique lisible : groupe 'input' manquant.")
        return
    print("\nAppuie sur des boutons (Ctrl-C pour sortir).")
    while True:
        for fd, ev in poller.poll(1000):
            if ev & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                poller.unregister(fd); os.close(fd)
                print("  %s deconnecte" % fds.pop(fd, "?"))
                continue
            try:
                buf = os.read(fd, IEV.size * 64)
            except OSError:
                continue
            for off in range(0, len(buf) - IEV.size + 1, IEV.size):
                _, _, et, code, val = IEV.unpack_from(buf, off)
                if et == EV_KEY and val in (0, 1):
                    name = next((k for k, v in KEY_NAMES.items() if v == code), "")
                    print("  %-22s code=%d (0x%x) %-3s %-8s%s"
                          % (fds.get(fd, "?"), code, code, name,
                             "APPUI" if val else "relache",
                             "   <== DECLENCHEUR" if (val and code in TRIGGER_KEYCODES) else ""))


def do_diag(hkcode):
    print("=== melonds-layout-toggle : diagnostic ===\n")

    print("-- systeme")
    try:
        ps = open("/proc/sys/kernel/yama/ptrace_scope").read().strip()
    except OSError:
        ps = "?"
    print("   ptrace_scope        : %s%s" % (ps, "   OK" if ps == "0" else "   (doit valoir 0)"))
    ok, why = uinput_status()
    print("   /dev/uinput         : %s" % why)
    ev = sorted(glob.glob("/dev/input/event*"))
    lisible = sum(1 for p in ev if os.access(p, os.R_OK))
    print("   /dev/input/event*   : %d present(s), %d lisible(s)%s"
          % (len(ev), lisible, "   (groupe input ?)" if lisible < len(ev) else ""))

    print("\n-- entrees declarant %s"
          % (",".join(sorted(k for k, v in KEY_NAMES.items() if v in TRIGGER_KEYCODES))
             or ",".join(str(c) for c in sorted(TRIGGER_KEYCODES))))
    found = 0
    for path in ev:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        bits = dev_keybits(fd)
        if bits and declares(bits, TRIGGER_KEYCODES):
            print("   %-22s %s" % (path, dev_name(fd)))
            found += 1
        os.close(fd)
    if not found:
        print("   AUCUNE. Manette allumee ? (--watch pour voir les codes reels)")

    print("\n-- liaison 'Swap screen emphasis' dans la config melonDS")
    tp = melonds_toml()
    if not tp:
        print("   config melonDS introuvable.")
    else:
        kb, joy = read_binding(tp)
        want = str(QT_KEYS.get(hkcode))
        print("   fichier             : %s" % tp)
        print("   touche clavier      : %s   %s"
              % (kb, "OK (%s)" % keyname(hkcode) if kb == want
                 else "-> attendu %s pour %s" % (want, keyname(hkcode))))
        print("   bouton manette      : %s   %s"
              % (joy, "OK (retiree)" if joy in ("-1", None)
                 else "a retirer : index SDL, casse au changement de manette"))
        if kb != want or joy not in ("-1", None):
            print("   -> le daemon la posera tout seul, melonDS ferme")

    print("\n-- melonDS")
    pid = find_pid(force=True)
    if not pid:
        print("   pas lance.")
        return
    try:
        mem = Mem(pid)
    except OSError as e:
        print("   pid=%d mais /proc/%d/mem inaccessible : %s" % (pid, pid, e))
        print("   -> ptrace_scope doit valoir 0 (install-melonds-layout-toggle.sh)")
        return
    span = module_span(pid)
    print("   pid=%d  module=0x%x" % (pid, span[0] if span else 0))
    print("   build               : %s" % (build_fingerprint(mem, *span) if span else "?"))
    print("   offsets en cache    : %s" % (load_cache(build_fingerprint(mem, *span))
                                           if span else None))
    mem.close()
    try:
        tgt = Target(pid)
    except Exception as e:
        print("   attache impossible : %s" % e)
        return
    s, a = tgt.cfg()
    print("   config en memoire   : ScreenSizing=%d  ScreenAspectTop=%d  (@0x%x, @0x%x)"
          % (s, a, tgt.toml_s, tgt.toml_a))
    if tgt.obj:
        st = tgt.panel_state()
        print("   ScreenPanel         : 0x%x   vtable+0x%x sizing+0x%x aspect+0x%x numscr+0x%x"
              % (tgt.obj, tgt.offs["vtable"], tgt.offs["sizing"],
                 tgt.offs["aspect"], tgt.offs["numscr"]))
        print("   etat affiche        : sizing=%d aspect=%d numScreens=%d%s"
              % (st[0], st[1], st[2],
                 "" if st[2] == expected_numscreens(st[0]) else "   (incoherent !)"))
    else:
        print("   ScreenPanel         : NON LOCALISE  -> lancer --derive")

    print("\n   (la liaison clavier %s est posee automatiquement par le daemon,"
          % keyname(hkcode))
    print("    melonDS ferme : voir la section 'liaison' plus haut.)")
    tgt.close()


def do_derive(recalc, hkcode):
    pid = find_pid(force=True)
    if not pid:
        print("melonDS ne tourne pas."); return
    tgt = Target(pid)
    emitter, eff = make_emitter(recalc, hkcode)
    if eff != "uinput":
        print("Sans uinput je ne peux pas declencher le recalcul moi-meme.")
        print("Relance avec --recalc uinput (cf. --diag).")
        tgt.close(); return
    print("Derivation des offsets pour ce build (l'ecran va basculer 2 fois)...")
    if derive(tgt, emitter) is None:
        print("  echoue : melonDS n'a pas recalcule, ou la classe a trop change.")
        print("  Verifier d'abord que la bascule elle-meme marche (--diag).")
    emitter.close()
    tgt.close()


def do_calibrate():
    pid = find_pid(force=True)
    if not pid:
        print("melonDS ne tourne pas."); return
    tgt = Target(pid)
    if tgt.obj is None:
        print("objet ScreenPanel non localise -> --derive d'abord."); return
    print("\n  CALIBRATION (mode blob, secours) - regle via le MENU de melonDS.")
    print("  Meme session, fenetre a la taille de jeu, sans la redimensionner.\n")

    def wait_state(want):
        shown = stable = None
        while True:
            if find_pid() != tgt.pid:
                raise RuntimeError("melonDS ferme pendant la calibration")
            cur = tgt.cfg()
            if cur != shown:
                shown = cur
                print("       (actuel sizing=%d aspect=%d - attendu %d/%d)"
                      % (cur[0], cur[1], want[0], want[1]))
            if cur == want:
                if stable is None:
                    stable = time.time()
                elif time.time() - stable >= 0.4:
                    return
            else:
                stable = None
            time.sleep(0.1)

    try:
        print("  1/2  View -> Screen sizing = Even, Aspect ratio (top) = 4:3")
        wait_state((STATE_A["sizing"], STATE_A["aspect"]))
        A = tgt.capture()
        print("       capture A OK\n")
        print("  2/2  View -> Screen sizing = Top only, Aspect ratio (top) = 16:9")
        wait_state((STATE_B["sizing"], STATE_B["aspect"]))
        B = tgt.capture()
        print("       capture B OK")
    except (RuntimeError, OSError) as e:
        print("\n  !! %s -- rien enregistre." % e); return
    if A["blob"] == B["blob"]:
        print("\n  !! A et B identiques. Recommence."); return
    os.makedirs(os.path.dirname(CALIB_PATH), exist_ok=True)
    json.dump({"version": 2, "blob_lo": BLOB_LO, "blob_hi": BLOB_HI, "A": A, "B": B},
              open(CALIB_PATH, "w"), indent=1)
    print("\n  Calibration enregistree : %s" % CALIB_PATH)
    tgt.close()


# ---------- main -----------------------------------------------------
def keyarg(v):
    """Accepte "L3" / "r3" / "F" (cf. KEY_NAMES) ou un code evdev numerique."""
    k = KEY_NAMES.get(v.strip().upper())
    if k is not None:
        return k
    try:
        return int(v, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "touche inconnue %r (noms : %s, ou un code evdev)" % (v, ", ".join(KEY_NAMES)))


def hkarg(v):
    k = UINPUT_KEYS.get(v.strip().upper())
    if k is not None:
        return k
    try:
        return int(v, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "touche inconnue %r (noms : %s, ou un code evdev)" % (v, ", ".join(UINPUT_KEYS)))


def main():
    global CALIB_PATH
    ap = argparse.ArgumentParser(description="bascule affichage melonDS (memoire, sans resize)")
    ap.add_argument("--diag", "--scan", dest="diag", action="store_true",
                    help="diagnostic complet (systeme, entrees, melonDS) puis sort")
    ap.add_argument("--watch", action="store_true",
                    help="affiche les evenements d'entree bruts de tous les peripheriques")
    ap.add_argument("--derive", action="store_true",
                    help="re-derive les offsets memoire pour ce build de melonDS")
    ap.add_argument("--calibrate", action="store_true", help="(mode blob) capture les etats A/B")
    ap.add_argument("--key", type=keyarg, action="append",
                    help="bouton declencheur : L3 (defaut), R3, L1, R1, PS, F, ou code evdev")
    ap.add_argument("--mode", choices=("native", "blob"), default="native",
                    help="native (defaut) : melonDS recalcule lui-meme ; "
                         "blob : rejoue une calibration")
    ap.add_argument("--recalc", choices=("auto", "uinput", "hotkey"), default="auto",
                    help="comment demander a melonDS de recalculer. uinput = touche "
                         "clavier synthetique, insensible au changement de manette "
                         "(defaut si /dev/uinput est accessible) ; hotkey = comportement v1")
    ap.add_argument("--hotkey-key", type=hkarg, default=HOTKEY_CODE, metavar="TOUCHE",
                    help="touche clavier envoyee a melonDS (defaut F12)")
    ap.add_argument("--no-widescreen", action="store_true",
                    help="ne pas toucher au cheat widescreen (cf. widescreen/)")
    ap.add_argument("--calib", metavar="FICHIER", help="chemin de la calibration")
    a = ap.parse_args()

    if a.key:
        TRIGGER_KEYCODES.clear(); TRIGGER_KEYCODES.update(a.key)
    if a.calib:
        CALIB_PATH = os.path.expanduser(a.calib)

    if a.watch:     return do_watch()
    if a.diag:      return do_diag(a.hotkey_key)
    if a.derive:    return do_derive(a.recalc, a.hotkey_key)
    if a.calibrate: return do_calibrate()
    return do_daemon(a.mode, a.recalc, a.hotkey_key, not a.no_widescreen)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass

# ---------------------------------------------------------------------------
# NOTE PORTAGE / MISES A JOUR
#   Plus rien n'est code en dur de facon bloquante :
#   - noeuds toml   : signature texte, independante du build
#   - objet panel   : offsets en cache par build, sinon pistes 1.1 validees par
#                     invariants, sinon balayage, sinon --derive
#   - declencheur   : code evdev (daemon) + keycode clavier (melonDS)
#   Apres une mise a jour de melonDS, le pire cas est :
#       melonds-layout-toggle --derive
#   qui recalcule et met en cache VTABLE_OFF / OFF_SIZING / OFF_ASPECT /
#   OFF_NUMSCR pour le nouveau binaire. La bascule, elle, marche deja sans eux.
# ---------------------------------------------------------------------------
