# The ISO blocker — **resolved**, kept as a record

**Raised 2026-08-09 against `main` = `7a5d62d`. Cleared the same day.**

For a while every text in this folder was unpublishable, because its opening
argument — "you don't have to install Arch first" — pointed at an ISO no release
had ever carried. That is no longer true, and this file stays because the way it
broke is worth keeping.

## Current state — verified

Release `v1.0.157` carries the image:

```
gamecore-1.0.157-x86_64.iso.00.part   1 992 294 400
gamecore-1.0.157-x86_64.iso.01.part     538 345 472
gamecore-1.0.157-x86_64.iso.sha256             94
REASSEMBLE.txt                                428
```

The run for `d8c3d97` is the first green `release.yml` since the `iso` job was
added — and the first that took 17 minutes rather than failing in 5, which is
itself the signal that an image was actually built. The split into `.part` files
is the nominal path, not a rare case: the image is over GitHub's 2 GiB asset
limit.

**Still not verified by anyone:** that the reassembled image boots. `sha256sum -c`
passing proves the transfer, not that UEFI will start it. Nobody has burned it.

## What was actually broken — two causes, stacked

The `iso` job never reached its upload step. Every run died on the same
`build.sh` guard, the one refusing to produce an image whose Electron shell would
be missing. The guard was doing its job; the defect was upstream of it. And there
were two, the first hiding the second.

**1. npm ≥ 11.6 no longer runs a dependency's install scripts by default** unless
`package.json` declares them under `allowScripts`. Electron's `postinstall` is
precisely the one that downloads the ~180 MB binary. Blocked, it downloads
nothing, **npm carries on and exits 0**, and the guard falls forty minutes later.
The only trace is a `npm warn install-scripts` line.

**2. Electron 31 cannot unpack its binary under Node 26.** It uses extract-zip
2.0.1 / yauzl 2.10, and on Node 26 the unpacking hangs without ever resolving its
promise: node drains its event loop and **exits 0** having written `dist/locales`
and nothing else. No error, no non-zero exit code. The symptom is the same guard
with the same message — indistinguishable from cause 1.

The measured matrix, same zip, same npm:

```
Node 26.4 + npm 11.18, without allowScripts -> no binary   (the CI's state)
Node 26.4 + npm 11.18, with allowScripts    -> no binary   (352 KB)
Node 22.21 + npm 11.18, without allowScripts -> no binary
Node 22.21 + npm 11.18, with allowScripts    -> 260 MB, a 182 MB binary
```

Both fixes are necessary, and together sufficient. Fixing only the first would
have left the job red — and learning that costs a full release cycle.

## The fixes that landed (`0a27646`, then `d8c3d97`)

- `electron/package.json` declares `allowScripts: { electron: true }` —
  versioned and reviewable, rather than an environment variable in the workflow
  nobody will find again. It holds for a local build too.
- The workflow installs `nodejs-lts-jod` (22.x) instead of the rolling `nodejs`.
  The ISO itself still ships the rolling `nodejs` and that is harmless:
  `dist/electron` is a self-contained Chromium build, and the frontend bundle
  built under Node 22 is bit-identical to the one built under Node 26.
- `build.sh` now rejects a Node outside 18–22 **before** the forty minutes of
  `pacstrap`, instead of letting the symptom surface at the guard where it is
  indistinguishable from the npm policy problem. The upper bound is the last
  version measured working, not the first known broken: 23, 24 and 25 were never
  tested.
- `d8c3d97` then fixed two package names Arch had changed underneath us:
  `nvidia` became `nvidia-open` with driver 590, and `wireless_regdb` never
  existed — it is `wireless-regdb`. `pacstrap` was failing on `target not found`
  several minutes in.

> **The trap that would have replayed the same outage silently.** Do not generate
> the `allowScripts` entry with `npm install-scripts approve electron`. By default
> that command writes an entry **pinned to the installed version** —
> `"electron@31.7.7": true`. But `electron/package.json` depends on `^31.0.0`: at
> the first Electron bump the pin stops matching, the postinstall is blocked
> again, and the ISO breaks exactly as it did — a month later, with nothing having
> been touched. Write the entry **by name**, or use
> `npm install-scripts approve electron --no-allow-scripts-pin`.

## What this changes for the texts in this folder

Every file in `submissions/`, plus `site.md` and `video-script.md`, was written
to lead through the graphical installer (`gamecore-installer`) and carries a
`> **Now that the ISO ships**` box with the wording to substitute.

**That condition is now met.** Those substitutions are pending and are the
human's to apply when sending each text — they change the pitch, so they are not
applied automatically here.
