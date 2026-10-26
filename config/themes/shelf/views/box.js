/**
 * The box, assembled from the three faces the backend warmed (`box-front`,
 * `box-spine`, `box-back`). This file is geometry only: six faces, a depth, a
 * rotation. Top, bottom and opening edge are plain cardboard.
 *
 * W and H come from the loaded front (SNES landscape, PS1 portrait), depth
 * follows width. A landscape box's spine scan is a wide band and is turned
 * upright (see `standUp`). Unfocused games are one spine <img>; only the
 * selected one is a full solid (20 solids = 60 layers).
 */
import { pick, jacket } from '../lib/dossier.js'
import { frontOf, knownFront } from '../lib/front.js'
import { title, stamp } from '../lib/names.js'
import { flat } from '../lib/accent.js'
import { isPc } from '../lib/pc.js'
import { createPcCase } from './pc-case.js'

/** Portrait, the commonest cover shape: held until lib/front.js has measured. */
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
  const { PcBand, PcBack } = createPcCase(sdk)

  /**
   * Mark a spine scan as landscape (data-wide) so the CSS stands it upright.
   *
   * `box-2D-side` is the face carrying the title: tall for PS1/DS/Switch, a
   * wide band for N64 (680x115 vs 42x680). Unturned, object-fit: cover keeps
   * ~2 % of the band — a black sliver. Turned clockwise so the title reads
   * top-to-bottom like the printed spines. Written on every load: the <img> is
   * reused and a stale 1 would turn a portrait scan sideways.
   */
  const standUp = (img) => {
    img.dataset.wide = img.naturalWidth > img.naturalHeight ? '1' : '0'
  }

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
      <button class="cz-spine" data-pc=${isPc(systemId) ? '1' : '0'} data-on=${on ? '1' : '0'} data-scan=${scan ? '1' : '0'}
              onClick=${onClick} style=${{ '--spine-h': String(hueOf(name)) }}
              aria-label=${name}>
        ${scan
          ? html`<img src=${src} alt=""
                      onLoad=${(e) => standUp(e.target)}
                      onError=${() => setScan(false)} />`
          : html`
            <span class="cz-spine-print">
              ${isPc(systemId) ? html`<span class="pc-spine-mark">PC</span>` : html`<span class="cz-spine-cap" />`}
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
    // Which picture is the front, and the box's shape, are settled once per
    // game by lib/front.js: the same answer the swap waits for before the
    // jacket turns to face you, so nothing here is drawn before it is known.
    // `undefined` while settling, `null` when the game has no cover.
    const [front, setFront] = useState(() => knownFront(systemId, game?.filename))
    const [frontDead, setFrontDead] = useState(false)
    const [spineDead, setSpineDead] = useState(false)

    // `Face` is keyed on the game it draws (views/library.js), so this state
    // is always this game's: a reset here once ran after a cached image had
    // already measured, and drew one game at another's proportions.
    useEffect(() => {
      if (!game) return
      let live = true
      frontOf(sdk, systemId, game.filename).then((f) => { if (live) setFront(f) })
      // A cover can also load fine and hold no picture: a scraper's chroma-key plate.
      flat(jacket(systemId, game.filename)).then((blank) => {
        if (live && blank) setFrontDead(true)
      })
      return () => { live = false }
    }, [systemId, game?.filename])

    if (!game) return null

    const name = title(game.display_name)
    const pc = isPc(systemId)
    const ratio = front?.ratio || RATIO_UNKNOWN
    const spine = sdk.api.media.url(systemId, game.filename, 'box-spine')
    const back = pick(sdk, systemId, game.filename, media, ['box-back'])

    return html`
      <div class="cz-box" data-pc=${pc ? '1' : '0'} data-flipped=${flipped ? '1' : '0'}
           style=${{ '--ratio': String(ratio) }}>

        <div class="cz-f cz-f-front">
          ${pc ? html`<${PcBand} />` : null}
          ${frontDead || front === null
            ? html`
              <div class="cz-noart">
                <span class="cz-noart-name">${name}</span>
                <span class="cz-noart-note">No cover scanned</span>
              </div>`
            : front
              ? html`<img key=${front.src} src=${front.src} alt=${name}
                          onError=${() => setFrontDead(true)} />`
              : null}
        </div>

        <div class="cz-f cz-f-back">
          ${back
            ? html`<${BackScan} src=${back} name=${name} systemId=${systemId}
                                game=${game} meta=${meta} media=${media} />`
            : html`<${pc ? PcBack : BackPrint} systemId=${systemId} game=${game} meta=${meta} media=${media} />`}
        </div>

        <div class="cz-f cz-f-spine" data-scan=${spineDead ? '0' : '1'}
             style=${{ '--spine-h': String(hueOf(name)) }}>
          ${spineDead
            ? html`${pc ? html`<span class="pc-spine-mark">PC</span>` : null}<span class="cz-spine-name">${name}</span>`
            : html`<img src=${spine} alt=""
                        onLoad=${(e) => standUp(e.target)}
                        onError=${() => setSpineDead(true)} />`}
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
    if (dead) return html`<${isPc(systemId) ? PcBack : BackPrint} systemId=${systemId} game=${game} meta=${meta} media=${media} />`
    return html`<img src=${src} alt=${`${name}, back cover`} onError=${() => setDead(true)} />`
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
          ${meta?.genres?.length ? html`<i>${meta.genres.slice(0, 2).join(', ')}</i>` : null}
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
          <span>${(meta?.publisher || meta?.developer || '').toUpperCase() || 'Uncredited'}</span>
          <span>${region || 'Region unknown'}</span>
          <span class="cz-back-code">${String(game.ext || '').replace('.', '').toUpperCase()}</span>
        </div>

        <div class="cz-back-bars" aria-hidden="true" />
      </div>`
  }

  return { Spine, Face }
}
