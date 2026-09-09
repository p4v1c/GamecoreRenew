import {coverUrl} from './catalog.js'
import {listMediaIndex} from './media-cache.js'

// Prefer the actual platform when Orbit knows it. Extension fallback keeps this
// useful for community packs without teaching the theme every emulator id.
const CART_SYSTEMS = new Set(['mgba', 'gopher64', 'rmg', 'melonds', 'azahar', 'ryujinx'])
const DISC_SYSTEMS = new Set(['duckstation', 'pcsx2', 'rpcs3', 'shadps4', 'ppsspp', 'dolphin', 'cemu', 'xenia'])
const DISC_EXT = /^(iso|chd|cue|bin|img|mdf|mds|ccd|toc|rvz|wbfs|wia|gcm|gcz|ciso|cso|pbp)$/i
const CART_EXT = /^(xci|nsp|nes|fds|sfc|smc|gb|gbc|gba|nds|3ds|cia|n64|z64|v64|gen|md|smd|sms|gg|pce|a26|a52|a78|lnx|j64|ws|wsc)$/i

const mediaCache = new Map()
const key = (systemId, filename) => `${systemId}::${filename}`

const extOf = (value) => {
  const raw = String(value || '').toLowerCase().trim()
  const leaf = raw.replace(/\\/g, '/').split('/').pop() || ''
  const dot = leaf.lastIndexOf('.')
  return (dot >= 0 ? leaf.slice(dot + 1) : leaf.replace(/^\./, '')).replace(/^\./, '')
}

export const physicalKind = (systemId, extOrFilename) => {
  const id = String(systemId || '').toLowerCase()
  if (CART_SYSTEMS.has(id)) return 'cart'
  if (DISC_SYSTEMS.has(id)) return 'disc'
  const ext = extOf(extOrFilename)
  if (DISC_EXT.test(ext)) return 'disc'
  if (CART_EXT.test(ext)) return 'cart'
  // Preserve Shelf's historical safe fallback for unknown ROM formats.
  return 'cart'
}

const typesFor = (kind) => kind === 'disc' ? ['disc'] : ['cart-front', 'cart-3d']

const loadPhysical = (sdk, systemId, filename, kind) => {
  if (!systemId || !filename) return Promise.resolve(null)
  const k = key(systemId, filename)
  if (mediaCache.has(k)) return Promise.resolve(mediaCache.get(k))

  return listMediaIndex(sdk, systemId, filename).then(index => {
    const type = typesFor(kind).find(t => index?.media?.[t]?.kind === 'image')
    const url = type ? sdk.api.media.url(systemId, filename, type) : null
    mediaCache.set(k, url)
    return url
  }).catch(() => null)
}

export const createPhysicalMedia = (sdk) => {
  const {html, useState, useEffect} = sdk.ui

  return function PhysicalMedia({systemId, filename, ext, title = '', active = false}) {
    const kind = physicalKind(systemId, ext || filename)
    const k = key(systemId, filename)
    const [photo, setPhoto] = useState(() => mediaCache.get(k) || null)
    const [photoBroken, setPhotoBroken] = useState(false)
    const [coverBroken, setCoverBroken] = useState(false)

    useEffect(() => {
      setPhotoBroken(false)
      setCoverBroken(false)
      setPhoto(mediaCache.get(k) || null)
    }, [k])

    // Every card can render this component, but only the currently selected
    // card is allowed to start a media lookup. The short delay absorbs rapid
    // gamepad scrolling; cache + inflight keep return trips at one request.
    useEffect(() => {
      if (!active || !systemId || !filename) return
      let live = true
      const cached = mediaCache.get(k)
      if (cached !== undefined) {
        setPhoto(cached)
        return () => { live = false }
      }
      const timer = setTimeout(() => {
        loadPhysical(sdk, systemId, filename, kind).then(url => {
          if (live) setPhoto(url)
        })
      }, 175)
      return () => { live = false; clearTimeout(timer) }
    }, [active, systemId, filename, kind])

    if (photo && !photoBroken) {
      return html`<span className="orbit-physical" data-kind="photo" data-medium=${kind}>
        <img className="orbit-physical-photo" src=${photo} alt="" draggable="false"
             onError=${() => setPhotoBroken(true)} />
      </span>`
    }

    const art = coverUrl(systemId, filename)
    const fallback = html`<span className="orbit-physical-fallback">${(title || '◇').slice(0, 2).toUpperCase()}</span>`
    const label = !coverBroken
      ? html`<img src=${art} alt="" draggable="false" loading="lazy" onError=${() => setCoverBroken(true)} />`
      : fallback

    if (kind === 'disc') {
      return html`<span className="orbit-physical" data-kind="disc">
        <span className="orbit-disc">
          <span className="orbit-disc-art">${label}</span>
          <span className="orbit-disc-sheen" />
          <span className="orbit-disc-hub"><i /></span>
        </span>
      </span>`
    }

    return html`<span className="orbit-physical" data-kind="cart">
      <span className="orbit-cart">
        <span className="orbit-cart-shoulder" />
        <span className="orbit-cart-label">${label}</span>
        <span className="orbit-cart-grip" />
        <i className="orbit-cart-screw orbit-cart-screw-l" />
        <i className="orbit-cart-screw orbit-cart-screw-r" />
      </span>
    </span>`
  }
}
