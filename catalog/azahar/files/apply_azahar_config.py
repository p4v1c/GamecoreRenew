#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_azahar_config.py  --  pose les 2 reglages Azahar dont la bascule L3 a besoin.

  [Layout]
  layouts_to_cycle   = 0, 1     -> F10 bascule Default <-> SingleScreen
                                   (au lieu de defiler les 7 layouts)
  screen_top_stretch = true     -> en SingleScreen, l'ecran du haut remplit
                                   toute la fenetre (16:9 plein cadre)

POURQUOI CE SCRIPT
  Azahar reecrit tout son qt-config.ini quand il se ferme, a partir de son etat
  en memoire : editer le fichier pendant qu'il tourne ne sert a rien. Ce script
  refuse donc d'ecrire si Azahar tourne, et sait attendre qu'il se ferme.

  A relancer si la config Azahar est un jour reinitialisee.

  --wait [SECONDES]   attend la fermeture d'Azahar (defaut : 2 h) puis applique
  --check             n'ecrit rien, dit juste ou on en est

NOTE : `aspect_ratio` (l'enum AspectRatio::R16_9) existe dans le moteur de layout
mais n'est ni lu ni ecrit par la config Qt en 2125.1.1 -- inutile de le poser
dans le .ini, il ne serait jamais relu. D'ou `screen_top_stretch`, qui lui est
bien persiste et n'agit que dans SingleFrameLayout (l'affichage natif n'y touche
pas : il passe par LargeFrameLayout).
"""

import os
import glob
import time
import shutil
import argparse

INI = os.path.expanduser(
    "~/.var/app/org.azahar_emu.Azahar/config/azahar-emu/qt-config.ini")
SECTION = "[Layout]"
WANT = {                       # cle -> (valeur voulue, flag \default voulu)
    "layouts_to_cycle":   ("0, 1", "false"),
    "screen_top_stretch": ("true", "false"),
}


def azahar_running():
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if open(p + "/comm").read().strip() == "azahar":
                return int(os.path.basename(p))
        except OSError:
            pass
    return None


def read_state(path):
    """Valeurs actuelles des cles surveillees dans [Layout]."""
    cur, insec = {}, False
    for ln in open(path, encoding="utf-8"):
        s = ln.strip()
        if s.startswith("["):
            insec = (s == SECTION)
        elif insec and "=" in s:
            k, _, v = s.partition("=")
            if k in WANT:
                cur[k] = v
    return cur


def apply(path):
    out, insec, changed, seen = [], False, [], set()
    wanted = {key + suffix: value for key, values in WANT.items()
              for suffix, value in zip(("", "\\default"), values)}

    def finish_section():
        for key, value in wanted.items():
            if key not in seen:
                out.append("%s=%s" % (key, value))
                changed.append("%s : absent -> %s" % (key, value))
                seen.add(key)

    found_section = False
    original = open(path, encoding="utf-8").read()
    for ln in original.splitlines():
        s = ln.strip()
        if s.startswith("["):
            if insec:
                finish_section()
            insec = (s == SECTION)
            found_section |= insec
        if insec and "=" in s:
            k, _, v = s.partition("=")
            k, v = k.strip(), v.strip()
            if k in wanted:
                seen.add(k)
                want = wanted[k]
                if v != want:
                    changed.append("%s : %s -> %s" % (k, v, want))
                    out.append("%s=%s" % (k, want))
                    continue
        out.append(ln)
    if not found_section:
        out.extend(["", SECTION])
    finish_section()
    if changed:
        shutil.copy2(path, path + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
        staged = path + ".layout-tmp"
        with open(staged, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.replace(staged, path)
    return changed


def main():
    ap = argparse.ArgumentParser(description="regle Azahar pour la bascule L3")
    ap.add_argument("--wait", nargs="?", type=int, const=7200, metavar="SECONDES",
                    help="attend la fermeture d'Azahar (defaut 7200 s) puis applique")
    ap.add_argument("--check", action="store_true", help="n'ecrit rien, montre l'etat")
    a = ap.parse_args()

    if not os.path.isfile(INI):
        print("Config Azahar introuvable : %s" % INI); return 1

    if a.check:
        cur = read_state(INI)
        pid = azahar_running()
        print("Azahar : %s" % ("lance (pid %d)" % pid if pid else "ferme"))
        for k, (want, _) in WANT.items():
            got = cur.get(k, "(absent)")
            print("  %-20s = %-8s  %s" % (k, got, "OK" if got == want else "-> %s" % want))
        return 0

    if a.wait is not None:
        deadline = time.time() + a.wait
        if azahar_running():
            print("Azahar tourne : il reecrira son .ini en quittant. J'attends…",
                  flush=True)
        while azahar_running() and time.time() < deadline:
            time.sleep(3)
        if azahar_running():
            print("Toujours lance apres %d s — rien fait." % a.wait); return 1
        time.sleep(2)          # laisse Azahar finir d'ecrire son fichier

    pid = azahar_running()
    if pid:
        print("Azahar tourne (pid %d) : il ecraserait la modification en quittant." % pid)
        print("Ferme-le, puis relance ce script (ou passe --wait).")
        return 1

    changed = apply(INI)
    if changed:
        print("Applique dans %s :" % SECTION)
        for c in changed:
            print("   " + c)
        print("Sauvegarde du fichier precedent a cote (.bak-*).")
    else:
        print("Rien a faire : les deux reglages sont deja bons.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
