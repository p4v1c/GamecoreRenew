import {coverUrl} from './catalog.js'
import {listMediaIndex} from './media-cache.js'

// Real box fronts on the reference collection range from portrait PS3 sleeves
// (about .6) to landscape N64 cartons (about 1.43). Wider images are scraper
// banners, including FIFA 19's 320x176 EA banner, rather than jackets.
const RATIO_MIN = 0.5
const RATIO_MAX = 1.5
const plausible = ratio => ratio >= RATIO_MIN && ratio <= RATIO_MAX

const boxFront = (sdk, systemId, filename) =>
  listMediaIndex(sdk, systemId, filename).then(index => {
    const entry = index?.media?.['box-front']
    return entry && (!entry.kind || entry.kind === 'image')
      ? sdk.api.media.url(systemId, filename, 'box-front')
      : null
  })

/** A complete jacket which rejects logo banners and preserves real box shape. */
export const createJacket = sdk => {
  const {html, useEffect, useState} = sdk.ui

  function MeasuredJacket({systemId, filename, title = '', className = '', onRatio}) {
    const direct = coverUrl(systemId, filename)
    const [src, setSrc] = useState(direct)
    const [stage, setStage] = useState('direct')
    const [loaded, setLoaded] = useState(false)

    useEffect(() => {
      if (stage !== 'resolving') return
      let live = true
      boxFront(sdk, systemId, filename)
        .then(url => {
          if (!live) return
          if (url) { setLoaded(false); setSrc(url); setStage('scraped') }
          else setStage('failed')
        })
        .catch(() => { if (live) setStage('failed') })
      return () => { live = false }
    }, [stage, systemId, filename])

    const measure = img => {
      const w = img?.naturalWidth || 0
      const h = img?.naturalHeight || 0
      if (!w || !h) return
      setLoaded(true)
      const next = w / h
      if (!plausible(next)) {
        setStage(stage === 'direct' ? 'resolving' : 'failed')
        return
      }
      // Reported, not applied here. A card that resizes itself is the defect
      // the fixed frame was protecting against; the shape of a SHELF is a
      // different question, and the caller is the only one that can see the
      // whole of it. See library.js.
      onRatio?.(next)
    }

    const failed = () => setStage(stage === 'direct' ? 'resolving' : 'failed')
    const fallback = stage === 'resolving' || stage === 'failed'

    return html`<span className=${`orbit-jacket ${className}`} data-source=${stage} data-loaded=${loaded || fallback ? 'true' : 'false'}>
      ${fallback
        ? html`<span className="art-fallback">${(title || '◇').slice(0, 2).toUpperCase()}</span>`
        : html`<img key=${src} src=${src} alt=${title} draggable="false" loading="lazy"
                    onLoad=${event => measure(event.currentTarget)} onError=${failed} />`}
    </span>`
  }

  // Identity creates fresh state before paint when a grid node is reused. An
  // effect would reset after a cached image had already reported its shape.
  return function Jacket(props) {
    return html`<${MeasuredJacket} key=${`${props.systemId}:${props.filename}`}
      systemId=${props.systemId} filename=${props.filename} title=${props.title}
      className=${props.className} onRatio=${props.onRatio} />`
  }
}
