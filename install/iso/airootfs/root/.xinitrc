#!/usr/bin/env bash
# The live session's X client list. `startx` execs this after the server is up.
#
# openbox first and in the background, the installer in the foreground with
# exec: X exits when THIS process exits, so the installer has to be the last
# one. Backgrounding the installer instead gives an X session that dies the
# instant it starts.
openbox &

exec /usr/local/bin/gamecore-iso-installer.sh
