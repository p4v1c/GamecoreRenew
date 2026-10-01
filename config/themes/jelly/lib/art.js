import {coverUrl} from './catalog.js'
import {createUseJacketStyle} from './jacket-style.js'

const indexes = new Map()

/** What a game has (`sdk.api.media.list`), asked once per game and shared by
 * every card showing it. A failure is not cached, so it is asked again. */
const mediaIndex = (sdk, systemId, filename) => {
  const k = `${systemId}::${filename}`
  if (!indexes.has(k)) {
    indexes.set(k, (sdk.api.media?.list ? sdk.api.media.list(systemId, filename) : Promise.resolve(null))
      .catch(() => { indexes.delete(k); return null }))
  }
  return indexes.get(k)
}

/** The URL of one media type when the game has it as an image, else null. */
const mediaOf = (sdk, systemId, filename, type) =>
  mediaIndex(sdk, systemId, filename).then((index) => {
    const e = index?.media?.[type]
    return e && (!e.kind || e.kind === 'image') ? sdk.api.media.url(systemId, filename, type) : null
  })

// Box fronts run from tall PS3 sleeves (~0.6) to wide N64 cartons (~1.43).
// Anything wider is a scraped banner, not a jacket.
const plausible = (w, h) => w > 0 && h > 0 && w / h >= 0.5 && w / h <= 1.5

export function createArt(sdk) {
  const {html, useState, useEffect} = sdk.ui
  const useJacketStyle = createUseJacketStyle(sdk)

  /** Two to three letters from a title, for a cover with no art. */
  const initials = (title) => String(title || '?').split(/\s+/).filter(Boolean)
    .slice(0, 3).map((w) => w[0]).join('').toUpperCase()

  /** A jacket.
   *
   * With the 3D style: the game's `box-3d` when its media index lists one,
   * drawn at its own irregular shape. Otherwise, or when that fails: the
   * cover API, then the scraped box front, then a drawn cover with the title
   * on it. Never a broken image.
   */
  function JacketInner({systemId, filename, title, style}) {
    const [stage, setStage] = useState(style === 'box-3d' ? 'index' : 'cover')
    const [src, setSrc] = useState(stage === 'cover' ? coverUrl(systemId, filename) : null)
    const [ready, setReady] = useState(false)

    useEffect(() => {
      if (stage !== 'index' && stage !== 'media') return
      let alive = true
      const type = stage === 'index' ? 'box-3d' : 'box-front'
      mediaOf(sdk, systemId, filename, type).then((url) => {
        if (!alive) return
        setReady(false)
        if (url) { setSrc(url); setStage(stage === 'index' ? '3d' : 'scraped') }
        else if (stage === 'index') { setSrc(coverUrl(systemId, filename)); setStage('cover') }
        else setStage('none')
      })
      return () => { alive = false }
    }, [stage])

    const fail = () => {
      setReady(false)
      if (stage === '3d') { setSrc(coverUrl(systemId, filename)); setStage('cover') }
      else setStage((s) => (s === 'cover' ? 'media' : 'none'))
    }
    const load = (e) => {
      const img = e.currentTarget
      // A 3D box has no standard shape; a flat jacket wider than 1.5:1 is a
      // scraped banner, not a jacket.
      if (stage === '3d' || plausible(img.naturalWidth, img.naturalHeight)) setReady(true)
      else fail()
    }

    if (stage === 'none') {
      return html`<span className="jl-jacket" data-art="none">
        <span className="jl-jacket-title" aria-hidden="true">${title}</span>
        <span className="jl-jacket-mark" aria-hidden="true">${initials(title)}</span>
      </span>`
    }
    // The title shows while the picture is on its way, so a slow scrape never
    // leaves a blank card.
    return html`<span className="jl-jacket" data-art=${ready ? 'ready' : 'loading'}
                      data-kind=${stage === '3d' ? '3d' : 'flat'}>
      ${ready ? null : html`<span className="jl-jacket-title" aria-hidden="true">${title}</span>`}
      ${src ? html`<img key=${src} src=${src} alt="" draggable="false" loading="lazy" decoding="async"
           onLoad=${load} onError=${fail} />` : null}
    </span>`
  }

  // Keyed by game, so a reused card starts its own fallback from scratch.
  function Jacket(props) {
    const style = useJacketStyle()
    return html`<${JacketInner} key=${`${props.systemId}:${props.filename}:${style}`} ...${props} style=${style} />`
  }

  /** A console photo or pack logo, else its short mark. */
  function Picture({src, mark, className = ''}) {
    const [failed, setFailed] = useState(false)
    useEffect(() => setFailed(false), [src])
    return src && !failed
      ? html`<img className=${className} src=${src} alt="" draggable="false" loading="lazy"
                  decoding="async" onError=${() => setFailed(true)} />`
      : html`<span className=${`jl-picture-mark ${className}`} aria-hidden="true">${mark}</span>`
  }

  return {Jacket, Picture}
}
