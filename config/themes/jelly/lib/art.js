import {coverUrl} from './catalog.js'

const media = new Map()

/** The scraped box front, asked once per game and shared. Null when the box
 * has none, so the caller can stop asking. */
const boxFront = (sdk, systemId, filename) => {
  const k = `${systemId}::${filename}`
  if (!media.has(k)) {
    media.set(k, (sdk.api.media?.list
      ? sdk.api.media.list(systemId, filename)
      : Promise.resolve(null))
      .then((index) => {
        const e = index?.media?.['box-front']
        return e && (!e.kind || e.kind === 'image')
          ? sdk.api.media.url(systemId, filename, 'box-front') : null
      })
      .catch(() => { media.delete(k); return null }))
  }
  return media.get(k)
}

// Box fronts run from tall PS3 sleeves (~0.6) to wide N64 cartons (~1.43).
// Anything wider is a scraped banner, not a jacket.
const plausible = (w, h) => w > 0 && h > 0 && w / h >= 0.5 && w / h <= 1.5

export function createArt(sdk) {
  const {html, useState, useEffect} = sdk.ui

  /** Two to three letters from a title, for a cover with no art. */
  const initials = (title) => String(title || '?').split(/\s+/).filter(Boolean)
    .slice(0, 3).map((w) => w[0]).join('').toUpperCase()

  /** A jacket: the cover API, then the scraped box front, then a drawn cover
   * with the title on it. Never a broken image. */
  function JacketInner({systemId, filename, title}) {
    const [src, setSrc] = useState(coverUrl(systemId, filename))
    const [stage, setStage] = useState('cover')
    const [ready, setReady] = useState(false)

    useEffect(() => {
      if (stage !== 'media') return
      let alive = true
      boxFront(sdk, systemId, filename).then((url) => {
        if (!alive) return
        if (url) { setReady(false); setSrc(url); setStage('scraped') } else setStage('none')
      })
      return () => { alive = false }
    }, [stage])

    const fail = () => setStage((s) => (s === 'cover' ? 'media' : 'none'))
    const load = (e) => {
      const img = e.currentTarget
      if (plausible(img.naturalWidth, img.naturalHeight)) setReady(true)
      else fail()
    }

    if (stage === 'media' || stage === 'none') {
      return html`<span className="jl-jacket" data-art="none">
        <span className="jl-jacket-title" aria-hidden="true">${title}</span>
        <span className="jl-jacket-mark" aria-hidden="true">${initials(title)}</span>
      </span>`
    }
    // The title shows while the picture is on its way, so a slow scrape never
    // leaves a blank card.
    return html`<span className="jl-jacket" data-art=${ready ? 'ready' : 'loading'}>
      ${ready ? null : html`<span className="jl-jacket-title" aria-hidden="true">${title}</span>`}
      <img key=${src} src=${src} alt="" draggable="false" loading="lazy" decoding="async"
           onLoad=${load} onError=${fail} />
    </span>`
  }

  // Keyed by game, so a reused card starts its own fallback from scratch.
  function Jacket(props) {
    return html`<${JacketInner} key=${`${props.systemId}:${props.filename}`} ...${props} />`
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
