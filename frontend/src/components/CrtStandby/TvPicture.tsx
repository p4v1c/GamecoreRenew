import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { StandbyItem } from '../../api/standby'
import { clipSeconds, nextIndex, STATIC_MS, STILL_S, type ReelMode } from '../../lib/standbyPlaylist'
import { TvStatic } from './TvStatic'
import type { LightSource } from './useTvLight'

/** Reduced motion: the picture fades out and in instead of the snow. */
const FADE_MS = 500

interface Props {
  mode: ReelMode
  items: StandbyItem[]
  reduced: boolean
  onShow: (item: StandbyItem | null) => void
  onLight: (source: LightSource) => void
  /** Every item failed to load: the caller falls back to stills, then to snow. */
  onExhausted: () => void
}

/** Two slots: the one on screen, and the next one buffering behind it. */
interface Reel { active: 0 | 1; slots: [number, number]; switching: boolean }
type Action = { type: 'switch' } | { type: 'swap'; n: number }

function reel(s: Reel, a: Action): Reel {
  if (a.type === 'switch') return { ...s, switching: true }
  const shown = (1 - s.active) as 0 | 1
  const slots: [number, number] = [...s.slots]
  slots[s.active] = nextIndex(s.slots[shown], a.n)
  return { active: shown, slots, switching: false }
}

/**
 * What is on the glass. Videos are double-buffered: the next clip loads paused
 * in the second element while the first plays, so only one ever decodes. A
 * clip plays for its length or 25 s, then snow, then the next.
 */
export function TvPicture({ mode, items, reduced, onShow, onLight, onExhausted }: Props) {
  const n = items.length
  const [state, dispatch] = useReducer(reel, undefined, () => ({ active: 0, slots: [0, nextIndex(0, n)], switching: false }) as Reel)
  const videoA = useRef<HTMLVideoElement>(null)
  const videoB = useRef<HTMLVideoElement>(null)
  const still = useRef<HTMLImageElement>(null)
  const failures = useRef(0)
  const switching = useRef(false)

  const advance = useCallback(() => {
    if (switching.current) return
    switching.current = true
    dispatch({ type: 'switch' })
    setTimeout(() => { dispatch({ type: 'swap', n }); switching.current = false },
               reduced ? FADE_MS : STATIC_MS)
  }, [n, reduced])

  const failed = useCallback(() => {
    failures.current += 1
    if (failures.current >= n) onExhausted()
    else advance()
  }, [n, advance, onExhausted])

  const item = n ? items[state.slots[state.active]] : null
  useEffect(() => { onShow(item) }, [item, onShow])
  useEffect(() => {
    if (mode === 'none') onLight({ kind: 'idle' })
    else if (state.switching && !reduced) onLight({ kind: 'snow' })
    else onLight({ kind: 'picture', el: mode === 'video' ? [videoA, videoB][state.active].current : still.current })
  }, [mode, state.switching, state.active, reduced, onLight])

  // Play the clip on screen, park the other one; leave on time or at its end.
  useEffect(() => {
    if (mode !== 'video' || !n) return
    const shown = [videoA, videoB][state.active].current
    const parked = [videoA, videoB][1 - state.active].current
    parked?.pause()
    if (!shown) return
    shown.currentTime = 0
    shown.play().catch(() => { /* autoplay refused: the timer still moves on */ })
    let timer = 0
    const arm = () => { clearTimeout(timer); timer = window.setTimeout(advance, clipSeconds(shown.duration) * 1000) }
    const playing = () => { failures.current = 0 }
    if (shown.readyState >= 1) arm()
    shown.addEventListener('loadedmetadata', arm)
    shown.addEventListener('ended', advance)
    shown.addEventListener('error', failed)
    shown.addEventListener('playing', playing)
    return () => {
      clearTimeout(timer)
      shown.removeEventListener('loadedmetadata', arm)
      shown.removeEventListener('ended', advance)
      shown.removeEventListener('error', failed)
      shown.removeEventListener('playing', playing)
    }
  }, [mode, n, state.active, state.slots, advance, failed])

  // Stills: a slow push-in, then the next; the one after is fetched meanwhile.
  useEffect(() => {
    if (mode !== 'still' || !n) return
    new Image().src = items[state.slots[1 - state.active]].url
    const timer = window.setTimeout(advance, STILL_S * 1000)
    return () => clearTimeout(timer)
  }, [mode, n, items, state.active, state.slots, advance])

  // Leaving standby: stop decoding and let go of the files at once.
  useEffect(() => {
    const els = [videoA.current, videoB.current]
    return () => els.forEach(v => { if (v) { v.pause(); v.removeAttribute('src'); v.load() } })
  }, [])

  const hidden = (on: boolean) => `crt-tv-picture${on ? '' : ' is-hidden'}`
  const snow = mode === 'none' ? 'idle' : state.switching && !reduced ? 'on' : 'off'
  return <>
    {mode === 'video' && [videoA, videoB].map((ref, i) => (
      <video key={i} ref={ref} className={hidden(i === state.active && !state.switching)}
             src={items[state.slots[i]]?.url} muted playsInline preload="auto"
             disablePictureInPicture aria-hidden="true" />
    ))}
    {mode === 'still' && item && (
      <img key={state.slots[state.active]} ref={still} src={item.url} alt=""
           className={`${hidden(!state.switching)} crt-tv-still`} onError={failed} />
    )}
    <TvStatic mode={snow} />
  </>
}
