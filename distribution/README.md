# Distribution — ready-to-publish material

**Nothing in this folder has been published.** No account created, no post sent,
no package submitted, no PR opened. Everything is written so that a human reads
it, decides, and sends it themselves.

That is deliberate and must stay that way: half of these channels (AlternativeTo,
awesome-*, r/linux_gaming) do not forgive a second submission. You get one shot,
and only once the front door holds.

---

## The ISO blocker is cleared — [`iso-blocker.md`](iso-blocker.md)

The opening argument of every text here is "you don't have to install Arch
first". For a while that was factually false: no release had ever carried an ISO,
because the `iso` job in `release.yml` failed on every one since it was added.

**That is fixed.** `v1.0.157` ships the image as split `.part` files with its
`.sha256`. The cause, the two stacked defects behind it, and the trap that would
have replayed it are in [`iso-blocker.md`](iso-blocker.md) — worth reading before
touching the ISO job.

One thing still nobody has done: **boot the reassembled image.** `sha256sum -c`
proves the transfer, not that UEFI starts it. Do that before pointing an audience
at it.

The texts below still lead through the graphical installer, and each carries a
`> **Now that the ISO ships**` box with the wording to substitute. Those
substitutions are **pending** — they change the pitch, so they are the sender's
to apply, not mine.

---

## The angle, identical everywhere

> A living-room box for the *recent* consoles — PS3, PS4, Switch, Wii U, Xbox
> 360 — with emulators that stay current, on an Arch that stays a real computer.

**Never "a Batocera alternative" as the main argument.** That is the comparison
on breadth: on number of supported systems, on project age, on community size, we
lose. The three points below are the only ground where the comparison is winnable,
and they are the ones to hold:

1. **Recent consoles first.** Thirteen systems, oriented at PS3/PS4/Switch/Wii
   U/Xbox 360 — not thirty 8-bit systems plus three modern emulators at the end
   of the list.
2. **Emulators that stay current.** They are Flathub Flatpaks, updated by
   Flatpak. RPCS3 and Ryujinx move every week; a frozen image freezes them until
   the distribution's next release.
3. **The machine stays a real machine.** It is a full Arch with a Plasma desktop
   behind it. `gamecore-session-select desktop` and you are on a PC. Nothing is
   read-only, nothing is locked down.

The fourth argument is quieter but it is the one that makes people stay: **the
controller configures itself, in every emulator**. That is the subject of the
video, and it is what demonstrates best in moving pictures.

---

## What is here

| File | What it is | Who sends it |
|---|---|---|
| [`iso-blocker.md`](iso-blocker.md) | The ISO outage, its two stacked causes, and the fix — **resolved**, kept as a record | read before touching the ISO job |
| [`github-about.md`](github-about.md) | Description, topics, repo URL | to paste into the GitHub settings |
| [`packaging/PKGBUILD`](packaging/PKGBUILD) | `gamecore-bin` package for the AUR | **do not submit** before reading [`packaging/README.md`](packaging/README.md) |
| [`video-script.md`](video-script.md) | Script for a 3-minute video | to shoot |
| [`submissions/alternativeto.md`](submissions/alternativeto.md) | AlternativeTo entry | to submit |
| [`submissions/awesome-emulators.md`](submissions/awesome-emulators.md) | Line + PR body for the awesome-lists | to open as a PR |
| [`submissions/reddit-emulationonlinux.md`](submissions/reddit-emulationonlinux.md) | r/EmulationOnLinux post | to post |
| [`submissions/reddit-linux_gaming.md`](submissions/reddit-linux_gaming.md) | r/linux_gaming post | to post |
| [`submissions/linuxfr.md`](submissions/linuxfr.md) | LinuxFr article — **written in French on purpose**, LinuxFr is a French-language site | to submit |

The site lives elsewhere, because it has to be served by GitHub Pages:
[`../docs/index.html`](../docs/index.html). See [`site.md`](site.md) to turn it
on.

---

## The publication order, and why this order

This is not a shopping list. Each step feeds the next, and two of them cannot be
undone.

1. ~~Fix the ISO blocker.~~ **Done** — but boot the reassembled image before sending anyone at it.
2. **The repo's About and topics.** Five minutes, reversible, and it is what every
   other link will point at. Today Google only has `Contribute to
   p4v1c/GamecoreRenew development by creating an account on GitHub.` — GitHub's
   default description, which is to say nothing.
3. **The Pages site.** It gives a clean URL to put in the About, and a `<title>`
   and a meta description we control — which the repo alone does not allow.
   GitHub blocks crawling of `/tree/` and `/blob/` in its `robots.txt`, so only
   the default branch's README is indexable.
4. **The video.** It has to exist before the posts: in this niche it ranks better
   than any page, and it is what creates searches for the name. A post without a
   video demo gets "any screenshots?" as its first comment.
5. **The Reddit and LinuxFr posts.** One channel a day, not all three the same
   day: posting everywhere at once reads as spam, and you only get one first post
   per community.
6. **AlternativeTo and the awesome-lists.** Last: they are directories, they
   benefit from a project that already has traces elsewhere, and a submission
   refused for "not established enough" is not easily retried.

**The AUR is not in this list.** See [`packaging/README.md`](packaging/README.md):
the PKGBUILD is written and syntactically checked, but it has never been built,
and shipping a broken AUR package is the worst possible first impression on that
particular channel.

---

## What the name costs, and the only thing to decide

"GameCore" is already taken several times over: a Java game engine, a 3D IDE, a
Mac engine on SourceForge, a YouTube channel, and the GitHub user `@GameCore`.
Fighting over that word is lost in advance — it will not rank, whatever we write.

On top of that the repo is called `GamecoreRenew` and the product `GameCore`: the
two dilute each other, and neither accumulates.

**This is not mine to settle, and there is only one decision to make: rename the
repo to `GameCore`, or not.**

- **Rename**: GitHub sets a permanent redirect, existing `git remote`s keep
  working, and the product name and the repo name stop diluting each other. It
  does break already-distributed release URLs and anything hardcoding
  `GamecoreRenew` — to check beforehand.
- **Don't rename**: nothing breaks, and we carry on with two names.

Either way, **the SEO strategy of these texts does not change**, because it does
not bet on the name: it bets on the long queries people actually type, which
today have almost no good answer:

- `ps3 emulator living room tv frontend`
- `rpcs3 gamepad autoconfig`
- `switch emulator couch setup linux`
- `arch linux emulation frontend flatpak`
- `batocera alternative recent consoles`

That is why the site's `<title>` and the About description both carry
"living-room emulation frontend for Arch Linux" next to the name, and not just
"GameCore". The name alone is nobody's search query; the description is one.
