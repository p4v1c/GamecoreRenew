import {coverUrl} from './catalog.js'

/** Selection is local to this theme instance. Hidden host screens never publish. */
export function createBackdrop(sdk) {
  const {html, useState, useEffect} = sdk.ui
  let selection = null
  const listeners = new Set()
  function select(next) {
    if (JSON.stringify(selection) === JSON.stringify(next)) return
    selection = next
    listeners.forEach(fn => fn(next))
  }
  function Background() {
    const [item, setItem] = useState(selection)
    const [sources, setSources] = useState([])
    const [failed, setFailed] = useState([])
    useEffect(() => { listeners.add(setItem); setItem(selection); return () => listeners.delete(setItem) }, [])
    useEffect(() => {
      let live = true
      setSources([])
      setFailed([])
      if (!item?.filename) return
      const fallback = coverUrl(item.systemId, item.filename)
      setSources([fallback])
      sdk.api.media.list(item.systemId, item.filename).then(index => {
        if (!live) return
        const types = ['fanart-background', 'background', 'screenshot-gameplay', 'screenshot-game-title', 'mix-rbv2']
          .filter(type => index?.media?.[type]?.kind === 'image')
        setSources([...types.map(type => sdk.api.media.url(item.systemId, item.filename, type)), fallback])
      }).catch(() => {})
      return () => { live = false }
    }, [item?.systemId, item?.filename])
    const src = sources.find(url => !failed.includes(url))
    return html`<div className="scenery" aria-hidden="true" data-kind=${item?.kind || 'collection'}
      style=${{'--scene-accent': item?.accent || '#8dc0f5'}}>
      <div className="backdrop">${src ? html`<img key=${src} src=${src} alt=""
        onError=${() => setFailed(previous => [...previous, src])} />` : null}</div>
      <div className="shade" /><div className="grain" />
    </div>`
  }
  return {select, Background}
}
