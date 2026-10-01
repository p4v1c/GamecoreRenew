import {currentPress} from '../../lib/presses.js'

export const ZONES = [['keys', 'Clavier'], ['filters', 'Filtres'], ['games', 'Jeux']]

/** Which zone of the search owns the pad, and the moves between them.
 *
 * Read from a ref, so two presses in one frame see the first one's move; and
 * judged per press, so the three zones' listeners do not each move it again. */
export const createUseZones = (sdk) => function useZones(usable) {
  const {useState, useRef} = sdk.ui
  const [zone, setState] = useState('keys')
  const ref = useRef('keys')
  const atPress = useRef({press: null, zone: 'keys'})
  const set = (z) => { ref.current = z; setState(z) }
  const go = (z) => { if (usable(z) && z !== ref.current) { sdk.system.playSound('move'); set(z) } }
  const cycle = (d) => {
    const at = ZONES.findIndex(([id]) => id === ref.current)
    for (let i = 1; i <= ZONES.length; i++) {
      const next = ZONES[(at + d * i + ZONES.length * 3) % ZONES.length][0]
      if (usable(next)) { go(next); return }
    }
  }
  const zoneAtPress = () => {
    const p = currentPress()
    if (!p) return ref.current
    if (atPress.current.press !== p) atPress.current = {press: p, zone: ref.current}
    return atPress.current.zone
  }
  return {zone, current: () => ref.current, set, go, cycle, zoneAtPress}
}
