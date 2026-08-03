/**
 * The thing you would actually be holding.
 *
 * The capture shows a photograph of the cartridge above every game's card, and
 * that photograph is `cart-front` — an artwork most games in most collections
 * do not have. Drawing the jacket in its place would look like a bug, so when
 * it is missing the media is *built*: a shell in CSS with the jacket set into
 * its label window, which is what a cartridge label is.
 *
 * Which shell depends on what the game actually shipped on, read off the file
 * extension. A PlayStation ISO in a cartridge frame would be a nicer-looking
 * mistake than a broken image, but still a mistake, so disc dumps get a disc.
 *
 * Everything here is a gradient on a div. No raster asset, nothing to fetch,
 * and it scales cleanly to whatever the boot animation blows it up to.
 */
import { pick, jacket } from '../lib/dossier.js'

const DISC_EXT = /^\.?(iso|chd|cue|bin|img|mdf|pbp|rvz|wbfs|wia|nsp|xci|gcm|gcz|ciso|cso)$/i

export const shellFor = (ext) => (DISC_EXT.test(String(ext || '')) ? 'disc' : 'cart')

export const createCartridge = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  /**
   * @param game     the entry, for its extension and its jacket
   * @param media    the media index for this game, from the dossier
   * @param size     'card' in the panel, 'boot' when it fills the screen
   */
  return ({ systemId, game, media, size = 'card' }) => {
    const [broken, setBroken] = useState(false)
    useEffect(() => { setBroken(false) }, [game?.filename])

    if (!game) return null

    const photo = pick(sdk, systemId, game.filename, media, ['cart-front', 'cart-3d', 'disc'])
    const kind = shellFor(game.ext)

    // A real photograph of the media beats anything drawn, every time.
    if (photo && !broken) {
      return html`
        <div class="cz-media" data-kind="photo" data-size=${size}>
          <img src=${photo} alt="" onError=${() => setBroken(true)} />
        </div>`
    }

    const art = jacket(systemId, game.filename)

    if (kind === 'disc') {
      return html`
        <div class="cz-media" data-kind="disc" data-size=${size}>
          <div class="cz-disc">
            <div class="cz-disc-art" style=${{ backgroundImage: `url("${art}")` }} />
            <div class="cz-disc-sheen" />
            <div class="cz-disc-hub"><i /></div>
          </div>
        </div>`
    }

    return html`
      <div class="cz-media" data-kind="cart" data-size=${size}>
        <div class="cz-cart">
          <div class="cz-cart-shoulder" />
          <div class="cz-cart-label">
            <div class="cz-cart-art" style=${{ backgroundImage: `url("${art}")` }} />
          </div>
          <div class="cz-cart-grip" />
          <i class="cz-cart-screw cz-cart-screw-l" />
          <i class="cz-cart-screw cz-cart-screw-r" />
        </div>
      </div>`
  }
}
