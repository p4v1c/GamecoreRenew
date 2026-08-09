# The catalogue update channel

The catalogue is versioned apart from the application. `catalog/CATALOG_VERSION`
is its number, and it exists so that a dead Flathub app id can be corrected on
every box in the fleet inside 24 hours without cutting a release.

The alternative is what this replaces: `release.yml` fires on every push to
`main`, so fixing one string in one `pack.json` rebuilds the frontend, rebuilds
the PyInstaller wizard, publishes three assets and ships the whole application
to every box. Many moving parts, each of them a way for the fix to be delayed
or to break something unrelated.

## This directory holds one file, and only the public half

    catalog-signing.pub    base64, 32 raw bytes, an Ed25519 public key

**It is not committed today, and until it is the channel is off.** A box with
no trust anchor refuses every bundle — before fetching it — because a remote
catalogue that is not authenticated is a remote code execution primitive with a
pleasant API: it names the application the box installs and the one it launches,
so whoever holds the endpoint, the DNS or the TLS terminator holds the fleet.

Turning the channel on is therefore a deliberate act by whoever will hold the
key:

```
scripts/sign-catalog.py --new-key ~/gamecore-catalog.key   # outside the repo
git add catalog/_ota/catalog-signing.pub                   # the public half only
```

The private key never enters this repository, never enters CI, and never
reaches a box. `.gitignore` refuses the obvious filenames, and a test asserts
this directory holds nothing but the public key — both are safety nets against
an accident, not the control. The control is that the key lives somewhere else.

Rotating the key means cutting a release: a box trusts exactly the public key
its installed version shipped.

## Publishing a correction

```
$EDITOR catalog/ryujinx/pack.json          # add the surviving app id to appIds
echo 43 > catalog/CATALOG_VERSION          # STRICTLY greater than the last one
scripts/sign-catalog.py --key ~/gamecore-catalog.key --out catalog.bundle.json
# serve catalog.bundle.json at the URL the boxes have in GAMECORE_CATALOG_URL
```

A box refuses a bundle whose version is not strictly greater than the one it
already applied. That is not tidiness: yesterday's bundle stays validly signed
for ever, and replaying it is how somebody puts back the app id today's bundle
fixes. A signature cannot express freshness; only the version can.

## What a remote catalogue may say

Data only, with no opt-in — stricter than `config/catalog.d/`, where
`GAMECORE_TRUST_LOCAL_PACKS=1` exists because the operator can say "I put that
directory there myself". Nobody can say that about bytes off the network.

`postInstall`, `services`, `sources`, `packages`, `files` and `secrets` are
dropped on arrival, and a bundle is a single JSON document that has no way to
express a `generator.py`, a symlink or a file mode in the first place.

That is enough for what the channel is for. Correcting `install.appIds`,
`launch.args` or an extension list reaches the fleet in an afternoon. Shipping
new generator code stays a release, where it goes through review and CI.

## The three tiers

    catalog/                 shipped   the release
    <data>/catalog-ota/      remote    signed corrections, override shipped
    config/catalog.d/        local     the operator, overrides everything

The operator is last on purpose. A box whose owner pinned a pack by hand must
not have that undone by an endpoint, or the update channel is also a way to
overrule the person holding the machine.
