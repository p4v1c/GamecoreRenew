import { useState, useEffect, useRef, useCallback } from 'react'
import { Overlay, OverlayLabel } from '../../ui'
import { api, type OverlayChoices, type PerGameState } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'

/**
 * The per-game options panel — which bezel the game gets, and what settings
 * belong to this title and no other.
 *
 * Opened with R2 from the library, on the game under the cursor — every face
 * button on that screen is already spoken for: ✕ launches, ○ goes back, △
 * searches and □ is the controller screen. It exists
 * because the automatic answer is right most of the time and visibly wrong
 * some of it: a pack whose artwork does not suit a game, a bezel someone
 * dislikes, or a title the cascade matched to the wrong PNG. Without a way to
 * say so from the sofa, the only remedy is an SSH session.
 *
 * Three states for the overlay, and the distinction between two of them is the
 * whole design:
 *
 *  · **Automatic** — the cascade decides, and keeps deciding. Stored as the
 *    ABSENCE of a preference, so installing a pack later changes the answer.
 *    A box that had written today's answer down would keep it forever.
 *  · **Off** — draw nothing. Not "no bezel found": that is the same picture
 *    and a completely different problem, and the panel says which.
 *  · A named bezel — only ever one that exists on this box. The backend
 *    refuses anything else, because a setting that saves happily and does
 *    nothing at launch is worse than a setting that is not offered.
 *
 * ## The second section, and what it deliberately is NOT
 *
 * There are no sliders here, and no list of the emulator's options. Building
 * one would mean translating "internal resolution" into thirteen vocabularies
 * and then chasing every one of them through every emulator release — the
 * thing that makes Batocera's configgen impossible to port. So the panel does
 * two much smaller jobs instead:
 *
 *  · it reports the known-good profile, if this game has one, and lets the
 *    player take it off. A setting placed by the catalogue that cannot be
 *    removed is a bug of trust, however correct the setting is;
 *  · it opens the emulator's OWN settings window, where the vocabulary is
 *    already right and always current. What the player sets there, GameCore
 *    then keeps for this game and no other.
 *
 * A system that cannot do per-game settings says so in the pack's own words.
 * An empty section and an emulator that genuinely has no per-title config look
 * identical from four metres away, and only one of them is worth chasing.
 *
 * Nothing here is applied to a running game. The overlay is resolved when a
 * game starts and the per-game file is written just before the emulator reads
 * it, so a change takes effect at the next launch — which is said on screen
 * rather than left to be discovered.
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const DIM = 'rgba(255,255,255,0.35)'
const WARN = '#fbbf24'

type Row = {
  /** Stable across re-renders; the focus index is positional, this is not. */
  key: string
  label: string
  hint: string
  selected: boolean
  run: () => void
}

export default function GameOptionsModal({ systemId, rom, title, onClose }: {
  systemId: string; rom: string; title: string; onClose: () => void
}) {
  const [state, setState] = useState<OverlayChoices | null>(null)
  const [perGame, setPerGame] = useState<PerGameState | null>(null)
  const [failed, setFailed] = useState(false)
  const [focus, setFocus] = useState(0)
  const [saving, setSaving] = useState(false)

  // The gamepad handlers are registered once and must not close over a stale
  // row list — the pad fires long before the fetch returns.
  const rowsRef = useRef<Row[]>([])
  const focusRef = useRef(0)
  useEffect(() => { focusRef.current = focus }, [focus])

  const refresh = useCallback(() => api.overlays.choices(systemId, rom)
    .then(s => { setState(s); setFailed(false) })
    .catch(() => setFailed(true)), [systemId, rom])

  // Separate from the overlay fetch, and allowed to fail on its own. The two
  // sections answer different questions, and a backend that cannot read one
  // must not blank the other — the overlay choice still works on a box whose
  // per-game records are unreadable, and saying "everything is broken" when
  // half of it is not sends the owner looking in the wrong place.
  const refreshPerGame = useCallback(() => api.perGame.state(systemId, rom)
    .then(setPerGame)
    .catch(() => setPerGame(null)), [systemId, rom])

  useEffect(() => { refresh(); refreshPerGame() }, [refresh, refreshPerGame])

  const choose = useCallback((id: string | null) => {
    setSaving(true)
    api.overlays.choose(systemId, rom, id)
      .then(refresh)
      .catch(() => setFailed(true))
      .finally(() => setSaving(false))
  }, [systemId, rom, refresh])

  const actOnProfile = useCallback((action: 'remove' | 'restore') => {
    setSaving(true)
    api.perGame.profile(systemId, rom, action)
      .then(setPerGame)
      .catch(() => refreshPerGame())
      .finally(() => setSaving(false))
  }, [systemId, rom, refreshPerGame])

  const openSettings = useCallback(() => {
    setSaving(true)
    // The emulator takes the screen from here. Closing the panel first means
    // the player is not left with a modal underneath a foreign window they
    // then have to dismiss blind when the emulator quits.
    api.perGame.openSettings(systemId, rom)
      .then(onClose)
      .catch(() => refreshPerGame())
      .finally(() => setSaving(false))
  }, [systemId, rom, onClose, refreshPerGame])

  const current = state ? (state.current ?? null) : null

  const overlayRows: Row[] = [
    { key: 'auto', label: 'Automatic', hint: describeAuto(state),
      selected: current === null, run: () => choose(null) },
    ...(state?.options ?? []).map(o => ({
      key: o.id,
      // `o.label` carries the console's own name for a `console` row — "Game
      // Boy Advance" — so the row says which machine rather than repeating the
      // emulator. Labelling it "System bezel" would be a lie on the one screen
      // where the distinction is the whole point.
      label: o.level === 'game' ? 'This game’s bezel'
           : o.level === 'console' ? 'This console’s bezel'
           : 'System bezel',
      hint: o.label,
      selected: current === o.id,
      run: () => choose(o.id),
    })),
    { key: 'off', label: 'No overlay', hint: 'Nothing is drawn over the game',
      selected: current === 'off', run: () => choose('off') },
  ]

  const gameRows: Row[] = []
  const profile = perGame?.profile
  if (profile?.available) {
    // Three sentences, not two. "Applied", "you removed it" and "it exists but
    // this box runs an emulator it does not claim to cover" are different
    // situations, and the third is the one a player would otherwise read as
    // the setting having silently failed.
    const hint = !profile.inRange
      ? `Not applied — verified for ${profile.emulator}, this box runs `
        + `${profile.emulatorVersion ?? 'an unknown version'}`
      : profile.dismissed
        ? `Removed. ${profile.why}`
        : profile.why ?? ''
    gameRows.push({
      key: 'profile',
      label: profile.dismissed
        ? `Restore the setting for ${profile.label}`
        : `Remove the setting for ${profile.label}`,
      hint,
      selected: Boolean(profile.applied) && !profile.dismissed,
      run: () => actOnProfile(profile.dismissed ? 'restore' : 'remove'),
    })
  }
  if (perGame?.canOpenSettings) {
    gameRows.push({
      key: 'open',
      label: 'Open the emulator’s settings',
      hint: 'Set it there; GameCore keeps it for this game only',
      selected: false,
      run: openSettings,
    })
  }

  const rows = [...overlayRows, ...gameRows]
  rowsRef.current = rows

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => setFocus(f => Math.max(0, f - 1))),
      onGp('gp:dpad-down', () =>
        setFocus(f => Math.min(rowsRef.current.length - 1, f + 1))),
      onGp('gp:confirm', () => rowsRef.current[focusRef.current]?.run()),
      onGp('gp:back', onClose),
      // R2 opened this panel; R2 closes it. A modal a player cannot leave with
      // the button that opened it is a modal they leave by killing the box.
      onGp('gp:r2', onClose),
    ]
    return () => offs.forEach(off => off())
  }, [onClose])

  return (
    <Overlay onClose={onClose} width={520}>
      <OverlayLabel text="GAME OPTIONS" />
      <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 11, color: DIM, marginBottom: 22 }}>Overlay</div>

      {failed && (
        <div style={{ fontSize: 12.5, color: WARN, marginBottom: 16 }}>
          The overlay settings could not be read. The game still launches.
        </div>
      )}

      {rows.map((row, i) => {
        const focused = focus === i
        return (
          <div key={row.key}>
            {row.key === gameRows[0]?.key && (
              <div style={{ fontSize: 11, color: DIM, margin: '20px 0 10px' }}>
                This game
              </div>
            )}
            <button
              onClick={row.run}
              onMouseEnter={() => setFocus(i)}
              disabled={saving}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, width: '100%',
                textAlign: 'left', cursor: 'pointer', marginBottom: 8,
                padding: '12px 14px', borderRadius: 12,
                background: focused ? 'rgba(255,255,255,0.07)' : 'transparent',
                border: `1px solid ${focused ? ACCENT : 'rgba(255,255,255,0.08)'}`,
                color: 'inherit', font: 'inherit',
              }}
            >
              <span style={{ width: 14, color: row.selected ? ACCENT : 'transparent' }}>
                ●
              </span>
              <span style={{ flex: 1 }}>
                <span style={{ fontSize: 14 }}>{row.label}</span>
                <span style={{ display: 'block', fontSize: 11.5, color: DIM,
                               marginTop: 2 }}>
                  {row.hint}
                </span>
              </span>
            </button>
          </div>
        )
      })}

      {perGame && !perGame.supported && perGame.why && (
        <div style={{ fontSize: 11.5, color: DIM, marginTop: 20, lineHeight: 1.5 }}>
          <span style={{ display: 'block', color: 'inherit', marginBottom: 4 }}>
            This system has no per-game settings.
          </span>
          {perGame.why}
        </div>
      )}

      {perGame?.supported && perGame.gameId === null && (
        <div style={{ fontSize: 11.5, color: DIM, marginTop: 20, lineHeight: 1.5 }}>
          This copy carries no identifier GameCore can read, so a setting could
          not be told apart from the next game’s. The emulator’s own settings
          still work.
        </div>
      )}

      <div style={{ fontSize: 11.5, color: DIM, marginTop: 18, lineHeight: 1.5 }}>
        Applies at the next launch. Overlays need an X11 session; on Wayland
        they are skipped.
      </div>
    </Overlay>
  )
}

/** What "Automatic" would actually do right now, said out loud.
 *
 *  Otherwise the default row is the only one whose effect the player cannot
 *  see — and for the five 16:9 systems the honest answer is "nothing", which
 *  is worth knowing before hunting for a bezel that was never needed.
 */
function describeAuto(state: OverlayChoices | null): string {
  if (!state) return 'Reading…'
  switch (state.resolved.source) {
    case 'game':     return 'A bezel matching this game was found'
    case 'console':  return 'No bezel for this game — this console’s is used'
    case 'system':   return 'No bezel for this game — the system’s is used'
    case 'declared': return 'No artwork installed — the configured frame is drawn'
    case 'chosen':   return 'Currently overridden below'
    default:         return 'No overlay is available for this system'
  }
}
