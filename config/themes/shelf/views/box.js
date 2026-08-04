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

/**
 * The shapes a game box actually comes in.
 *
 * The solid is built from the artwork: height is fixed and width follows the
 * image's aspect, which is the only way one theme draws a PS3 slipcase and a
 * Mega Drive carton without cropping two thirds of a real collection. The catch
 * is that it trusts the file to *be* a box front, and the cover route does not
 * always return one — for four games on the reference box it returned a wide
 * logo banner, three of them at exactly 320×176. At a ratio of 1.82 against a
 * fixed 400px height, that draws a box 728px wide: the jacket filled the stage
 * and dwarfed the shelf it was supposed to have come out of.
 *
 * So an aspect no box has is read as what it is — evidence that the file is not
 * a box front — rather than faithfully rendered. Measured against the 55 covers
 * cached on that box, the legitimate ones run 0.60 to 1.43 (a portrait PS3 case
 * at one end, a landscape Mario Kart 64 carton at the other) and the banners
 * sit at 1.80–1.82, with nothing in between. The band below is wide enough to
 * hold every real shape with room to spare and still exclude them.
 */
const RATIO_MIN = 0.5
const RATIO_MAX = 1.5
const plausible = (r) => r >= RATIO_MIN && r <= RATIO_MAX

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

    // The host's cover route has handed back something that is not a box front.
    // It is the preferred source — the same URL the rest of the UI requests, so
    // it is a cache hit rather than a second download — but it is not the only
    // one, and when it fails this way the scraped `box-front` sitting in the
    // media set usually is one. All four of the banners found on the reference
    // box had a correct box-front on disk.
    //
    // This is a VERDICT, not an instruction, and that distinction is the whole
    // fix. It used to be `ownArt` — "we have switched to the scraped art" —
    // and switching was only possible when `box-front` was already known. But
    // the cover is a cache hit and `media` is a round trip, so the measurement
    // almost always happens first: `scraped` was still null, the swap was
    // skipped, and the else-branch clamped the banner to RATIO_MAX and drew it.
    // That is the wide blue FIFA slab — a 1.81 banner squashed to 1.5 and
    // rendered as a box. `media` then arrived with the real front, and nothing
    // asked again, because an <img> that has loaded does not load twice.
    //
    // Remembered instead, the verdict outlives the race: the moment box-front
    // turns up, `front` below points at it and the new source measures itself.
    const [rejected, setRejected] = useState(false)

    // A cover can fail in three ways, and only one of them raises `onError`.
    // It can be a file that loads perfectly and contains no picture — a
    // scraper's chroma-key plate — which has to be looked at to be recognised.
    // Or it can be a picture of something else, which is what a wide logo
    // banner is, and that one is only visible once it has been measured.
    //
    // This effect used to open by resetting the four states above for the new
    // game, and that is what drew one game's box at another game's proportions.
    // An effect runs AFTER paint; an <img> whose src points at something the
    // browser already has fires `load` before that. So the order was measure,
    // then reset — and the reset won. The box then stood at RATIO_UNKNOWN, a
    // portrait guess, whatever shape the artwork actually was, and it stayed
    // there because nothing would fire `load` a second time. Walking away and
    // back re-entered on a cold node and it came out right, which is exactly
    // the "wrong until I scroll away and return" this produced.
    //
    // The reset is gone. `Face` is now keyed on the game it draws (see
    // views/library.js), so a different game is a different component with
    // fresh state, decided before any image can load rather than after.
    useEffect(() => {
      if (!game) return
      let live = true
      flat(jacket(systemId, game.filename)).then((blank) => {
        if (live && blank) setFrontDead(true)
      })
      return () => { live = false }
    }, [systemId, game?.filename])

    if (!game) return null

    const name = title(game.display_name)
    const scraped = pick(sdk, systemId, game.filename, media, ['box-front'])
    // Derived, so it becomes true on the render where `media` lands rather than
    // needing something to notice and act. One step only: once we are on the
    // scraped front there is nothing further to fall back to.
    const useScraped = rejected && !!scraped
    const front = useScraped ? scraped : jacket(systemId, game.filename)
    const spine = sdk.api.media.url(systemId, game.filename, 'box-spine')
    const back = pick(sdk, systemId, game.filename, media, ['box-back'])

    /**
     * The image decides the shape of the solid, so it has to be believed —
     * but only once it has said something believable.
     *
     * An implausible aspect is not a shape to draw, it is a wrong file. Record
     * that and the swap to the scraped box-front follows on its own, whenever
     * the media set arrives — which is the point, because it usually arrives
     * after this runs. `useScraped` makes it a single step, so a game whose
     * every source is a banner cannot loop. If the second file is no better the
     * value is clamped rather than obeyed: a box at the edge of the band is
     * odd, a box twice the width of the stage is broken.
     *
     * Measured on the reference box, FIFA 19 on PS3: the cover route answers
     * 320x176 (ratio 1.82, a wide EA logo banner) and box-front is 581x680
     * (0.85, the actual sleeve). Both files were there the whole time.
     */
    const measure = (el) => {
      if (!el) return
      const { naturalWidth: w, naturalHeight: h } = el
      if (!w || !h) return
      const r = w / h
      if (!plausible(r) && !useScraped) {
        // Record it whether or not there is anywhere to go yet. If box-front is
        // already here the swap re-measures on the new file and this value is
        // irrelevant; if it is not, the clamped banner stands in until it
        // arrives, which beats an empty stage.
        setRejected(true)
        if (scraped) return
      }
      setRatio(Math.max(RATIO_MIN, Math.min(RATIO_MAX, r)))
    }

    // `load` is an event, and an event only reaches a listener that was already
    // attached. A cached image assigned to a node that is being reused can be
    // complete before the handler is on it, and then the measurement simply
    // never happens — the second half of the same bug, and the half that
    // survives a remount. Reading `complete` on the node settles it without
    // waiting for anything: if the picture is already there, measure it now.
    const seed = (el) => { if (el && el.complete) measure(el) }

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
            : html`<img key=${front} ref=${seed} src=${front} alt=${name}
                        onLoad=${(e) => measure(e.target)}
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
