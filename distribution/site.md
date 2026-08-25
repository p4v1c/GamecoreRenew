# The site — enabling GitHub Pages from `docs/`

The site is [`../docs/index.html`](../docs/index.html), with
[`../docs/robots.txt`](../docs/robots.txt),
[`../docs/sitemap.xml`](../docs/sitemap.xml) and
[`../docs/.nojekyll`](../docs/.nojekyll).

**It is not served yet.** Enabling Pages is an action on GitHub's side, so it
falls to the human.

---

## Why a site when there is a README

Three things the repo alone cannot give, and they are the entire reason this page
exists:

1. **The `<title>`.** GitHub's page title is imposed: `GitHub -
   p4v1c/GamecoreRenew`. That is the blue clickable text in search results, and
   it is the single heaviest factor in a page's ranking. Here it reads:
   `GameCore — living-room emulation frontend for Arch Linux (PS3, PS4, Switch, Wii U)`.
2. **The meta description.** On GitHub it is `Contribute to p4v1c/GamecoreRenew
   development by creating an account on GitHub.` for as long as no About is
   filled in — and even once it is, GitHub decides how it is formatted.
3. **Indexing itself.** GitHub's `robots.txt` forbids crawlers on `/tree/` and
   `/blob/`. Only the default branch's README is indexable: the whole of the
   repo's documentation is invisible to a search engine. `github.io` does not
   carry that restriction.

## Enabling

1. `https://github.com/p4v1c/GamecoreRenew` → **Settings** → **Pages**
   (left sidebar).
2. **Source**: `Deploy from a branch`.
3. **Branch**: `main`, folder **`/docs`**. Save.
4. Wait one or two minutes, then check
   `https://p4v1c.github.io/GamecoreRenew/`.
5. **Only then**, paste that URL into the About block's Website field
   (see [`github-about.md`](github-about.md)). A Website field that 404s is
   followed by crawlers, so it is worse than an empty one.

## Checking the tags are the intended ones

```bash
curl -s https://p4v1c.github.io/GamecoreRenew/ | grep -E '<title>|name="description"'
```

## Speeding up indexing

Optional, and the only lever that turns "a few weeks" into "a few days": declare
the site in [Google Search Console](https://search.google.com/search-console)
(URL-prefix property, validated by HTML tag or by DNS), then submit
`sitemap.xml` there.

**For the human to do**: it needs a Google account and it publishes a property.

---

## What it exposes, and what it does not

Enabling Pages on `/docs` serves **all** of `docs/` on the web, not just
`index.html`: `SECURITY.md`, `TESTING.md`, `CONTROLLER_MODELS.md`,
`architecture/`, `themes/`.

Those files are already public — the repo is — so nothing new is exposed. The
difference is that they become **indexable**, which they were not behind GitHub's
`robots.txt`.

Two consequences, and only one deserves an action:

- `sitemap.xml` only declares `index.html`. The `.md` files are not submitted for
  indexing: served as plain text, they show up as a downloaded file, and someone
  landing on one from Google would see bare Markdown rather than a page. They
  stay reachable by direct URL, which is the intended behaviour.
- **`docs/SECURITY.md` becomes an indexable page describing the product's
  security model.** That is not a secret, and publishing your security model is
  good practice — but it is the one file in the set worth a deliberate reread
  before pressing Save, because it is the only one whose audience would change in
  kind. **For the owner to review.** I have not: judging what is publishable in
  the security model of your own machine is not a decision that delegates.

## The `og:image` screenshot

Still to add in `docs/index.html` — the comment in `<head>` says where and
under what constraints.
