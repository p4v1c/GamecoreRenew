#!/usr/bin/env bash
# ================================================================
#  boot-timeline.sh — where a boot's seconds actually went.
#
#  Reads the journal of the current boot (or `-b -1` for the previous one) and
#  prints the moments that matter, in order, with the gap between each. Nothing
#  is written, no service is touched, no root needed for the parts that matter.
#
#  What it is FOR: a box that takes too long to reach its dashboard is not slow
#  everywhere — it is slow in one place, and which place differs from machine to
#  machine. This says which. On one box it is the X server, on another the ROM
#  library, on a third a television that resynchronises twice.
#
#  What it is NOT for: choosing a delay. Nothing in GameCore waits for a
#  duration any more — the shell waits for `/api/ready`, the interface waits
#  for the facts in frontend/src/lib/boot.ts — and a number read here has
#  nowhere to be put back. If a step is slow, the fix is to move it off the
#  boot path, not to wait for it more politely.
#
#  Usage:  scripts/boot-timeline.sh [-b <boot>]
# ================================================================
set -uo pipefail

BOOT="${2:-0}"
[[ "${1:-}" == "-b" ]] || BOOT=0

command -v journalctl >/dev/null 2>&1 || { echo "no journalctl on this machine"; exit 1; }

echo "GameCore — boot timeline (journal boot ${BOOT})"
echo

# Each line: <label>|<journal matcher>. The matcher is a plain grep over the
# boot's journal, so a machine that names something differently prints one
# blank line rather than a wrong number.
MARKERS=$(cat <<'LIST'
kernel is up|Linux version
display manager|Simple Desktop Display Manager|Started.*sddm
X server ready|X.Org X Server
console session|\[gamecore-session\]
backend started|Started GameCore
shell waiting|\[boot\] WAITING_BACKEND
interface loading|\[boot\] LOADING_UI
interface ready|\[boot\] RUNNING
LIST
)

FIRST=""
PREV=""
while IFS='|' read -r label pattern; do
  [[ -n "$label" ]] || continue
  # Searched forward only. Without `--since`, `grep -m1` finds the first match
  # anywhere in the boot — including one that PRECEDES the previous marker,
  # which prints a negative gap and reads as nonsense.
  if [[ -n "$PREV" ]]; then
    line=$(journalctl -b "$BOOT" --since "@$PREV" --no-pager -o short-unix 2>/dev/null \
           | grep -m1 -E "$pattern" || true)
  else
    line=$(journalctl -b "$BOOT" --no-pager -o short-unix 2>/dev/null \
           | grep -m1 -E "$pattern" || true)
  fi
  if [[ -z "$line" ]]; then
    # Not every marker exists on every box: a machine with no console session
    # has no line for it, and that is an answer rather than a gap.
    printf '  %-20s %s\n' "$label" "—"
    continue
  fi
  ts=${line%% *}
  ts=${ts%.*}
  [[ -z "$FIRST" ]] && FIRST=$ts
  if [[ -n "$PREV" ]]; then
    printf '  %-20s +%-5ss  (total %ss)\n' "$label" "$(( ts - PREV ))" "$(( ts - FIRST ))"
  else
    printf '  %-20s %-6s  (start)\n' "$label" ""
  fi
  PREV=$ts
done <<< "$MARKERS"

echo
echo "The gaps are what to read. A large one is a step to move off the boot"
echo "path — never a delay to configure: nothing here is read by any code."
