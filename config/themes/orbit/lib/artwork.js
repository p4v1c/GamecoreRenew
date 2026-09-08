// Theme-owned presentation data. Never alters a pack or another theme's assets.
export const consoles = {
  duckstation: ['ps1.png', 'PlayStation'], pcsx2: ['ps2.png', 'PlayStation 2'],
  rpcs3: ['ps3.png', 'PlayStation 3'], shadps4: ['ps4.png', 'PlayStation 4'],
  ppsspp: ['psp.png', 'PlayStation Portable'], cemu: ['wiiu.png', 'Nintendo Wii U'],
  dolphin: ['gamecube.png', 'GameCube & Wii'], ryujinx: ['switch.png', 'Nintendo Switch'],
  azahar: ['3ds.png', 'Nintendo 3DS'], melonds: ['ds.png', 'Nintendo DS'],
  mgba: ['gba.png', 'Game Boy Advance'], gopher64: ['n64.png', 'Nintendo 64'],
  rmg: ['n64.png', 'Nintendo 64'], xenia: ['xbox360.png', 'Xbox 360'],
}
export const appStyles = {
  youtube: {color: '#ff0000', scale: 1.43}, twitch: {color: '#a544ff', scale: 1.66},
  stremio: {color: '#7b5bf5', scale: 1.04}, steam: {color: '#1c2232', scale: 1.02},
}
export const isApp = (s) => s?.kind === 'app' || s?.type === 'app'
export const systemName = (s) => s?.platform || consoles[s?.id]?.[1] || s?.label || s?.id || 'Collection'
export const packLogo = (s) => s?.iconPath
  ? `/assets/logos/${encodeURIComponent(s.iconPath.replace(/\\/g, '/').split('/').pop())}` : null
export const coverUrl = (systemId, filename) => `/api/covers/${encodeURIComponent(systemId)}/${encodeURIComponent(filename)}`

export function createArtwork(sdk) {
  const {html, useState} = sdk.ui
  function Image({src, fallback, alt = '', className = '', style}) {
    const [failed, setFailed] = useState([])
    const url = [src, fallback].find((u) => u && !failed.includes(u))
    return url ? html`<img className=${className} src=${url} alt=${alt} style=${style}
      draggable="false" onError=${() => setFailed((v) => [...v, url])} />`
      : html`<span className="orbit-art-fallback">${alt.slice(0, 2).toUpperCase() || '◇'}</span>`
  }
  function SystemArt({system, large = false}) {
    const app = isApp(system)
    const asset = consoles[system?.id]?.[0]
    const brand = appStyles[system?.id] || {color: system?.color || '#203757', scale: 1}
    return html`<div className=${`orbit-system-art ${app ? 'orbit-app-art' : ''} ${large ? 'orbit-art-large' : ''}`}
      style=${app ? {background: brand.color, '--orbit-logo-scale': brand.scale} : {}}>
      <${Image} src=${!app && asset ? sdk.system.asset(`assets/consoles/${asset}`) : packLogo(system)}
        fallback=${packLogo(system)} alt=${systemName(system)} />
    </div>`
  }
  return {Image, SystemArt}
}
