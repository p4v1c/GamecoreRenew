#!/bin/sh
# Push the working branch, retrying on network failure (2s, 4s, 8s, 16s).
cd /home/user/GamecoreRenew || exit 1
[ "$(git rev-parse --abbrev-ref HEAD)" = "claude/modest-noether-4ipr9j" ] || { echo "wrong branch"; exit 1; }
for d in 0 2 4 8 16; do
  [ $d -gt 0 ] && sleep $d
  git push -u origin claude/modest-noether-4ipr9j && exit 0
done
exit 1
