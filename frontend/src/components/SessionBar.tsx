/**
 * The way back to a suspended session — and the host's guarantee that there
 * always is one.
 *
 * Drawn above the theme's shell rather than inside it, and drawn whether or not
 * the theme asked for it. A theme exports `sessionBar` to replace the picture;
 * it cannot remove the bar, because omitting it would leave a frozen emulator
 * holding several gigabytes of RAM with nothing on screen able to resume or
 * close it, and the player's only way out would be the power button. Suspending
 * is reachable from a gesture the core owns (double Home), so the way back has
 * to be owned by the core too.
 *
 * The bindings are deliberately narrow. This sits over whatever screen the
 * player was on, so it takes ✕ and ○ only while it is focused, and it takes
 * them through the same modal-depth lock every other overlay uses — otherwise
 * confirming here would also launch the game underneath.
 */
import { useEffect, useRef, useState, type ComponentType } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore, type BackgroundSession } from '../store'
import { onGp } from '../hooks/useGamepad'
import { api } from '../api'
import { playSound } from '../lib/sounds'
import { formatGameName } from '../lib/formatGameName'

export interface SessionBarProps {
  /** Suspended sessions, oldest first. Never empty when this renders. */
  sessions: BackgroundSession[]
  /** Which one the cursor is on. */
  focusIdx: number
  /** True while the bar owns the pad — a theme should show its cursor then. */
  active: boolean
  /** True while a resume or close is in flight. */
  busy: boolean
  /** `Super_Mario_64_(USA).z64` → `Super Mario 64`, already applied. */
  title: (s: BackgroundSession) => string
  onFocus: (i: number) => void
  onResume: (s: BackgroundSession) => void
  onClose: (s: BackgroundSession) => void
}

/**
 * `Zelda_(USA).iso` → `Zelda_`. Extension off, bracketed and parenthesised tags
 * out — the same two things `clean_name` does in
 * backend/services/rom_scanner.py, which is where a library entry's
 * `display_name` comes from. The point is that a suspended game is named the
 * way the library named it, not the way the disk did.
 */
const cleanRomName = (filename: string) =>
  filename.replace(/\.[^.]+$/, '').replace(/[([{][^)\]}]*[)\]}]/g, '').trim()

/** What the button says. An application is not a game, and saying so is the
 *  difference between an interface that knows what it started and one that
 *  calls Stremio a game. */
export const closeLabel = (s: BackgroundSession) =>
  s.kind === 'app' ? 'Close application' : 'Close game'

export const resumeLabel = (s: BackgroundSession) =>
  s.kind === 'app' ? 'Back to application' : 'Resume game'

function DefaultSessionBarView(p: SessionBarProps) {
  const s = p.sessions[p.focusIdx] ?? p.sessions[0]
  if (!s) return null
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 14,
        padding: '12px 22px',
        background: 'linear-gradient(0deg, rgba(9,9,15,0.98), rgba(9,9,15,0.86))',
        borderTop: '1px solid rgba(124,58,237,0.45)',
        fontFamily: "'Outfit', sans-serif", color: '#fff',
      }}
      role="region" aria-label="Suspended session"
    >
      <span style={{
        width: 8, height: 8, borderRadius: '50%', background: '#7c3aed',
        boxShadow: '0 0 10px #7c3aed', flex: '0 0 auto',
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 10, letterSpacing: 1.6, opacity: 0.55 }}>
          {s.kind === 'app' ? 'APPLICATION IN THE BACKGROUND' : 'GAME IN THE BACKGROUND'}
          {p.sessions.length > 1 && ` · ${p.focusIdx + 1}/${p.sessions.length}`}
        </div>
        <strong style={{
          fontSize: 16, display: 'block', overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{p.title(s)}</strong>
      </div>
      <button
        onClick={() => p.onResume(s)} disabled={p.busy}
        style={{
          padding: '9px 18px', borderRadius: 9, border: 'none', cursor: 'pointer',
          background: p.active ? '#7c3aed' : 'rgba(124,58,237,0.35)',
          color: '#fff', fontWeight: 600, fontSize: 14,
        }}
      >{p.busy ? 'Working…' : resumeLabel(s)} <kbd style={{ opacity: 0.7 }}>✕</kbd></button>
      <button
        onClick={() => p.onClose(s)} disabled={p.busy}
        style={{
          padding: '9px 18px', borderRadius: 9, cursor: 'pointer',
          border: '1px solid rgba(255,255,255,0.22)',
          background: 'transparent', color: '#fff', fontSize: 14,
        }}
      >{closeLabel(s)}</button>
    </div>
  )
}

export default function SessionBar({ view }: { view?: ComponentType<SessionBarProps> }) {
  const sessions = useStore(s => s.backgroundSessions)
  const foreground = useStore(s => s.sessionGameKey)
  const modalDepth = useStore(s => s.modalDepth)
  const [focusIdx, setFocusIdx] = useState(0)
  const [busy, setBusy] = useState(false)

  // The bar only takes the pad when nothing is in front of it: no game on the
  // screen, no modal open. Otherwise ✕ would both confirm here and launch
  // whatever the cursor is on underneath.
  const active = sessions.length > 0 && !foreground && modalDepth === 0

  const stateRef = useRef({ sessions, focusIdx, active, busy })
  stateRef.current = { sessions, focusIdx, active, busy }

  useEffect(() => {
    if (focusIdx > sessions.length - 1) setFocusIdx(Math.max(0, sessions.length - 1))
  }, [sessions.length, focusIdx])

  const act = async (fn: () => Promise<unknown>) => {
    if (stateRef.current.busy) return
    setBusy(true)
    try { await fn() } catch (e) { console.error('[gamecore] session action failed:', e) }
    finally { setBusy(false) }
  }

  const resume = (s: BackgroundSession) => act(() => api.games.foreground(s.session))
  const close = (s: BackgroundSession) => act(() => api.games.kill(s.session))

  useEffect(() => {
    const offs = [
      // ✕ resumes. The single most likely thing the player wants from a bar
      // that exists because they suspended something a moment ago.
      onGp('gp:confirm', () => {
        const { sessions: list, focusIdx: i, active: on } = stateRef.current
        if (!on) return
        const s = list[i]
        if (s) { playSound('launch'); resume(s) }
      }),
      // L1/R1 walk the list when there is more than one. Not the d-pad: that
      // belongs to the screen underneath, which is still live.
      onGp('gp:l1', () => {
        const { sessions: list, active: on } = stateRef.current
        if (!on || list.length < 2) return
        setFocusIdx(i => (i - 1 + list.length) % list.length)
      }),
      onGp('gp:r1', () => {
        const { sessions: list, active: on } = stateRef.current
        if (!on || list.length < 2) return
        setFocusIdx(i => (i + 1) % list.length)
      }),
    ]
    return () => offs.forEach(off => off())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const View = view ?? DefaultSessionBarView
  /**
   * What the player is shown, from what the box keys the session by.
   *
   * A session is identified by its ROM FILENAME — `Zelda_(USA).iso` — which is
   * not a title. Everywhere else the library has already been through the
   * backend's `clean_name` and hands the UI a `display_name`; here there is no
   * library entry to ask, only the key. So the same two steps happen locally:
   * drop the extension and the bracketed tags, then the shared
   * `formatGameName`. Without it this bar would be the one place in the
   * interface that calls a game by its file.
   */
  const title = (s: BackgroundSession) =>
    s.kind === 'app'
      ? (s.systemId || s.gameKey)
      : formatGameName(cleanRomName(s.gameKey))

  return (
    <AnimatePresence>
      {sessions.length > 0 && (
        /* The HOST supplies the layer and the theme draws inside it — the same
           bargain as the themed splash in App.tsx, and for the same reason.
           Themes are forbidden to write a z-index (docs/themes/README.md §6:
           the shell owns stacking), and Shelf's stylesheet says so in its own
           header. A bar that had to position itself would force every theme to
           break that rule to be visible at all. */
        <motion.div
          key="session-bar"
          initial={{ y: 90, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
          exit={{ y: 90, opacity: 0 }} transition={{ duration: 0.22 }}
          style={{ position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 300 }}
        >
          <View
            sessions={sessions} focusIdx={Math.min(focusIdx, sessions.length - 1)}
            active={active} busy={busy} title={title}
            onFocus={setFocusIdx} onResume={resume} onClose={close}
          />
        </motion.div>
      )}
    </AnimatePresence>
  )
}
