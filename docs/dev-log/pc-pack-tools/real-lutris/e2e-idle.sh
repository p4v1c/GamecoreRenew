#!/bin/bash
# Lutris's window is already open: the launch must not be forwarded to it.
cd ~ || exit 1
flatpak run net.lutris.Lutris > ~/gui.log 2>&1 &
sleep 10
echo "before: $(flatpak ps --columns=application | tr '\n' ' ')"
bash /opt/gctest/e2e.sh
echo "after: $(flatpak ps --columns=application | tr '\n' ' ')"
