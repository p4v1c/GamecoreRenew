import { useState, useEffect, useRef, useCallback } from 'react'
import { Overlay, OverlayLabel } from '../../ui'
import { api, type OverlayChoices } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'

/**
 * The per-game options panel — today, which bezel the game gets.
 *
 * Opened with R2 from the library, on the game under the cursor — every face
 * button on that screen is already spoken for: ✕ launches, ○ goes back, △
 * searches and □ is the controller screen. It exists
 * because the automatic answer is right most of the time and visibly wrong
 * some of it: a pack whose artwork does not suit a game, a bezel someone
 * dislikes, or a title the cascade matched to the wrong PNG. Without a way to
 * say so from the sofa, the only remedy is an SSH session.
 *
 * Three states, and the distinction between two of them is the whole design:
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
 * Nothing here is applied to a running game. The overlay is resolved when a
 * game starts, so a change takes effect at the next launch — which is said on
 * screen rather than left to be discovered.
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const DIM = 'rgba(255,255,255,0.35)'

type Row = { id: string | null; label: string; hint: string }

export default function GameOptionsModal({ systemId, rom, title, onClose }: {
  systemId: string; rom: string; title: string; onClose: () => void
}) {
  const [state, setState] = useState<OverlayChoices | null>(null)
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

  useEffect(() => { refresh() }, [refresh])

  const rows: Row[] = [
    { id: null, label: 'Automatic', hint: describeAuto(state) },
    ...(state?.options ?? []).map(o => ({
      id: o.id,
      label: o.level === 'game' ? 'This game’s bezel' : 'System bezel',
      hint: o.label,
    })),
    { id: 'off', label: 'No overlay', hint: 'Nothing is drawn over the game' },
  ]
  rowsRef.current = rows

  const choose = useCallback((id: string | null) => {
    setSaving(true)
    api.overlays.choose(systemId, rom, id)
      .then(refresh)
      .catch(() => setFailed(true))
      .finally(() => setSaving(false))
  }, [systemId, rom, refresh])

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => setFocus(f => Math.max(0, f - 1))),
      onGp('gp:dpad-down', () =>
        setFocus(f => Math.min(rowsRef.current.length - 1, f + 1))),
      onGp('gp:confirm', () => choose(rowsRef.current[focusRef.current]?.id ?? null)),
      onGp('gp:back', onClose),
      // R2 opened this panel; R2 closes it. A modal a player cannot leave with
      // the button that opened it is a modal they leave by killing the box.
      onGp('gp:r2', onClose),
    ]
    return () => offs.forEach(off => off())
  }, [choose, onClose])

  const current = state ? (state.current ?? null) : null

  return (
    <Overlay onClose={onClose} width={520}>
      <OverlayLabel text="GAME OPTIONS" />
      <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 11, color: DIM, marginBottom: 22 }}>Overlay</div>

      {failed && (
        <div style={{ fontSize: 12.5, color: '#fbbf24', marginBottom: 16 }}>
          The overlay settings could not be read. The game still launches.
        </div>
      )}

      {rows.map((row, i) => {
        const selected = current === row.id
        const focused = focus === i
        return (
          <button
            key={row.id ?? 'auto'}
            onClick={() => choose(row.id)}
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
            <span style={{ width: 14, color: selected ? ACCENT : 'transparent' }}>●</span>
            <span style={{ flex: 1 }}>
              <span style={{ fontSize: 14 }}>{row.label}</span>
              <span style={{ display: 'block', fontSize: 11.5, color: DIM, marginTop: 2 }}>
                {row.hint}
              </span>
            </span>
          </button>
        )
      })}

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
    case 'system':   return 'No bezel for this game — the system’s is used'
    case 'declared': return 'No artwork installed — the configured frame is drawn'
    case 'chosen':   return 'Currently overridden below'
    default:         return 'No overlay is available for this system'
  }
}
