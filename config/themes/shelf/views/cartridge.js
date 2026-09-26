/**
 * The media you would be holding: the `cart-front` photo when it exists,
 * otherwise a CSS shell with the jacket in its label window.
 *
 * The shell is chosen from the PLATFORM first, the extension second: `.xci`
 * and `.nsp` are Switch cards, and `.bin` is both a PS1 track and a Mega Drive
 * ROM. The photo follows the same rule (disc game → disc picture only).
 * Gradients only: nothing to fetch, scales cleanly for the boot animation.
 */
import { pick, jacket } from '../lib/dossier.js'

const CART_SYSTEMS = new Set(['mgba', 'gopher64', 'rmg', 'melonds', 'azahar', 'ryujinx'])
const DISC_SYSTEMS = new Set(['duckstation', 'pcsx2', 'rpcs3', 'shadps4', 'ppsspp', 'dolphin', 'cemu', 'xenia'])
const DISC_EXT = /^\.?(iso|chd|cue|bin|img|mdf|mds|ccd|toc|pbp|rvz|wbfs|wia|gcm|gcz|ciso|cso)$/i
const CART_EXT = /^\.?(xci|nsp|nes|fds|sfc|smc|gb|gbc|gba|nds|3ds|cia|n64|z64|v64|gen|md|smd|sms|gg|pce|a26|a52|a78|lnx|j64|ws|wsc)$/i

export const shellFor = (ext, systemId = '') => {
  const id = String(systemId || '').toLowerCase()
  if (CART_SYSTEMS.has(id)) return 'cart'
  if (DISC_SYSTEMS.has(id)) return 'disc'
  if (DISC_EXT.test(String(ext || ''))) return 'disc'
  if (CART_EXT.test(String(ext || ''))) return 'cart'
  return 'cart'
}

export const createCartridge = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  /**
   * @param systemId the console the game is filed under — the first word on
   *                 what it shipped on, and the one the extension cannot say
   * @param game     the entry, for its extension and its jacket
   * @param media    the media index for this game, from the dossier
   * @param size     'card' in the panel, 'boot' when it fills the screen
   */
  return ({ systemId, game, media, size = 'card' }) => {
    const [broken, setBroken] = useState(false)
    useEffect(() => { setBroken(false) }, [game?.filename])

    if (!game) return null

    const kind = shellFor(game.ext, systemId)
    const photo = pick(sdk, systemId, game.filename, media,
      kind === 'disc' ? ['disc'] : ['cart-front', 'cart-3d'])

    // A real photograph of the media beats anything drawn, every time.
    if (photo && !broken) {
      return html`
        <div class="cz-media" data-kind="photo" data-medium=${kind} data-size=${size}>
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
