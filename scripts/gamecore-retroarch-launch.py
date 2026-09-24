#!/usr/bin/env python3
"""Launch one GameCore RetroArch pack without a shell command string."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--core", required=True)
    p.add_argument("rom")
    args = p.parse_args()

    env = dict(os.environ)
    env["LIBRETRO_SYSTEM_DIRECTORY"] = str(
        Path.home() / ".config" / "gamecore-retroarch" / "system"
    )
    argv = [
        "/usr/bin/retroarch",
        "--config", args.config,
        "--libretro", args.core,
        "--fullscreen",
        args.rom,
    ]
    os.execvpe(argv[0], argv, env)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
