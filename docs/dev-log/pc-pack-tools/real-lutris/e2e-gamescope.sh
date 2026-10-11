#!/bin/bash
# The session under gamescope: settings written at launch, game followed, all gone after.
cd ~ || exit 1
echo "xrandr: $(xrandr --query 2>&1 | grep ' connected' | head -2)"
bash /opt/gctest/docs/dev-log/pc-pack-tools/real-lutris/e2e.sh
cat ~/.var/app/net.lutris.Lutris/data/lutris/system.yml
grep -i "gamescope\|lutris-wrapper" ~/.cache/lutris/lutris.log ~/session.log 2>/dev/null | tail -12
echo "left: $(pgrep -u "$(id -u)" -x 'gamescope|sleep|lutris-wrapper' | wc -l) game processes"
