#!/bin/bash
# GameCore kills a session with SIGKILL to its process group: nothing may survive.
cd ~ || exit 1
setsid python3 /opt/gctest/catalog/lutris/files/lutris_session.py --app-id net.lutris.Lutris ~/emu/lutris/Sleeper.lutris > ~/kill.log 2>&1 &
sleep 8
leader=$(pgrep -f "^python3 /opt/gctest/catalog/lutris/files/lutris_session.py")
pg=$(ps -o pgid= -p "$leader" | tr -d ' ')
echo "session leader=$leader pgid=$pg"
for p in $(pgrep -f "lutris-wrapper|sleep 30"); do echo "  game: $(ps -o pid=,pgid=,args= -p "$p" | cut -c1-80)"; done
kill -KILL -- "-$pg"
sleep 2
echo "left after killpg: $(pgrep -f 'lutris-wrapper|sleep 30' | wc -l) game processes; instances: $(flatpak ps --columns=application | wc -l)"
