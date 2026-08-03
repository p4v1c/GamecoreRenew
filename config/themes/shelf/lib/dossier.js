/**
 * Everything the card on the right knows about one game.
 *
 * One call, not two: `sdk.api.media.list()` answers with the metadata *and* the
 * catalogue of artwork in the same response, so asking it gives us the release
 * date, the developer, the publisher and the answer to "does this cartridge
 * have a photograph" for the price of a single request.
 *
 * It is only ever asked about the *settled* selection. The host debounces that
 * 150 ms behind the cursor for exactly this reason: a fast scroll down a system
 * with four hundred games would otherwise queue four hundred lookups, and the
 * first display of an uncached game costs a real round trip to the scraper.
 *
 * A box with no media source configured answers `available: false`. That is not
 * an error and must not read as one — it means the metadata tier is the only
 * one that can answer, so we ask it and draw what we get.
 */

const cache = new Map()

const key = (systemId, filename) => `${systemId}::${filename}`

export const createUseDossier = (sdk) => {
  const { useState, useEffect } = sdk.ui

  const load = async (systemId, filename) => {
    const k = key(systemId, filename)
    if (cache.has(k)) return cache.get(k)

    let media = {}
    let meta = {}

    try {
      const index = await sdk.api.media.list(systemId, filename)
      media = index?.media || {}
      meta = index?.meta || {}
    } catch {
      // 404, no source, or an unreachable scraper — all the same to this card.
    }

    // Nothing usable came back, or the box has no media tier at all: the
    // metadata endpoint still knows year, genre and player count.
    if (!meta || !meta.title) {
      try {
        const m = await sdk.api.metadata.get(systemId, filename)
        if (m?.found) meta = { ...m, ...meta }
      } catch { /* unknown game — the card handles empty */ }
    }

    const out = { meta: meta || {}, media }
    cache.set(k, out)
    return out
  }

  return (systemId, filename) => {
    const [state, setState] = useState({ meta: {}, media: {}, loading: !!filename })

    useEffect(() => {
      if (!systemId || !filename) { setState({ meta: {}, media: {}, loading: false }); return }
      const k = key(systemId, filename)

      // Already known: commit synchronously, so paging back to a game you have
      // already looked at does not blink through an empty card.
      if (cache.has(k)) { setState({ ...cache.get(k), loading: false }); return }

      let live = true
      setState({ meta: {}, media: {}, loading: true })
      load(systemId, filename).then((r) => { if (live) setState({ ...r, loading: false }) })
      return () => { live = false }
    }, [systemId, filename])

    return state
  }
}

/**
 * The best artwork this game actually has for a given job, or null.
 *
 * Asking for a type the game does not carry gets you the jacket instead, which
 * is the right fallback for a hero image and the wrong one for a cartridge
 * photograph — a jacket in a cartridge-shaped frame just looks like a bug. So
 * the card asks here first and draws its own cartridge when the answer is null.
 */
export const pick = (sdk, systemId, filename, media, types) => {
  for (const t of types) {
    if (media && media[t]) return sdk.api.media.url(systemId, filename, t)
  }
  return null
}

/**
 * The host's own cover route.
 *
 * Written exactly the way `CoverImage` writes it, character for character —
 * the system id unescaped, the filename escaped. A different-but-equivalent
 * URL would be a second cache entry and a second request for a picture already
 * on screen.
 */
export const jacket = (systemId, filename) =>
  `/api/covers/${systemId}/${encodeURIComponent(filename)}`
