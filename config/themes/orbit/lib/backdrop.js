import {listMediaIndex} from './media-cache.js'

/** Orbit backdrop resolver.
 *
 * Selection changes are intentionally cheap: the current picture stays in place
 * while the cursor is moving. Only a selection that remains stable for 175 ms
 * may ask the media API, and the new picture is swapped in only after preload.
 */
const TYPES = ['fanart-background', 'background', 'screenshot-gameplay', 'screenshot-game-title', 'mix-rbv2']

const resolveSources = (sdk, systemId, filename) =>
  listMediaIndex(sdk, systemId, filename).then(index => TYPES
    .filter(type => index?.media?.[type]?.kind === 'image')
    .map(type => sdk.api.media.url(systemId, filename, type)))
    .catch(() => [])

const preload = (url) => new Promise(resolve => {
  if (!url) { resolve(null); return }
  if (typeof Image === 'undefined') { resolve(url); return }
  const image = new Image()
  image.src = url
  // Modern Electron/Chromium exposes decode(), which resolves only when pixels
  // are ready. Older/test DOMs may not; preserve their historical direct-swap
  // fallback rather than hanging forever on an event they do not implement.
  if (typeof image.decode !== 'function') { resolve(url); return }
  image.decode().then(() => resolve(url)).catch(() => resolve(null))
})

const firstLoadable = async (urls) => {
  for (const url of urls) {
    const loaded = await preload(url)
    if (loaded) return loaded
  }
  return null
}

/** Selection is local to this theme instance. Hidden host screens never publish. */
export function createBackdrop(sdk) {
  const {html, useState, useEffect, useRef} = sdk.ui
  let selection = null
  const listeners = new Set()

  function select(next) {
    if (JSON.stringify(selection) === JSON.stringify(next)) return
    selection = next
    listeners.forEach(fn => fn(next))
  }

  function Background() {
    const [item, setItem] = useState(selection)
    const [current, setCurrent] = useState(null)
    const [previous, setPrevious] = useState(null)
    const currentRef = useRef(current)
    const generation = useRef(0)
    const fadeTimer = useRef(null)

    useEffect(() => {
      listeners.add(setItem)
      setItem(selection)
      return () => listeners.delete(setItem)
    }, [])

    useEffect(() => {
      currentRef.current = current
    }, [current])

    useEffect(() => () => {
      generation.current += 1
      if (fadeTimer.current) clearTimeout(fadeTimer.current)
    }, [])

    useEffect(() => {
      const mine = ++generation.current

      // App/system/collection scenes deliberately use Orbit's neutral scenery.
      // A library with no settled item keeps the last valid game backdrop rather
      // than flashing during host loading/filtering.
      if (!item?.filename) {
        // Neutral scenes are also stabilized. Crossing an app/collection tile
        // during a fast rail scroll must not blank a perfectly good backdrop.
        const neutralTimer = setTimeout(() => {
          if (generation.current !== mine || item?.kind === 'library') return
          if (fadeTimer.current) clearTimeout(fadeTimer.current)
          currentRef.current = null
          setCurrent(null)
          setPrevious(null)
        }, 175)
        return () => clearTimeout(neutralTimer)
      }

      const timer = setTimeout(() => {
        resolveSources(sdk, item.systemId, item.filename).then(async sources => {
          if (generation.current !== mine) return
          const next = await firstLoadable(sources)
          if (generation.current !== mine || !next || next === currentRef.current) return

          const old = currentRef.current
          if (fadeTimer.current) clearTimeout(fadeTimer.current)
          setPrevious(old && old !== next ? old : null)
          currentRef.current = next
          setCurrent(next)
          fadeTimer.current = setTimeout(() => {
            if (generation.current === mine) setPrevious(null)
          }, 380)
        })
      }, 175)

      return () => clearTimeout(timer)
    }, [item?.kind, item?.systemId, item?.filename])

    return html`<div className="scenery" aria-hidden="true" data-kind=${item?.kind || 'collection'}
      style=${{'--scene-accent': item?.accent || '#8dc0f5'}}>
      <div className="backdrop orbit-backdrop-crossfade">
        ${previous ? html`<img className="orbit-backdrop-layer orbit-backdrop-previous" src=${previous} alt="" />` : null}
        ${current ? html`<img key=${current} className="orbit-backdrop-layer orbit-backdrop-current" src=${current} alt="" />` : null}
      </div>
      <div className="shade" /><div className="grain" />
    </div>`
  }

  return {select, Background}
}
