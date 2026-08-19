# Session reports — the project's decision record

Each file here is the written outcome of one working session: what was
measured before anything was changed, which decisions were taken alone and
why, what was deliberately NOT done, and how to undo each change. They were
originally written in French as live working notes and translated to English
so that any developer — or any AI — picking the project up can replay the
reasoning, not just read the result.

Read them newest-first if you want the current state; oldest-first if you
want to understand how the box got here.

| file | session | what it decided |
|---|---|---|
| [bezels-per-console-phase1.md](bezels-per-console-phase1.md) | 2026-08-18 | the measurements that proved one bezel served three consoles — taken before a single line changed |
| [bezels-per-console-phase3.md](bezels-per-console-phase3.md) | 2026-08-18 | the owner's verification protocol and box-migration procedure for the per-console cascade |
| [bezels-per-console-report.md](bezels-per-console-report.md) | 2026-08-18 | the per-console bezel level: decisions taken alone, with how to undo each |
| [bezels-artwork-and-deposit-report.md](bezels-artwork-and-deposit-report.md) | 2026-08-18 | the shipped mGBA frames and the ROM-Manager deposit path; the two-roots test that caught a live-backend false positive |
| [refactoring-diagnostic.md](refactoring-diagnostic.md) | 2026-08-19 | dead code removed with proof, four facts converged to one copy each, the deliberate-duplication list, and the order-dependence flake killed at its root |

A rule these files follow, worth keeping for future entries: **every claim
names its evidence** (a command, a measurement, a failing test), and every
"do not do X" names the failure that taught it.
