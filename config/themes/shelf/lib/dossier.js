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

/**
 * Answers the box actually gave. Only answers.
 *
 * The cache used to hold whatever came out of `load()`, and `load()` swallows
 * every exception — so a backend that was busy restarting, or a scraper that
 * timed out once, wrote an empty card into this map and it stayed there for
 * the life of the page. Walking away and coming back showed the same blank
 * card, with nothing to retry and nothing saying why. The same held for a game
 * whose media were configured or scraped *after* the empty result was
 * remembered: it could not appear.
 *
 * "Nothing is known about this game" is an answer and belongs here; "nobody
 * answered" is not one and does not. There is no expiry, because there is
 * nothing to expire: a failure is simply not written.
 */
const cache = new Map()

/**
 * Lookups in flight, so a return trip along the shelf asks once.
 *
 * Without it, leaving a game and coming straight back before the first request
 * landed sent a second — and the first display of an uncached game is a real
 * round trip to the scraper.
 */
const inflight = new Map()

const key = (systemId, filename) => `${systemId}::${filename}`

export const createUseDossier = (sdk) => {
  const { useState, useEffect } = sdk.ui

  const fetchOnce = async (systemId, filename) => {
    let media = {}
    let meta = {}
    // Whether anything actually answered. Not the same question as whether
    // anything was found.
    let answered = false

    try {
      const index = await sdk.api.media.list(systemId, filename)
      media = index?.media || {}
      meta = index?.meta || {}
      answered = true
    } catch {
      // 404, no source, or an unreachable scraper — all the same to the card,
      // but not to the cache: this one is not remembered.
    }

    // Nothing usable came back, or the box has no media tier at all: the
    // metadata endpoint still knows year, genre and player count.
    if (!meta || !meta.title) {
      try {
        const m = await sdk.api.metadata.get(systemId, filename)
        if (m?.found) meta = { ...m, ...meta }
      } catch {
        // An unknown game answers `found: false` and does not come through
        // here; this is the tier being unreachable, and the card stays
        // retryable because of it.
        answered = false
      }
    }

    const out = { meta: meta || {}, media }
    if (answered) cache.set(key(systemId, filename), out)
    return out
  }

  const load = (systemId, filename) => {
    const k = key(systemId, filename)
    if (cache.has(k)) return Promise.resolve(cache.get(k))

    const running = inflight.get(k)
    if (running) return running

    const p = fetchOnce(systemId, filename).finally(() => inflight.delete(k))
    inflight.set(k, p)
    return p
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
