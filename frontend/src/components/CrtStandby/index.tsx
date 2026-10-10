import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import type { StandbyItem, StandbyPlaylist } from '../../api/standby'
import { useStore } from '../../store'
import { useLocalWake } from '../../hooks/useLocalWake'
import { reelItems, reelMode, type ReelMode } from '../../lib/standbyPlaylist'
import plateOff from '../../assets/standby/room-off.webp'
import plateLight from '../../assets/standby/room-tvlight.webp'
import { DustMotes } from './DustMotes'
import { StandbyCaption } from './StandbyCaption'
import { TvPicture } from './TvPicture'
import { TV_H, TV_W, useTvPlacement } from './useTvPlacement'
import { useTvLight, type LightSource } from './useTvLight'
import './crtStandby.css'

export interface CrtStandbyProps {
  /** A class on the root, for the theme's caption font and colours. */
  skin?: string
  /** `system_id:filename` keys the theme keeps as favourites; they come up more. */
  favourites?: () => string[]
}

/**
 * The CRT standby: a room at night, the library's game clips on a small TV,
 * the TV's light on the walls. `sdk.defaults.CrtStandby`; a theme opts in by
 * passing it as the Shell's `screensaver`.
 *
 * Driven by the store's `standby` stage like the default screensaver, and for
 * the same reason (see Screensaver.tsx): `sleep` is black with nothing mounted,
 * since DPMS has the screen off, and leaving `screensaver` unmounts the room,
 * which stops and releases both videos.
 */
export default function CrtStandby({ skin = '', favourites }: CrtStandbyProps) {
  const stage = useStore(s => s.standby)
  useLocalWake(stage)
  if (stage === 'off') return null
  if (stage === 'sleep') return <div className="crt-standby-sleep" />
  return <CrtRoom skin={skin} favourites={favourites} />
}

function usePrefersReducedMotion(): boolean {
  return useMemo(() => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches, [])
}

function CrtRoom({ skin, favourites }: CrtStandbyProps) {
  const reduced = usePrefersReducedMotion()
  const [list, setList] = useState<StandbyPlaylist | null>(null)
  const [mode, setMode] = useState<ReelMode | null>(null)
  const [item, setItem] = useState<StandbyItem | null>(null)
  const [light, setLight] = useState<LightSource>({ kind: 'idle' })
  const root = useRef<HTMLDivElement>(null)
  const transform = useTvPlacement()
  useTvLight(root, light, reduced)

  // Once per standby: the list is shuffled server-side, and a theme's inline
  // `favourites` arrow must not refetch it on every render.
  const favs = useRef(favourites)
  useEffect(() => {
    let cancelled = false
    api.standby.videos(favs.current?.() ?? [])
      .then(l => { if (!cancelled) { setList(l); setMode(reelMode(l)) } })
      // No playlist (old backend, network): the TV shows snow, the clock still works.
      .catch(() => { if (!cancelled) setMode('none') })
    return () => { cancelled = true }
  }, [])

  const exhausted = useCallback(() => {
    setMode(m => (m === 'video' && list?.stills.length ? 'still' : 'none'))
  }, [list])
  const items = useMemo(() => reelItems(list, mode ?? 'none'), [list, mode])

  return (
    <div ref={root} className={`crt-standby ${skin ?? ''}`}>
      <img className="crt-plate" src={plateOff} alt="" />
      <div className="crt-light" aria-hidden="true">
        <img className="crt-plate" src={plateLight} alt="" />
        <div className="crt-light-tint" />
      </div>
      <div className="crt-tv" style={{ width: TV_W, height: TV_H, transform }}>
        {mode && <TvPicture key={mode} mode={mode} items={items} reduced={reduced}
                            onShow={setItem} onLight={setLight} onExhausted={exhausted} />}
        <div className="crt-tv-glass" />
      </div>
      {!reduced && <DustMotes />}
      <StandbyCaption item={mode === 'none' ? null : item} />
    </div>
  )
}
