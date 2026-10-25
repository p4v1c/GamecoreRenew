import { useEffect, useState } from 'react'
import { api, type GameMediaIndex } from '../../api'
import { formatGameName } from '../../lib/formatGameName'
import './launchCover.css'

/** Key art first; a title screen is the last resort, it prints the logo twice. */
const HERO_TYPES = ['fanart-background', 'screenshot-gameplay', 'screenshot-game-title']
const LOGO_TYPES = ['clear-logo-hd', 'clear-logo']

export interface CoverArt {
  hero: string | null
  logo: string | null
  /** The box, drawn alone when the game has no key art. */
  jacket: string
  title: string
}

const image = (index: GameMediaIndex | null, types: string[]) =>
  types.find((t) => {
    const entry = index?.media?.[t]
    return entry && (!entry.kind || entry.kind === 'image')
  }) ?? null

/** `Uncharted 2.sh`, `Ico (Europe) (En,Fr).iso` → the name a player says. */
export function titleOf(rom: string): string {
  const stem = rom.replace(/\.[A-Za-z0-9]{1,5}$/, '')
  return formatGameName(stem.replace(/\s*[([][^)\]]*[)\]]/g, '')).trim() || stem
}

export function coverArt(system: string, rom: string, index: GameMediaIndex | null): CoverArt {
  const hero = image(index, HERO_TYPES)
  const logo = image(index, LOGO_TYPES)
  return {
    hero: hero && api.media.url(system, rom, hero),
    logo: logo && api.media.url(system, rom, logo),
    jacket: `/api/covers/${system}/${encodeURIComponent(rom)}`,
    title: index?.meta?.title || titleOf(rom),
  }
}

/**
 * The launch cover's page, in the window electron/cover.js opens over the
 * emulator. Built-in look on purpose: it shows for seconds over a game, under
 * every theme, and the game's own art carries it.
 */
export default function LaunchCover() {
  const params = new URLSearchParams(window.location.search)
  const system = params.get('system') ?? ''
  const rom = params.get('rom') ?? ''
  const [art, setArt] = useState<CoverArt>(() => coverArt(system, rom, null))
  const [heroShown, setHeroShown] = useState(false)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    let live = true
    api.media.list(system, rom)
      .then((index) => { if (live) setArt(coverArt(system, rom, index)) })
      .catch(() => { /* the name and the box are enough */ })
    window.gamecore?.onCoverLeave?.(() => setLeaving(true))
    return () => { live = false }
  }, [system, rom])

  return (
    <div className="gc-cover" data-leaving={leaving ? '1' : '0'}>
      {art.hero ? (
        <img className="gc-cover-hero" data-shown={heroShown ? '1' : '0'} src={art.hero} alt=""
             onLoad={() => setHeroShown(true)} onError={() => setArt({ ...art, hero: null })} />
      ) : (
        <img className="gc-cover-jacket" src={art.jacket} alt=""
             onError={(e) => { e.currentTarget.hidden = true }} />
      )}
      <div className="gc-cover-name">
        {art.logo
          ? <img className="gc-cover-logo" src={art.logo} alt={art.title}
                 onError={() => setArt({ ...art, logo: null })} />
          : <span className="gc-cover-title">{art.title}</span>}
      </div>
      <div className="gc-cover-spinner" role="progressbar" aria-label="Loading" />
    </div>
  )
}
