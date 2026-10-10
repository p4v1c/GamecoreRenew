/**
 * The PC case: one house colour, the way a console has its own (the Switch's
 * red). A blue band with the PC mark across the front and the back, white
 * plastic for the edges and the spine. Most PC games were never boxed, so
 * the reverse is printed from what the media index holds, set the way a
 * retail PC back is set: key art under the logo, the blurb, two shots, the
 * minimum spec panel, the credit and the bars.
 */
import { pick } from '../lib/dossier.js'
import { title } from '../lib/names.js'

/** The spec rows, in the order a box prints them, keyed as meta.requirements. */
const REQS = [['os', 'OS'], ['cpu', 'CPU'], ['ram', 'RAM'], ['gpu', 'GPU'], ['disk', 'Disk']]

export const createPcCase = (sdk) => {
  const { html } = sdk.ui

  const PcBand = ({ small = false }) => html`
    <div class=${small ? 'pc-band pc-band-small' : 'pc-band'}>
      <svg viewBox="0 0 24 20" aria-hidden="true">
        <rect x="1.5" y="1.5" width="21" height="13" rx="1.5" fill="none" stroke="currentColor" stroke-width="2.4" />
        <path d="M8 19h8M12 15v4" stroke="currentColor" stroke-width="2.4" />
      </svg>
      <b>PC</b>
    </div>`

  const PcBack = ({ systemId, game, meta, media }) => {
    const art = (types) => pick(sdk, systemId, game.filename, media, types)
    const logo = art(['clear-logo-hd', 'clear-logo'])
    // A title screen as the key art would print the logo twice; gameplay
    // first, then the fanart, then whatever shot there is.
    const hero = art(['fanart-background', 'screenshot-gameplay', 'screenshot-game-title'])
    const shots = [art(['screenshot-gameplay']), art(['screenshot-game-title'])]
      .filter((s) => s && s !== hero)
    const reqs = REQS.filter(([k]) => meta?.requirements?.[k])

    return html`
      <div class="pc-back">
        <${PcBand} small />
        <div class="pc-hero" data-art=${hero ? '1' : '0'}
             style=${hero ? { backgroundImage: `url("${hero}")` } : null}>
          ${logo
            ? html`<img class="pc-logo" src=${logo} alt="" />`
            : html`<b class="pc-logo-text">${title(game.display_name)}</b>`}
        </div>
        <div class="pc-body">
          ${meta?.description ? html`<p class="pc-blurb">${meta.description}</p>` : null}
          ${shots.length ? html`
            <div class="pc-shots">${shots.map((s) => html`<img key=${s} src=${s} alt="" />`)}</div>` : null}
          ${reqs.length ? html`
            <div class="pc-req">
              <b>Minimum system requirements</b>
              <dl>${reqs.map(([k, label]) => html`<dt key=${k}>${label}</dt><dd>${meta.requirements[k]}</dd>`)}</dl>
            </div>` : null}
        </div>
        <div class="pc-foot">
          <span class="pc-credit">
            <b>${meta?.developer || meta?.publisher || ''}</b>
            <i>${[meta?.year || String(meta?.released || '').slice(0, 4), meta?.genres?.[0]].filter(Boolean).join(', ')}</i>
          </span>
          <span class="pc-bars" aria-hidden="true" />
        </div>
      </div>`
  }

  return { PcBand, PcBack }
}
