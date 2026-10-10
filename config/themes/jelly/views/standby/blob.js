import {coverUrl} from '../../lib/catalog.js'

/** The jellies' colours, from the approved mockup: Jelly's pink, yellow,
 * purple and cyan, plus the green, orange and lilac of css/standby.css. */
export const PALETTE = ['#f950a3', '#ffe66b', '#5931a0', '#7ee08a', '#80deed', '#ff9a5a', '#b48cff']

/** One jelly's element: the coloured body, a cover floating inside, the
 * shine on top. Sized once here; the engine only writes its transform and
 * outline after that. */
export function createBlobEl(game, color, diameter) {
  const el = document.createElement('div')
  el.className = 'jl-sb-blob'
  el.style.setProperty('--c', color)
  el.style.setProperty('--float-delay', `${-Math.random() * 7}s`)
  el.style.setProperty('--tilt', `${(Math.random() - 0.5) * 20}deg`)
  sizeBlobEl(el, diameter, diameter)
  if (game) {
    const img = document.createElement('img')
    img.className = 'jl-sb-cover'
    img.alt = ''
    img.decoding = 'async'
    img.src = coverUrl(game.systemId, game.filename)
    el.appendChild(img)
  }
  const shine = document.createElement('span')
  shine.className = 'jl-sb-shine'
  el.appendChild(shine)
  return el
}

/** A size change is a layout: done when a jelly starts or ends a feature,
 * never per frame (the frame only scales). */
export function sizeBlobEl(el, w, h) {
  el.style.width = `${w}px`
  el.style.height = `${h}px`
  el.style.setProperty('--blob-w', `${w}px`)
}

/** Resolves true when the game's cover loads: the jellies only hold games
 * that have one. */
export function coverLoads(game) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve(img.naturalWidth > 0)
    img.onerror = () => resolve(false)
    img.src = coverUrl(game.systemId, game.filename)
  })
}

const DROPS = 7
const SPLAT_MS = 700

/** A pop's splat: drops of the jelly's colour flying out from its centre.
 * CSS keyframes on transform and opacity; removed when they land. */
export function splatAt(layer, x, y, radius, color) {
  const group = document.createElement('div')
  group.className = 'jl-sb-splat'
  group.style.transform = `translate3d(${x}px, ${y}px, 0)`
  group.style.setProperty('--c', color)
  for (let i = 0; i < DROPS; i++) {
    const a = (i / DROPS) * Math.PI * 2 + Math.random() * 0.6
    const reach = radius * (0.9 + Math.random() * 0.5)
    const drop = document.createElement('span')
    drop.className = 'jl-sb-drop'
    drop.style.setProperty('--dx', `${Math.cos(a) * reach}px`)
    drop.style.setProperty('--dy', `${Math.sin(a) * reach}px`)
    drop.style.setProperty('--s', `${radius * (0.16 + Math.random() * 0.14)}px`)
    group.appendChild(drop)
  }
  layer.appendChild(group)
  setTimeout(() => group.remove(), SPLAT_MS)
}
