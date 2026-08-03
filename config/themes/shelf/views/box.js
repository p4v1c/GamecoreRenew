/**
 * The box, assembled.
 *
 * The backend already did the hard part. `WARM_MEDIA` pulls down `box-front`,
 * `box-spine` and `box-back` for the whole library once the covers have landed
 * — its own comment calls them "the three faces the 3D box is built from" — so
 * nothing here scrapes, guesses or draws artwork. This file is geometry: six
 * faces, a depth, and a rotation.
 *
 *      ┌───────────┐
 *     ╱           ╱│     front  = box-front   (W × H)
 *    ┌───────────┐ │     spine  = box-spine   (D × H, the left face)
 *    │           │ │     back   = box-back    (W × H)
 *    │   front   │ ╱      top · bottom · opening edge — cardboard. No artwork
 *    │           │╱        exists for them because none is printed on a box.
 *    └───────────┘
 *
 * ── W and H come from the artwork, not from a token ────────────────────────
 * A SNES box is landscape, a PS1 box is portrait, a Mega Drive box is neither.
 * Fixing a ratio would crop or letterbox two thirds of a real collection, so
 * the front is measured on load and the whole solid is built from what it
 * reports. Depth follows width, the way it does on a shelf.
 *
 * ── Why a spine is not a box ───────────────────────────────────────────────
 * Twenty solids is sixty images and sixty compositing layers, for nineteen
 * boxes showing one face each. An unfocused game *is* its spine — one `<img>`,
 * the exact face a real shelf shows you. The solid is built for the one box
 * that is turned towards you.
 */
import { pick, jacket } from '../lib/dossier.js'
import { title, stamp } from '../lib/names.js'
import { flat } from '../lib/accent.js'

/** Portrait, the commonest cover shape — held until the front image measures. */
const RATIO_UNKNOWN = 0.72

/** Stable per title: the printed spine's colour, for a game with no scan. */
const hueOf = (s) => {
  let h = 0
  const str = String(s || '')
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 3600
  return h / 10
}

export const createBox = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  /**
   * One game on the shelf, edge-on.
   *
   * `box-spine` is warmed for the whole library, so in the normal case this is
   * a file already on disk. A game nobody ever scanned falls back to a printed
   * spine rather than a gap — and since a real cardboard spine is a black
   * field with a coloured wordmark, the shelf stays level either way.
   */
  const Spine = ({ systemId, game, on, onClick }) => {
    const [scan, setScan] = useState(true)
    useEffect(() => { setScan(true) }, [game.filename])

    const name = title(game.display_name)
    const src = sdk.api.media.url(systemId, game.filename, 'box-spine')

    return html`
      <button class="cz-spine" data-on=${on ? '1' : '0'} data-scan=${scan ? '1' : '0'}
              onClick=${onClick} style=${{ '--spine-h': String(hueOf(name)) }}
              aria-label=${name}>
        ${scan
          ? html`<img src=${src} alt="" onError=${() => setScan(false)} />`
          : html`
            <span class="cz-spine-print">
              <span class="cz-spine-cap" />
              <span class="cz-spine-name">${name}</span>
              <span class="cz-spine-foot" />
            </span>`}
      </button>`
  }

  /**
   * The turned box: a real solid, rotated by CSS.
   *
   * Flipping is a rotation of one object, not a cross-fade between two
   * pictures — the box carries on turning the way it was already going, past
   * its opening edge, and stops on the back. That is the whole reason this is
   * assembled rather than composited: a flat image cannot be turned over.
   */
  const Face = ({ systemId, game, meta, media, flipped }) => {
    const [ratio, setRatio] = useState(RATIO_UNKNOWN)
    const [frontDead, setFrontDead] = useState(false)
    const [spineDead, setSpineDead] = useState(false)

    // A cover can fail in two ways, and only one of them raises `onError`.
    // The other is a file that loads perfectly and contains no picture — a
    // scraper's chroma-key plate — which has to be looked at to be recognised.
    // Both land on `frontDead`, because from here they are the same fact: this
    // game has no front, print one instead.
    useEffect(() => {
      setRatio(RATIO_UNKNOWN)
      setFrontDead(false)
      setSpineDead(false)
      if (!game) return
      let live = true
      flat(jacket(systemId, game.filename)).then((blank) => {
        if (live && blank) setFrontDead(true)
      })
      return () => { live = false }
    }, [systemId, game?.filename])

    if (!game) return null

    const name = title(game.display_name)
    const front = jacket(systemId, game.filename)
    const spine = sdk.api.media.url(systemId, game.filename, 'box-spine')
    const back = pick(sdk, systemId, game.filename, media, ['box-back'])

    const measure = (e) => {
      const { naturalWidth: w, naturalHeight: h } = e.target
      if (w && h) setRatio(Math.max(0.45, Math.min(1.9, w / h)))
    }

    return html`
      <div class="cz-box" data-flipped=${flipped ? '1' : '0'}
           style=${{ '--ratio': String(ratio) }}>

        <div class="cz-f cz-f-front">
          ${frontDead
            ? html`
              <div class="cz-noart">
                <span class="cz-noart-name">${name}</span>
                <span class="cz-noart-note">No cover scanned</span>
              </div>`
            : html`<img src=${front} alt=${name} onLoad=${measure}
                        onError=${() => setFrontDead(true)} />`}
        </div>

        <div class="cz-f cz-f-back">
          ${back
            ? html`<${BackScan} src=${back} name=${name} systemId=${systemId}
                                game=${game} meta=${meta} media=${media} />`
            : html`<${BackPrint} systemId=${systemId} game=${game} meta=${meta} media=${media} />`}
        </div>

        <div class="cz-f cz-f-spine" data-scan=${spineDead ? '0' : '1'}
             style=${{ '--spine-h': String(hueOf(name)) }}>
          ${spineDead
            ? html`<span class="cz-spine-name">${name}</span>`
            : html`<img src=${spine} alt="" onError=${() => setSpineDead(true)} />`}
        </div>

        <!-- The three faces nobody prints: the opening edge and the two ends.
             Cardboard, a fold line, and the shadow the shelf casts on them. -->
        <div class="cz-f cz-f-edge" />
        <div class="cz-f cz-f-top" />
        <div class="cz-f cz-f-bottom" />
      </div>`
  }

  /**
   * The scanned reverse — when there really is one.
   *
   * This is where the green came from. `box-back` is the least reliable file a
   * scraper produces, and when it has nothing it does not omit it, it returns a
   * chroma-key plate: a perfectly valid PNG of flat #00FF00. `onError` cannot
   * see that, so the box turned over onto a green slab while `BackPrint` — the
   * printed reverse written for exactly this case — sat unused. Reading the
   * image settles it, and the answer is cached per URL, so turning the same box
   * over twice costs one look.
   */
  const BackScan = ({ src, name, systemId, game, meta, media }) => {
    const [dead, setDead] = useState(false)
    useEffect(() => {
      setDead(false)
      let live = true
      flat(src).then((blank) => { if (live && blank) setDead(true) })
      return () => { live = false }
    }, [src])
    if (dead) return html`<${BackPrint} systemId=${systemId} game=${game} meta=${meta} media=${media} />`
    return html`<img src=${src} alt=${`${name} — back cover`} onError=${() => setDead(true)} />`
  }

  /**
   * When no scan of the back exists, the back is printed instead.
   *
   * Turning a box over and finding the front again reads as a broken control,
   * and a blank rectangle reads as a missing file. So the reverse is set the
   * way a reverse is set: the blurb the metadata tier already holds, the
   * screenshots the game already carries, and the small print off the
   * filename. Same information, in the place the object puts it.
   */
  const BackPrint = ({ systemId, game, meta, media }) => {
    const name = title(game.display_name)
    const { region } = stamp(game.filename)
    const shots = ['screenshot-game-title', 'screenshot-gameplay']
      .map((t) => pick(sdk, systemId, game.filename, media, [t]))
      .filter(Boolean)

    return html`
      <div class="cz-back">
        <div class="cz-back-head">
          <b>${name}</b>
          ${meta?.genres?.length ? html`<i>${meta.genres.slice(0, 2).join(' · ')}</i>` : null}
        </div>

        ${shots.length ? html`
          <div class="cz-back-shots" data-n=${String(shots.length)}>
            ${shots.map((s, i) => html`<img key=${i} src=${s} alt="" />`)}
          </div>` : null}

        <p class="cz-back-blurb">
          ${meta?.description
            || 'No description on file. Everything the shelf knows about this title is on the card.'}
        </p>

        <div class="cz-back-fine">
          <span>${(meta?.publisher || meta?.developer || '').toUpperCase() || 'UNCREDITED'}</span>
          <span>${region || 'REGION UNKNOWN'}</span>
          <span class="cz-back-code">${String(game.ext || '').replace('.', '').toUpperCase()}</span>
        </div>

        <div class="cz-back-bars" aria-hidden="true" />
      </div>`
  }

  return { Spine, Face }
}
