#!/bin/bash
# Real Lutris, real lutris_session.py: the session must last as long as the game.
cd ~ || exit 1
start=$(date +%s.%N)
python3 /opt/gctest/catalog/lutris/files/lutris_session.py --app-id net.lutris.Lutris ~/emu/lutris/Sleeper.lutris > ~/session.log 2>&1
code=$?
end=$(date +%s.%N)
echo "exit=$code elapsed=$(python3 -c "print(round($end-$start,1))")"
grep "gamecore-lutris\|lutris-wrapper\|Game ID\|Launching\|quit\|Shutting" ~/session.log | head -20
