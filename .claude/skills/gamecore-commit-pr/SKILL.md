---
name: gamecore-commit-pr
description: Commit, branch and pull-request rules for GameCore (GamecoreRenew), including the release hazards (every push to main publishes an OTA release; never workflow_dispatch release.yml from a branch). Use whenever committing, pushing, opening or merging a PR in this repo.
---

# GameCore commits and PRs

## Hazards — read first

- **Every push to `main` publishes a release** that boxes install over the air.
  Never push to `main` directly. Branch.
- **Never run `workflow_dispatch` on `release.yml` from a branch**: the
  publish step has no guard and releases a tag named after the branch — the
  fleet installs it.
- PRs have **no CI**. Run the checks locally (`gamecore-tests`) before asking
  for a merge.

## Branch

`feat/<topic>` · `fix/<topic>` · `refactor/<topic>` · `docs/<topic>` — English, kebab-case.

## Commit message

```
<type>(<area>): <what changed for the player or the dev, present tense>

<why: what broke, how, what the reader would otherwise re-derive.
2-6 lines. English.>
```

- Types: `feat` `fix` `refactor` `docs` `test` `chore` `ci` `revert`.
- Area = the touched part: `orbit`, `session`, `catalog`, `rpcs3`, `ota`…
- **English**, subject ≤ 72 chars, no trailing period.
- One logical change per commit; generated files with their source.
- Good: `fix(bluetooth): named devices first, in the paired list and the scan`
- Bad: `fix(orbit): les réglages d'Orbit reviennent` (French), `fix: stuff`, `wip`.

## PR

Title = the main commit subject. Body:

```
## What
- bullets
## Why
- the failure or the need, one line each
## Checked
- commands run + result (tests, check-docs, gen-catalog --check, on-box check if any)
## Not done
- what is left, if anything
```

Short. No narrative. Link the doc updated.
