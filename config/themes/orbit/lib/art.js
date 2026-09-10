export function createArt(sdk) {
  const {html, useState, useEffect} = sdk.ui

  /** An image that falls back to initials rather than a broken frame. */
  function Art({src, alt = '', className = ''}) {
    const [failed, setFailed] = useState(false)
    useEffect(() => setFailed(false), [src])
    return src && !failed
      ? html`<img className=${className} src=${src} alt=${alt} draggable="false"
                  onError=${() => setFailed(true)} />`
      : html`<span className="art-fallback">${(alt || '◇').slice(0, 2).toUpperCase()}</span>`
  }

  return Art
}
