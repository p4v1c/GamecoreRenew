# Game streaming — assessed, not shipped

> **Status: nothing is installed, and no addon exists.** This document is the
> result of asking whether a Moonlight-compatible streaming host fits the
> `api: 1` addon contract. It does not, for one reason that is not negotiable
> from the addon side, and this is the record of why — so the question is not
> re-opened from scratch in six months.

The production box has Sunshine installed by hand, service `disabled`, not run
for a month. It came from the owner, not from GameCore, and nothing in this
repository has ever referenced it.

## The conclusion first

A streaming host cannot be a GameCore addon under the contract as written,
because the contract says an addon **may not bind anything but loopback** and a
streaming host exists to accept connections from other machines. Everything else
about the fit is workable; this one is the whole point of the software.

That is a result, not a blocker to route around. Extending the contract to allow
LAN-bound addons is a decision about the security model — the model is one LAN
port (`docs/SECURITY.md`), and it is public and freshly settled. It is the
owner's call, not something to slip in with a feature.

## Which tool, if one is ever chosen

Not a foregone conclusion, so it was checked rather than assumed.

| | Sunshine | Apollo | Steam Remote Play | Parsec |
|---|---|---|---|---|
| Licence | GPL-3.0 | GPL-3.0 (Sunshine fork) | proprietary | proprietary |
| Flathub | yes — `dev.lizardbyte.app.Sunshine` | no | via the Steam Flatpak | no |
| Self-hosted | yes | yes | yes, tied to Steam | no, brokered by a vendor |
| Client | Moonlight (every platform, FOSS) | Artemis / Moonlight fork | Steam Link | Parsec client |
| Maintained | actively, by LizardByte | fork, smaller | by Valve | by Unity |

**Sunshine is the right choice if one is made.** It is the only candidate that is
simultaneously free software, packaged on Flathub (which is how every other
emulator on this box is delivered), and client-agnostic through Moonlight. Apollo
is a fork of it with a narrower audience. Parsec is proprietary and brokered
through a third party, which is the opposite of what this box is. Steam Remote
Play already works today through the existing Steam tile and needs nothing from
GameCore — worth saying plainly to anyone who just wants to stream to another
room, because it is the answer that costs nothing.

Nothing below depends on the choice: the mismatch is structural and every
Moonlight-compatible host has the same shape.

## Where it meets the contract, and where it does not

Measured against `api: 1` as the `_template` addon and the addon-model document
in `p4v1c/gamecore-addons` define it.

### Fits

- **`type: "service"` already exists** — headless daemon, no tile, no nav-bar
  link. Exactly the category. A streaming host does not need the contract to
  grow a new type.
- **`service: "user"` is already the norm.** Every current addon is a systemd
  *user* unit in `~/.config/systemd/user` with `WantedBy=default.target`. This
  was expected to be a gap and is not — and a user unit is in fact what a
  streaming host needs, since capture requires the graphical session.
- **Independent process, own unit, `Restart=on-failure`** — the addon model's
  central claim (a crash cannot take the TV down) holds here.
- **Registry and Addons screen** already carry every type, not just `web`.

### Does not fit

1. **Loopback only.** The contract's "may not" list is explicit: *bind anything
   but loopback*. A streaming host must answer Moonlight clients on the LAN.
   There is no configuration of Sunshine that satisfies both.
2. **Not an HTTP service.** The addon model is "an HTTP service with a static web
   UI", proxied by Caddy at a path prefix, with auth done by `forward_auth`.
   Moonlight speaks its own control protocol plus RTP over UDP. Caddy's reverse
   proxy cannot carry it, so the `path` field and the shared login do not apply —
   Sunshine authenticates with its own PIN pairing instead, which is a second
   auth system on the box.
3. **One port, and the wrong ones.** `addon.json` has a scalar `port`, and
   8770-8799 is the reserved addon range. Sunshine derives roughly fifteen ports
   by offset from a base of 47989: TCP 47984-47990 (control, and the HTTPS web UI
   on 47990), UDP 47998-48000 (video), 48010 (audio), 48100-48110 (control and
   input). Not expressible, and outside the range.
4. **The file contract does not describe it.** An addon is `server.py` +
   `web/index.html` + `requirements.txt` — a Python app whose checkout is what
   runs. Sunshine is a C++ Flatpak with its own bundled web UI. Its `install.sh`
   would install nothing and configure a Flatpak, which is a different thing
   wearing the same filename.
5. **The sandbox is wide.** The Flathub manifest requests `--device=all`,
   `--socket=wayland`, `--socket=fallback-x11`, `--socket=pulseaudio`,
   `--filesystem=home`, `--share=network` and `--talk-name=org.freedesktop.Flatpak`
   — the last of which lets it run commands on the host, outside the sandbox.
   That is inherent to screen capture and virtual input, not carelessness, but it
   is far past what any current addon asks for, and the contract has never had to
   have an opinion about it.

Points 2-5 are all arguably solvable with contract changes. Point 1 is the
security model.

## What is *not* the obstacle

Recorded because each looked like one:

- Not the user-vs-system service question — user units are already the norm.
- Not the missing tile — `type: "service"` covers exactly that.
- Not GPU access — the box already has a working Vulkan/VA-API stack, and the
  gaming user is in the groups the emulators need.

## If it is ever built, this is what it would owe `docs/SECURITY.md`

Not written there now, because writing ports into the security model for
software that is not installed would be a lie in the other direction.

- TCP 47984-47990, UDP 47998-48000, 48010, 48100-48110, all LAN-facing.
- **TCP 47990 is a second web UI on the LAN**, with its own credentials, outside
  Caddy and outside the shared login. It is the part that most deserves scrutiny:
  it configures what gets captured and can execute the commands in its app list.
- PIN pairing, held in Sunshine's own state, unrelated to the GameCore password.
- Whether UPnP is off. Sunshine can forward its own ports to the internet from
  inside the LAN; on a console in a living room that default deserves a decision.

## One-way link with mDNS, and it must stay one-way

Moonlight finds hosts by mDNS, and Sunshine talks to Avahi over D-Bus
(`--system-talk-name=org.freedesktop.Avahi` in its Flatpak manifest). The
`Failed to create client: Daemon not running` line in the box's journal was
Sunshine finding Avahi disabled.

mDNS is in the base install (`install/arch.sh`, `install/iso/packages.x86_64`)
because the box needs a name of its own — the ROM manager, the save manager and
the login page are all behind one DHCP address. That justification stands with no
streaming on the box at all, and **streaming must never become the reason mDNS is
there**: removing a streaming addon must not remove mDNS, and mDNS must not pull
in a streaming host. They are in separate repositories and neither declares the
other.
