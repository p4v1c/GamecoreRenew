#!/usr/bin/env bash
# List tracked code files over the GameCore line budget (warn 600, fail 800).
# Usage: check-file-size.sh [--diff [base]]   (default base: origin/main)
set -euo pipefail

WARN=600
LIMIT=800
EXEMPT='(^backend/services/gamemedia/(gamemedia|gamescrape)\.py$|^install/generated/|catalog_data\.py$|/tests/fixtures/|/seed/|gamecontrollerdb\.txt$|package-lock\.json$|^LICENSE$|^CHANGELOG\.md$|^install/(arch|uninstall)\.sh$)'
CODE='\.(py|ts|tsx|js|mjs|sh|css)$|^install/bin/|^update/'

if [[ "${1:-}" == "--diff" ]]; then
  files=$(git diff --name-only --diff-filter=AM "${2:-origin/main}"...HEAD)
else
  files=$(git ls-files)
fi

report=$(while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  grep -qE "$CODE" <<<"$f" || continue
  grep -qE "$EXEMPT" <<<"$f" && continue
  n=$(wc -l <"$f")
  limit=$LIMIT; warn=$WARN
  # Tests get 1.5x.
  if [[ "$f" == *test* ]]; then limit=$((LIMIT * 3 / 2)); warn=$((WARN * 3 / 2)); fi
  if (( n > limit )); then echo "FAIL $n $f"
  elif (( n > warn )); then echo "WARN $n $f"; fi
done <<<"$files" | sort -k2 -rn)
[[ -n "$report" ]] && echo "$report"
! grep -q '^FAIL' <<<"$report"
