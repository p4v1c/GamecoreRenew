/** Jelly's icons: one 24-unit grid, one 2.2 stroke, round caps. Drawn here
 * so no glyph or emoji stands in for an icon. */
const PATHS = {
  star: 'M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z',
  dice: 'M5 5h14v14H5zM9 9h.01M15 9h.01M12 12h.01M9 15h.01M15 15h.01',
  search: 'M10.5 4.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12zM15 15l5 5',
  erase: 'M9 6h11v12H9l-6-6zM12.5 9.5l5 5M17.5 9.5l-5 5',
  box: 'M4 8l8-4 8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8',
  flat: 'M6 4h12v16H6zM9 8h6',
  again: 'M4 12a8 8 0 1 0 2.5-5.8M4 4v4h4',
  pause: 'M9 6v12M15 6v12',
  out: 'M8 16L16 8M9 8h7v7',
  back: 'M14 6l-6 6 6 6',
  sparkle: 'M12 3c.6 4.6 2.4 6.4 7 7-4.6.6-6.4 2.4-7 7-.6-4.6-2.4-6.4-7-7 4.6-.6 6.4-2.4 7-7z',
  plus: 'M12 5v14M5 12h14',
  ring: 'M12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12z',
}

export function createIcon(sdk) {
  const {html} = sdk.ui
  return function Icon({name, filled = false, className = ''}) {
    return html`<svg className=${`jl-svg ${className}`} viewBox="0 0 24 24" aria-hidden="true"
      fill=${filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2.2"
      strokeLinecap="round" strokeLinejoin="round"><path d=${PATHS[name] || PATHS.ring} /></svg>`
  }
}
