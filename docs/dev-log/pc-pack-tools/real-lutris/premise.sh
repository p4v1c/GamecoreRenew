#!/bin/bash
# Without the wrapper: does a second `flatpak run` return before the game ends?
cd ~ || exit 1
flatpak run net.lutris.Lutris > ~/gui.log 2>&1 &
sleep 10
s=$(date +%s.%N)
flatpak run net.lutris.Lutris lutris:rungameid/1 > ~/second.log 2>&1
e=$(date +%s.%N)
echo "second flatpak run returned after $(python3 -c "print(round($e-$s,1))") s"
sleep 8
flatpak kill net.lutris.Lutris
