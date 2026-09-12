# Phase 1 — the installer and uninstaller, audited for the Store

**Session:** 2026-09-12. **Base:** `59ea18d` (merge of PR #60).
**Branch:** `feature/gamecore-store`. **Clone:** `~/gamecore-dev/gamecore-store`.

> **Where this document sits, written after the fact.** The Store roadmap puts
> the installer and uninstaller at **step 19**, after the catalogue, the Store
> core, the search and acquisition providers and the importer. This audit was
> produced at **step 2**, before any of them — the brief asked for it early. So
> read it as step 19's input, delivered ahead of its turn, and not as a verdict
> on work that had already been done.
>
> Two consequences of that inversion, both worth knowing before trusting a
> section below:
>
> **S1 and S2 do not bite the Store as it was finally defined.** They were
> written against a reading in which the Store *installs software from the
> network*. It does not: it is core code — a backend router and a frontend
> screen — that downloads **game files** into `<DATA>/emu/<system>/`, and the
> pack channel it never enters is the one S1 describes. S2's `/api/*` 403 is
> Caddy's, and the television does not go through Caddy (`Caddyfile:16`), so a
> Store screen inside a theme reaches the core directly. Both findings stay
> true about the code; they simply describe a road this feature does not take.
> They return the day a Store page has to work from a phone on the LAN.
>
> **S3, S5, S6 and S7 do bite, at steps 10 and 12.** A managed Prowlarr and a
> Real-Debrid provider are a daemon, a LAN-facing port and credentials that
> change after install. That is exactly what those four sections are about.
>
> **And the ground under one finding has shifted.** §S8 is still accurate —
> there is no AUR provider, and `github-archive` still writes into the install
> root. What changed is how much the `pacman` provider now carries. At
> `59ea18d` no emulator pack used it at all; at `c1a4df6` the catalogue gained
> 18 RetroArch packs and **17 of them install through `pacman`** (`retroarch`
> plus one `libretro-*` core), making it the majority provider. That does not
> contradict S8, it loads it: two knock-on effects the uninstaller has not
> caught up with —
> `uninstall.sh:811` still tells an operator with no manifest that *"GameCore
> realistically adds only: caddy unclutter"*, which is now false by about
> eighteen packages; and `--remove-packages`, until now a near-empty option,
> becomes the flag that decides whether a box keeps RetroArch. Neither is a
> bug today. Both are step 19's work, and they are why this document will need
> a second pass rather than a re-read.

Read-only audit. `install/arch.sh`, `install/uninstall.sh` and `update/linux.sh`
were **not executed**, in any mode, `--dry-run` included: the machine carries a
live GameCore install and dry-run is a reduced risk, not an isolation boundary.
Nothing under `/opt`, `/userdata`, `/var/lib/gamecore`, `/etc`, `/usr/local/bin`
or `~/.var/app` was read for state, written, backed up or chmod'ed. No service
was restarted. No commit was made.

The question asked: **what does the Store have to pass through, and where does
the current code not carry it?** Not "is the installer good" — it is unusually
careful, and most of what follows is a consequence of decisions that are right.

First, the fact that reframes the whole chantier: **there is no Store code in
this tree.** `grep -ril` over the repo for `prowlarr`, `torrent`, `qbittorrent`,
`jackett`, `indexer` returns three unrelated hits (`gamemedia/identity.py`, two
layout-toggle scripts). So the expectations written into this chantier's
guardrail — a managed Prowlarr removed only when the manifest proves it, an
external one kept, Store secrets planned for deletion — describe a target
state. None of them can pass or fail against today's code. What can be audited
is the *seam*: the mechanisms a Store component would have to enter, and
whether they are shaped to receive it.

---

## 0. The five mechanisms the Store has to enter

| mechanism | where | what it decides |
|---|---|---|
| the install manifest | `/var/lib/gamecore/` — `manifest.env`, `pacman-installed`, `flatpak-installed`, `flatpak-overrides` | what the uninstaller is allowed to remove |
| the uninstaller's decision model | `install/uninstall.sh` | manifest-driven for packages; **hand-written lists** for everything else |
| secrets | `catalog/*/pack.json:secrets` → `applier.py:91` → pack files | collected once by the wizard, expanded as `@KEY@` tokens |
| providers | `providers.py:325` — four of them | how an artifact is obtained |
| the trust tiers | `catalog/`, `<DATA>/catalog-ota/`, `config/catalog.d/` | what a pack coming from elsewhere is allowed to do |

The manifest's rule, stated in `manifest.py`'s own docstring and worth keeping
in front of the Store work: **record only what was NOT already present.** It is
the entire reason the uninstaller can tell "we installed caddy" from "caddy was
already here", and the reason the guardrail's "external Prowlarr is kept"
expectation is achievable at all.

---

## 1. Findings

Ordered by how much each one changes the *shape* of Phase 2, not by severity.

### S1 — The remote tier cannot install anything, on purpose

`backend/services/catalog/ota.py:68`

```
FORBIDDEN_BLOCKS = ("postInstall", "services", "sources", "packages",
                    "hostAccess", "files", "secrets")
```

and `backend/services/catalog/loader.py:50` strips the same list (minus `files`
and `secrets`) from local packs unless `GAMECORE_TRUST_LOCAL_PACKS=1`.

`docs/architecture/10-catalog-and-install.md:436` gives the reasoning: *"Data
only, with no opt-in. Nobody can say 'I put that directory there myself' about
bytes off the network."* An unauthenticated remote catalogue is described,
correctly, as a remote-code-execution primitive.

**Consequence.** If "the Store" means *a channel that delivers installable
content from the network*, it collides head-on with a deliberate, documented
decision — and the Ed25519 channel that could carry it is still off:
`catalog/_ota/catalog-signing.pub` is not committed and `CATALOG_VERSION` is
`1` (doc 10:447). Note this repo's memory that pack signing was abandoned once
already.

**The decision Phase 2 cannot avoid:** is the Store a *browser* over sources
the release already trusts (Flathub app ids, GitHub releases named in a shipped
pack), or a *delivery channel*? The first needs no new trust anchor. The second
needs the key custody question answered before a line is written.

### S2 — A LAN browser cannot call the core's API

`install/system/Caddyfile:69` — inside the authenticated `handle`:

```
handle /api/* {
    error 403
}
```

Every addon instead gets its own loopback port and a path prefix: `:8770`
(`/roms`), `:8771` (`/rpcs3`), `:8772` (`/saves`) — Caddyfile:82-88, contract
doc 12:101.

**Consequence.** A Store screen served to a phone or laptop on the LAN cannot
reach `/api/store/*` on the core. Its browser-facing half has to be an
addon-shaped process on its own port (`:8773` is the next free one), or the
Caddyfile needs an exemption — and Caddyfile:50 records what the last
wildcard exemption cost: `@public` had to be enumerated because `/api/auth/*`
also exposed `/api/auth/change-password` to the whole LAN.

### S3 — A pack cannot declare a system service; an addon can

`catalog/_schema/pack.schema.json:552` — `"scope": { "const": "user" }`.
`install/bin/gamecore-addon:221-224` — an addon whose `addon.json` says
`service: system` is installed with root and lands in
`/etc/systemd/system/gamecore-addon-<id>.service`.

**Consequence.** A managed Prowlarr — a system unit, a service user, a state
directory outside anyone's `$HOME` — cannot be expressed as a catalogue pack at
all. `hostAccess` is the only root-applied pack block and it is a closed enum of
two booleans (`uinput`, `ptrace`).

### S4 — An addon cleans itself up; a pack is cleaned up by hand

The uninstaller is **generic** for addons: it reads `<DATA>/config/addons.json`
and calls `gamecore-addon remove <id>` for each entry (uninstall.sh:318-347),
then sweeps `gamecore-addon-*.service` in both scopes (:371 user, :392 system).

For packs it is **four hand-written lists**:

| list | line | covers |
|---|---|---|
| `USER_UNITS=(embertv.service gamepad-tv-bridge.service)` | 359 | pack `services` |
| `safe_rm /opt/Twitch-TV /opt/gamepad-tv-bridge /opt/Stremio /opt/gamecore-addons` | 680 | pack `sources` |
| `safe_rm …/.mozilla/firefox/youtube-tv …/twitch-tv` | 669 | pack `files` |
| `safe_rm …/.local/share/gamecore/layout-toggle` | 382 | pack `files` |

I enumerated every `sources`, `services` and `files` destination declared by
the twenty packs and compared them to those four lists. **Coverage is complete
today** — twitch, stremio, youtube, azahar and melonds are all accounted for,
including the conditional azahar/melonds unit test at :360-365 that skips a
standalone daemon belonging to a user who never selected the emulator.

So this is not a bug. It is that the Store would be the sixth entry in lists
that no test defends. Nothing fails if it is forgotten; the failure surfaces on
somebody's box, after an uninstall, as a service that still runs.

**The precedent for the fix is in this repo.**
`backend/tests/test_catalog_consumers.py:86`,
`test_no_installer_hardcodes_a_flatpak_config_path`, exists because the same
map lived in four files and grew a phantom directory. The same shape applies:
a `catalog-query.py uninstall-targets` subcommand (the script already answers
`config-dest`, `flatpaks`, `sandbox`, `packages`…) plus a test asserting that
every declared destination appears in `uninstall.sh`.

### S5 — The one-LAN-port invariant has no enforcement but the bind address

`grep -rn 'ufw\|iptables\|firewalld\|nft '` over `install/` and `update/`
returns **nothing**. There is no firewall. `docs/SECURITY.md:7` makes the check
an observation — *"`ss -tlnp` must show exactly one non-loopback port"* — and
`docs/SECURITY.md:168` records what happens when a component ignores it:
EmberTV listened on `0.0.0.0:8097` with no auth, *"which meant any device on
the Wi-Fi could post to Twitch as the owner"*.

**Consequence.** Any Store daemon that binds `0.0.0.0` becomes the second LAN
port silently. An indexer manager is precisely the kind of service that ships
with a wide default bind (Prowlarr's `BindAddress` default and its `:9696` are
an upstream fact I could not verify offline here — verify before writing the
unit, not after). The EmberTV route at Caddyfile:97-118 is the working pattern:
loopback-only upstream, reached at a prefix behind the shared login, with
`header_up Host {hostport}` because the upstream's CSRF guard compares Origin
to Host.

### S6 — There is no runtime secret store

Secrets are collected **once**, interactively (`arch.sh:279-294`) or from the
unattended conf, then expanded as `@KEY@` tokens into pack files
(`applier.py:91-93`), with `when: secrets.KEY` choosing between a real config
and a demo one (`applier.py:104-115`, the twitch pack's two `files` entries).
Install-time keys that the backend needs later go into one drop-in,
`chmod 600`, at `arch.sh:1168-1182`. The only *managed* runtime secret is the
web login: `config/auth.json` + `config/auth_secret`, with a rotation path
(`gamecore-addon auth-reset`).

**Consequence.** A Store needs credentials that change after install — an
indexer added in June, a key rotated in July. Nothing in the wizard model
supports that: re-running the installer to add an indexer is not a story
anybody will accept. `ADDON_DATA_DIR` (`<DATA>/addons/<id>/`, created before
the hook runs, doc 12:57) is the only writable, OTA-surviving,
backup-included home that exists today.

### S7 — `<DATA>/addons/<id>/` is never swept by the uninstaller

`uninstall.sh:824` removes exactly two data-root files by name:

```
safe_rm "$GC_DATA/config/auth.json" "$GC_DATA/config/auth_secret"
```

and the comment above it says why: *"leaving an argon2 hash and an HMAC key
behind after removal is not acceptable."* That reasoning does not extend to
addon data. On a split-root box `$GC_DATA` is **never** deleted, `--purge`
included (:835-836), and `config/` is preserved by default anyway (:850).

The script already anticipates the failure mode — :315-317 warns that addons
registered with the CLI gone *"cannot uninstall themselves"* and tells the
operator to check `/opt/gamecore-addons` — but there is no equivalent sentence,
and no sweep, for the data directory where an addon's secrets actually live.

**Consequence.** If the Store keeps indexer credentials in
`<DATA>/addons/store/` and its own `uninstall.sh` hook fails, or the CLI was
already removed, those credentials survive the uninstall silently. So does
`config/addons.json`, which keeps listing the addon.

### S8 — No AUR provider, and `github-archive` writes into the install root

`providers.py:325` — the registry is exactly four: `flatpak`, `github-asset`,
`github-archive`, `pacman`. `grep -rn 'yay\|paru\|makepkg\|aur.archlinux'` over
`install/`, `backend/`, `update/`, `scripts/` returns nothing.

**Consequence.** A component that Arch ships only through the AUR cannot be
installed by the `pacman` provider — `_pacman_install` (`providers.py:79`) runs
plain `pacman -S`. That leaves `github-archive`, which extracts into
`ctx.gamecore_path / spec["dest"]` (`providers.py:271`) — the tree the OTA
replaces wholesale and that doc 12:18 says is *"aiming at being a read-only
mount"*. A daemon whose state directory sits next to its binary therefore
breaks twice: wiped on update, unwritable later.

### S9 — `assets-installed` is dead code

`manifest.py:33` declares `ASSET_MANIFEST`, `manifest.py:91` defines
`record_asset()`, and a `grep -rn 'record_asset\|assets-installed\|
ASSET_MANIFEST'` across the tree finds **no caller** — only those two
definitions. The docstring promises it is *"a record for `verify` and for the
hot-install path"*; nothing writes it, so `verify` cannot read it.

Harmless today, because every provider writes inside `GAMECORE_PATH` and the
uninstaller deletes that wholesale. It stops being harmless the first time a
component installs outside the install root — which is what S8 pushes the Store
towards.

### S10 — The OTA never updates a companion in `/opt`

`update/linux.sh` contains no `git` invocation and no `/opt/<companion>` path
(the only hit is the `GAMECORE_PATH` default at :19 and a comment at :205).
Pack `sources` are `git_sync`'d at install time only.

**Consequence.** A Store shipped as a source clone in `/opt` would be installed
once and never updated — the same class of trap as this box's melonDS lesson,
where GameCore never updates an emulator it has already installed.

### S11 — Installer secrets survive outside `/tmp`

`uninstall.sh:713` shreds `/tmp/gamecore-install-*.conf`, correctly noting it
holds the Twitch secret, the TheGamesDB key and the web password in cleartext.
But `arch.sh:218` accepts `--unattended <f>` at **any** path.

The GUI is fine: `gamecore_installer.py:532` uses `mkstemp(prefix=
"gamecore-install-", suffix=".conf")`, chmods it `600` and unlinks it itself
(:643) — the shred glob is a net for a wizard that crashed. Only a
hand-written conf is exposed. Worth naming here because the Store will add
indexer credentials to that same file if it follows the wizard pattern.

---

## 2. What this means for Phase 2's shape

Not code, and not a decision I get to take alone — but the audit points one
way, and the reasons are all above.

**The addon contract carries the Store; the catalogue pack does not.** An addon
may run a system service (S3), gets a writable data directory that survives the
OTA and is included in backups (S6), removes itself through a generic path the
uninstaller already exercises (S4), and is reachable from the LAN on its own
port behind the same login without touching the `/api/*` 403 (S2). A pack gets
none of those and would add a sixth entry to four undefended lists.

Three things the addon route does not solve, which Phase 2 has to answer
explicitly:

1. **What the Store installs, and under whose trust.** S1 is not a gap to
   patch — it is a boundary somebody has to decide to cross or not.
2. **A manifest record for a managed component.** "Remove Prowlarr only if we
   installed it" needs the same treatment caddy got: `arch.sh:1318-1331` is the
   worked example, including the two traps recorded there — a packaged config
   file always exists on a fresh install, and `is-active` is true on the second
   run of an idempotent installer, so a naive check records GameCore's own
   service as pre-existing.
3. **A sweep for addon data on uninstall** (S7), with the same argument that
   justifies removing `auth_secret`.

## 3. What was deliberately not done

- No execution of `install/arch.sh`, `install/uninstall.sh` or
  `update/linux.sh`. No `--dry-run` either.
- No fixture harness or fake-`PATH` suite built yet: there is no Store code to
  exercise, and a dry-run test of today's uninstaller would assert the
  behaviour of code this chantier has not written.
- No file changed outside this report. No commit, no push, no merge.
- Prowlarr's default bind address and port are stated as an upstream fact to
  verify, not as a measurement taken here.
