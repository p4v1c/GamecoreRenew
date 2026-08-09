#!/usr/bin/env bash
# Live-ISO entry point: the first thing root runs after the tty1 autologin.
#
# It is reached from BOTH .zlogin and .bash_profile, and that is deliberate.
# archiso's own profile ships only .zlogin because releng sets root's shell to
# zsh; this profile does not pin a shell, and a root shell of /bin/bash reads
# neither .zlogin nor .zprofile. The symptom of getting that wrong is the worst
# kind: the ISO boots, autologin works, and you are sitting at a root prompt
# with no installer and no error anywhere to explain it.
#
# Both files source this one, so it must be idempotent — see the guard below.

# Only on the console we autologin on. An admin who switches to tty2 and logs in
# to look around must get a shell, not a second X server fighting the first one
# for the same GPU.
[[ "$(tty)" == "/dev/tty1" ]] || return 0 2>/dev/null || exit 0

# Sourced twice (a shell that reads both files, or a re-login after the operator
# quits X) would otherwise stack X servers.
[[ -n "${GAMECORE_ISO_SESSION_STARTED:-}" ]] && return 0 2>/dev/null
export GAMECORE_ISO_SESSION_STARTED=1

exec /usr/local/bin/gamecore-iso-session.sh
