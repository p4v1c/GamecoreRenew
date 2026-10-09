#!/bin/sh
# Mirror the checkout's Shelf theme into the dev server's data dir (it serves themes from there).
S=/tmp/claude-0/-home-user-GamecoreRenew/1b797080-036c-5ff1-9857-ebc0724751de/scratchpad
rsync -a --delete /home/user/GamecoreRenew/config/themes/shelf/ $S/gcdata/config/themes/shelf/
