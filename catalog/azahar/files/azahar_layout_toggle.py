#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
azahar_layout_toggle.py  --  L3 bascule le layout d'ecran d'Azahar entre
   A = affichage 3DS natif (les deux ecrans)
   B = ecran du haut seul

PRINCIPE
  Azahar sait deja tout faire : son raccourci "Toggle Screen Layout" (F10) fait
  defiler le reglage `layouts_to_cycle`. Reduit a "0, 1", c'est exactement une
  bascule Default <-> SingleScreen (ecran du haut, puisque swap_screen=false).

  Il manque juste le lien manette -> clavier : Azahar ne sait lier ses raccourcis
  qu'a des touches, jamais a un bouton de manette ([Controls] ne contient que les
  boutons de la console emulee).

  Ce daemon lit L3 sur /dev/input/event* et envoie F10 via un clavier virtuel
  uinput, uniquement quand Azahar tourne.

  Aucune ecriture memoire, aucun offset, aucune dependance : une mise a jour
  d'Azahar ne peut pas casser ce daemon.

AUTONOME
  Ce programme ne depend de rien d'autre : ni du gamepad-tv-bridge, ni du daemon
  melonDS. Les deux peuvent tourner en meme temps sans se genrer (chacun ne fait
  quelque chose que si SON emulateur tourne).

USAGE
  azahar-layout-toggle              daemon
  azahar-layout-toggle --test       diagnostic : montre ce qui est vu, n'injecte rien

PREREQUIS
  - appartenir au groupe `input`            (lecture de /dev/input/event*)
  - acces en ecriture a /dev/uinput         (ACL de session, deja le cas)
  - cote Azahar : layouts_to_cycle = 0, 1   (sinon F10 fait defiler 7 layouts)
"""

import os
import glob
import time
import fcntl
import struct
import select
import argparse

# ===========================================================================
# CONFIG
# ===========================================================================
PROC_NAME  = "azahar"       # /proc/<pid>/comm de l'emulateur

KEY_NAMES = {              # codes evdev, /usr/include/linux/input-event-codes.h
    "L3": 0x13d,           # BTN_THUMBL - clic du stick gauche
    "R3": 0x13e,           # BTN_THUMBR
    "L1": 0x136,
    "R1": 0x137,
    "PS": 0x13c,
}
TRIGGER_KEYCODES = {KEY_NAMES["L3"]}

SEND_KEY   = 68            # KEY_F10 = raccourci "Toggle Screen Layout" d'Azahar
DEBOUNCE_S = 0.35
RESCAN_S   = 2.0           # la manette Bluetooth apparait/disparait a chaud

# ===========================================================================
IEV     = struct.Struct("llHHi")    # struct input_event (x86-64), 24 octets
EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------- process ------------------------------------------------------
# Balayer tout /proc chaque seconde coute plus cher que tout le reste du daemon
# (~300 ouvertures de fichier par seconde). Tant que le PID connu repond, on ne
# lit qu'un seul /proc/<pid>/comm ; sinon on ne rebalaye qu'a intervalle espace.
SCAN_IDLE_S = 3.0
SCAN_FULL_S = 10.0       # controle "une instance plus recente est-elle apparue ?"
_pid_cache = {"pid": None, "next_scan": 0.0, "next_full": 0.0, "warned": None}


def _starttime(pid):
    """Champ 22 de /proc/<pid>/stat : date de demarrage, en ticks depuis le boot."""
    try:
        d = open("/proc/%d/stat" % pid).read()
        return int(d[d.rindex(")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return 0


def _all_pids(name=PROC_NAME):
    out = []
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if open(p + "/comm").read().strip() == name:
                out.append(int(os.path.basename(p)))
        except OSError:
            pass
    return out


def find_pid(name=PROC_NAME, force=False):
    """PID de l'emulateur -- la plus RECENTE s'il y en a plusieurs.

    La touche synthetique part vers la fenetre au premier plan, donc vers
    l'instance que l'utilisateur vient d'ouvrir. Viser une autre instance ne
    produirait rien de visible.

    Balayer tout /proc chaque seconde coute plus cher que tout le reste du
    daemon : tant que le PID connu repond on ne lit qu'un /proc/<pid>/comm, et
    le balayage complet n'a lieu que toutes les SCAN_FULL_S.
    """
    c = _pid_cache
    now = time.time()

    fast = None
    if c["pid"] is not None:
        try:
            if open("/proc/%d/comm" % c["pid"]).read().strip() == name:
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
    pids = _all_pids(name)
    if not pids:
        c["pid"] = None
        return None
    best = max(pids, key=_starttime)
    if len(pids) > 1 and c["warned"] != best:
        c["warned"] = best
        log("%d instances de %s (%s) -> j'utilise la plus recente : %d"
            % (len(pids), name, ",".join(str(x) for x in sorted(pids)), best))
    elif len(pids) == 1:
        c["warned"] = None
    c["pid"] = best
    return best


# ---------- clavier virtuel (uinput, ioctls bruts) -----------------------
UI_SET_EVBIT   = 0x40045564         # _IOW('U', 100, int)
UI_SET_KEYBIT  = 0x40045565         # _IOW('U', 101, int)
UI_DEV_CREATE  = 0x00005501         # _IO ('U', 1)
UI_DEV_DESTROY = 0x00005502         # _IO ('U', 2)

class VirtualKeyboard:
    """Clavier virtuel minimal : une seule touche declaree.

    On passe par l'ancienne mise en place (ecriture d'un struct uinput_user_dev
    puis UI_DEV_CREATE), toujours supportee et plus simple que UI_DEV_SETUP.
    """

    def __init__(self, keycode, name=b"azahar-layout-toggle"):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, keycode)
        # struct uinput_user_dev : name[80] + input_id(4x u16) + ff_effects_max
        #                          + 4 tableaux abs* de 64 s32
        dev = (name[:79].ljust(80, b"\0")
               + struct.pack("<HHHH", 0x03, 0x1209, 0x0001, 1)   # BUS_USB, vid, pid, ver
               + struct.pack("<I", 0)
               + b"\0" * (4 * 64 * 4))
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self.keycode = keycode
        time.sleep(0.3)          # laisse le compositeur ouvrir le peripherique

    def _ev(self, etype, code, value):
        os.write(self.fd, IEV.pack(0, 0, etype, code, value))

    def tap(self):
        self._ev(EV_KEY, self.keycode, 1)
        self._ev(EV_SYN, SYN_REPORT, 0)
        time.sleep(0.02)
        self._ev(EV_KEY, self.keycode, 0)
        self._ev(EV_SYN, SYN_REPORT, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


def open_keyboard(keycode):
    """Cree le clavier virtuel, en attendant si /dev/uinput n'est pas encore la.

    /dev/uinput est root:root 0660 avec le tag udev `uaccess` : l'acces vient
    UNIQUEMENT de l'ACL posee par logind quand la session devient active. Au
    demarrage de la machine, le service utilisateur (lingering) peut se lancer
    avant. On attend au lieu de sortir en erreur."""
    t0, warned = time.time(), 0
    while True:
        try:
            return VirtualKeyboard(keycode)
        except OSError as e:
            if warned == 0:
                log("/dev/uinput pas encore accessible (%s) - j'attends l'ACL de session…" % e)
                warned = 1
            elif warned == 1 and time.time() - t0 > 60:
                log("toujours rien apres 60 s. Verifier : getfacl /dev/uinput "
                    "(il faut une ligne user:<toi>:rw-)")
                warned = 2
            time.sleep(3)


# ---------- capacites : ne garder que les peripheriques utiles ------------
def EVIOCGBIT(ev, length):
    """_IOC(_IOC_READ, 'E', 0x20 + ev, length)"""
    return (2 << 30) | (length << 16) | (ord("E") << 8) | (0x20 + ev)

KEYBITS_LEN = 96        # KEY_CNT / 8 : couvre tous les codes jusqu'a 767

def declares_trigger(fd):
    """True si ce peripherique declare au moins un des boutons declencheurs.

    Sans ce filtre on ouvre les 20+ autres entrees de la machine ; les capteurs
    de mouvement de la DS4 emettent en continu et reveillaient `select` en
    permanence pour des evenements qui ne nous concernent pas (~1 % de CPU en
    continu). On ne garde que la manette."""
    buf = bytearray(KEYBITS_LEN)
    try:
        fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, KEYBITS_LEN), buf)
    except OSError:
        return False
    return any(buf[c // 8] >> (c % 8) & 1 for c in TRIGGER_KEYCODES)


# ---------- entrees manette ---------------------------------------------
class Inputs:
    """Tous les /dev/input/event* lisibles, re-scannes periodiquement : la
    manette Bluetooth peut se connecter apres le demarrage du daemon, et
    disparaitre quand elle s'eteint (sinon select() boucle sur un fd mort)."""

    def __init__(self):
        self.fds = {}
        self.readable = 0            # entrees ouvrables, filtre compris
        self.last_scan = 0.0
        self.rescan(force=True)

    def rescan(self, force=False):
        now = time.time()
        if not force and now - self.last_scan < RESCAN_S:
            return
        self.last_scan = now
        present = set(glob.glob("/dev/input/event*"))
        known = set(self.fds.values())
        self.readable = 0
        for path in sorted(present):
            if path in known:
                self.readable += 1
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.readable += 1
            if not declares_trigger(fd):
                os.close(fd)          # clavier, souris, capteurs… : rien pour nous
                continue
            self.fds[fd] = path
            log("entree + %s" % path)
        for fd, path in list(self.fds.items()):
            if path not in present:
                self.drop(fd)

    def drop(self, fd):
        self.fds.pop(fd, None)
        try:
            os.close(fd)
        except OSError:
            pass

    def pressed(self, ready):
        hit = False
        for fd in ready:
            if fd not in self.fds:
                continue
            try:
                buf = os.read(fd, IEV.size * 64)
            except BlockingIOError:
                continue
            except OSError:
                self.drop(fd)          # ENODEV : manette eteinte
                continue
            for off in range(0, len(buf) - IEV.size + 1, IEV.size):
                _, _, et, code, val = IEV.unpack_from(buf, off)
                if et == EV_KEY and val == 1 and code in TRIGGER_KEYCODES:
                    hit = True
        return hit


# ---------- boucles ------------------------------------------------------
def loop(test=False):
    from apply_azahar_config import INI, apply, azahar_running

    def configure():
        if not test and os.path.isfile(INI) and not azahar_running():
            try:
                changes = apply(INI)
                if changes:
                    log("configuration Azahar :", "; ".join(changes))
            except OSError as e:
                log("configuration Azahar indisponible :", e)

    configure()
    devs = Inputs()
    if not devs.readable:
        print("Aucun /dev/input/event* lisible. Groupe 'input' requis "
              "(sudo usermod -aG input $USER puis relogin).")
        return 1

    kbd = open_keyboard(SEND_KEY) if not test else None

    names = ",".join(sorted(k for k, v in KEY_NAMES.items() if v in TRIGGER_KEYCODES))
    log("daemon pret%s. %d peripherique(s) avec le bouton, sur %d lus. %s -> KEY_%d, cible '%s'"
        % (" [TEST, aucune injection]" if test else "",
           len(devs.fds), devs.readable, names or sorted(TRIGGER_KEYCODES),
           SEND_KEY, PROC_NAME))
    if not devs.fds:
        log("aucune manette avec ce bouton pour l'instant - je l'attends (hotplug)")

    seen_pid = None
    last_press = last_check = 0.0
    try:
        while True:
            ready, _, _ = select.select(list(devs.fds), [], [], 1.0)
            now = time.time()

            if now - last_check > 1.0:
                last_check = now
                devs.rescan()
                pid = find_pid()
                if pid != seen_pid:
                    seen_pid = pid
                    log("Azahar %s" % ("lance (pid %d)" % pid if pid else "ferme"))
                    if pid is None:
                        configure()

            if not devs.pressed(ready):
                continue
            if now - last_press < DEBOUNCE_S:
                continue
            last_press = now

            if seen_pid is None:
                seen_pid = find_pid(force=True)     # Azahar vient peut-etre de demarrer
            if seen_pid is None:
                log("bouton recu, mais Azahar ne tourne pas -> rien envoye")
                continue
            if test:
                log("bouton recu, Azahar pid=%d -> j'enverrais KEY_%d" % (seen_pid, SEND_KEY))
                continue
            kbd.tap()
            log("bouton recu -> KEY_%d envoye (bascule du layout)" % SEND_KEY)
    except KeyboardInterrupt:
        pass
    finally:
        if kbd:
            kbd.close()
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="L3 bascule le layout d'ecran d'Azahar (via son raccourci F10)")
    ap.add_argument("--key", action="append",
                    help="bouton declencheur : L3 (defaut), R3, L1, R1, PS, ou un code evdev")
    ap.add_argument("--send-key", type=int, metavar="CODE",
                    help="code de la touche envoyee (defaut 68 = KEY_F10)")
    ap.add_argument("--test", action="store_true",
                    help="diagnostic : affiche ce qui est vu, n'injecte rien")
    a = ap.parse_args()

    if a.key:
        codes = set()
        for v in a.key:
            k = KEY_NAMES.get(v.strip().upper())
            if k is None:
                try:
                    k = int(v, 0)
                except ValueError:
                    ap.error("touche inconnue %r (noms : %s, ou un code evdev)"
                             % (v, ", ".join(KEY_NAMES)))
            codes.add(k)
        TRIGGER_KEYCODES.clear(); TRIGGER_KEYCODES.update(codes)
    if a.send_key:
        global SEND_KEY
        SEND_KEY = a.send_key
    raise SystemExit(loop(a.test))


if __name__ == "__main__":
    main()
