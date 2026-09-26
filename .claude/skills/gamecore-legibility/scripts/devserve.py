"""Dev-only: serve the app WITHOUT its lifespan, with the boot steps marked
done so the UI leaves its splash.

Never run the real lifespan in dev: it calls `sudo -n cpupower`, and failed
sudo attempts lock the account (pam_faillock).

    GAMECORE_PATH=$PWD GAMECORE_DATA=/tmp/gcdata PYTHONPATH=$PWD \
        python3 .claude/skills/gamecore-legibility/scripts/devserve.py

GAMECORE_DATA needs config/systems.json and config/apps.json (copy them from
install/generated/*.dist) and config/themes/ (copy from the repo).
"""
import uvicorn
from backend import main
from backend.services import boot

for step in getattr(boot, "REQUIRED", []):
    boot.done(step)
uvicorn.run(main.app, host="127.0.0.1", port=8766, lifespan="off")
