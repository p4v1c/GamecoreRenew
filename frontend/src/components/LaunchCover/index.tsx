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

/** Resolves once `url` is decoded and ready to paint, false when it cannot load. */
function preload(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => { img.decode().then(() => resolve(true), () => resolve(true)) }
    img.onerror = () => resolve(false)
    img.src = url
  })
}

/** The art the page will show, every image already decoded: a picture that
 * arrives after the page is up swaps one screen for another in front of the
 * player (the box and the name first, then the key art and the logo). */
async function finalArt(system: string, rom: string): Promise<CoverArt> {
  const index = await api.media.list(system, rom).catch(() => null)
  const art = coverArt(system, rom, index)
  const [hero, logo] = await Promise.all([art.hero, art.logo].map((u) => (u ? preload(u) : false)))
  const jacket = !hero && await preload(art.jacket)
  return { ...art, hero: hero ? art.hero : null, logo: logo ? art.logo : null, jacket: jacket ? art.jacket : '' }
}

type Game = { system: string; rom: string }

/**
 * The launch cover's page, in the window electron/cover.js keeps over the
 * emulator. Built-in look on purpose: it shows for seconds over a game, under
 * every theme, and the game's own art carries it.
 *
 * The window is made once and reused: the game comes by `cover:game` (or the
 * URL, in a browser), and `cover:reset` blanks the page between launches.
 * Invisible until its art is decoded, then one fade in: the window is
 * transparent, so until then the launch ceremony stays on screen. It leaves
 * like a console: the art goes to black, then the black opens on the game.
 */
export default function LaunchCover() {
  const [game, setGame] = useState<Game | null>(() => {
    const params = new URLSearchParams(window.location.search)
    const system = params.get('system') ?? ''
    return system ? { system, rom: params.get('rom') ?? '' } : null
  })
  const [art, setArt] = useState<CoverArt | null>(null)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    const offs = [
      window.gamecore?.onCoverGame?.((d) => {
        setArt(null)
        setLeaving(false)
        setGame({ system: d.system ?? '', rom: d.rom ?? '' })
      }),
      window.gamecore?.onCoverLeave?.(() => setLeaving(true)),
      window.gamecore?.onCoverReset?.(() => {
        setGame(null)
        setArt(null)
        setLeaving(false)
      }),
    ]
    return () => offs.forEach((off) => { if (typeof off === 'function') off() })
  }, [])

  useEffect(() => {
    if (!game) return
    let live = true
    finalArt(game.system, game.rom).then((a) => { if (live) setArt(a) })
    return () => { live = false }
  }, [game])

  return (
    <div className="gc-cover" data-shown={art ? '1' : '0'} data-leaving={leaving ? '1' : '0'}>
      {art && (
        <div className="gc-cover-art">
          {art.hero
            ? <img className="gc-cover-hero" src={art.hero} alt="" />
            : art.jacket && <img className="gc-cover-jacket" src={art.jacket} alt="" />}
          <div className="gc-cover-name">
            {art.logo
              ? <img className="gc-cover-logo" src={art.logo} alt={art.title} />
              : <span className="gc-cover-title">{art.title}</span>}
          </div>
          <div className="gc-cover-spinner" role="progressbar" aria-label="Loading" />
        </div>
      )}
    </div>
  )
}
