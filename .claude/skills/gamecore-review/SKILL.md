---
name: gamecore-review
description: Review a GameCore (GamecoreRenew) diff, branch or the whole repo against the project's own rules (comments, docs, quality, naming, file size, tests, commits) and output a short findings report. Use when asked to review code, audit the repo, check a PR, or before merging.
---

# GameCore review

Output is a **report, straight to the point**: one line per finding.

## Scope

- Diff: `git diff origin/main...HEAD` (or the PR).
- Whole repo: run the automated pass, then sample the biggest / newest files.

## 1. Automated pass

```bash
ruff check .
python3 scripts/check-docs.py --all
python3 scripts/check-catalog.py && python3 scripts/gen-catalog.py --check
bash .claude/skills/gamecore-file-size/scripts/check-file-size.sh [--diff]
# French left in code comments / commit subjects
git diff -U0 origin/main | grep -nE '^\+.*(#|//|\*) .*\b(le|la|les|une|pour|est|pas|dans|avec)\b'
git log origin/main..HEAD --format=%s | grep -E '\b(le|la|les|une|pour|est|pas)\b'
```

## 2. Manual checklist (per skill)

| Skill | Question |
|---|---|
| gamecore-code-quality | right layer? one source of truth? no FastAPI in services? no hardcoded roots? |
| gamecore-file-size | any file grew past budget? functions > 50 lines? |
| gamecore-naming | names match the tables? events `domain:event`? |
| gamecore-comments | English, why, ≤ 3 lines? no commented-out code? |
| gamecore-docs | every new public name in its doc table? no line counts? |
| gamecore-tests | fix has a failing-first test? network marked? |
| gamecore-commit-pr | English conventional commits? nothing pushed to main? |
| gamecore-human-touch | UI or copy changed: slop-audit counts down? no AI tells added? |
| gamecore-legibility | UI changed: legibility-audit 0 `FAIL` on each touched theme × screen? |

Also run the generic reviews if available: `/code-review` (bugs),
`/simplify` (reuse), `/ponytail-review` (over-engineering).

## 3. Report format

```
# Review — <scope> — <date>
Verdict: <ship | fix first | rework>

## Blocking
- file:line — problem → fix

## Should fix
- file:line — problem → fix

## Nice to have
- …

## Numbers
- files over budget: N (list)   French comment lines: N   docs check: ok/ko
```

No praise paragraphs, no restating the diff. Every finding has a location and a fix.
