/** Which artwork the game cards stand on: the 3D box when a game has one,
 * or the flat jacket. A player's choice, kept in this browser. */
const KEY = 'jelly-jacket'
const STYLES = ['box-3d', 'box-front']
const listeners = new Set()
let style = 'box-3d'
try {
  const saved = localStorage.getItem(KEY)
  if (STYLES.includes(saved)) style = saved
} catch { /* storage disabled: the default stands */ }

export const jacketStyle = () => style

export function toggleJacketStyle() {
  style = style === 'box-3d' ? 'box-front' : 'box-3d'
  try { localStorage.setItem(KEY, style) } catch { /* ignore */ }
  listeners.forEach((fn) => fn(style))
  return style
}

/** The current style, re-rendering when it changes. */
export const createUseJacketStyle = (sdk) => function useJacketStyle() {
  const {useState, useEffect} = sdk.ui
  const [now, setNow] = useState(style)
  useEffect(() => { listeners.add(setNow); return () => listeners.delete(setNow) }, [])
  return now
}
