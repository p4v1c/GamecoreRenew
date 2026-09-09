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
import ErrorBoundary from './ErrorBoundary'
import { useThemeCtx } from './ThemeSurface'

/** The menu must be gone before a theme starts drawing its handover. */
const SESSION_MENU_EXIT_MS = 150

/** One thing the menu can do, already resolved to a label and a handler. */
export interface SessionAction {
  id: 'resume' | 'close' | 'back' | 'keep' | 'confirm-close'
  label: string
  /** The one that ends a session. Themes draw it as the dangerous one. */
  danger?: boolean
  /** The one a player most likely wants. Themes draw it as the primary one. */
  primary?: boolean
  run: () => void
}

export interface SessionMenuProps {
  /** The session being managed. */
  session: BackgroundSession
  /** Every suspended session, so a theme can show which of them this is. */
  sessions: BackgroundSession[]
  index: number
  /** True once Close has been chosen and is waiting to be confirmed. */
  confirming: boolean
  busy: boolean
  actions: SessionAction[]
  /** Which action the pad is on. */
  actionIdx: number
  title: (s: BackgroundSession) => string
  /** Mouse affordances; the pad goes through the host's own bindings. */
  onFocus: (i: number) => void
  onClose: () => void
}

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
  /**
   * Open the menu — the same thing L2 does, for a theme that would rather
   * offer one button than repeat the menu's own choices on the bar.
   *
   * Orbit drew Resume and "Close game" side by side, which is the menu's first
   * two options spelled out a second time, in a place where neither could be
   * reached with a pad. One button that opens the menu is the honest version:
   * every action lives in one place, and that place is the one the pad can
   * drive.
   */
  onManage: () => void
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

export const nounOf = (s: BackgroundSession) => s.kind === 'app' ? 'application' : 'game'

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
      >{p.busy ? 'Working…' : resumeLabel(s)}</button>
      <button
        onClick={() => p.onClose(s)} disabled={p.busy}
        style={{
          padding: '9px 18px', borderRadius: 9, cursor: 'pointer',
          border: '1px solid rgba(255,255,255,0.22)',
          background: 'transparent', color: '#fff', fontSize: 14,
        }}
      >{closeLabel(s)}</button>
      <kbd style={{ opacity: 0.45, fontSize: 11 }}>L2</kbd>
    </div>
  )
}

function DefaultSessionMenuView(p: SessionMenuProps) {
  return (
    <div style={{
      padding: 30, borderRadius: 18, minWidth: 340, maxWidth: 520,
      background: '#12121b', border: '1px solid rgba(124,58,237,0.4)',
      fontFamily: "'Outfit', sans-serif", color: '#fff',
    }}>
      <div style={{ fontSize: 10, letterSpacing: 1.6, opacity: 0.55 }}>
        {p.confirming ? 'END THIS SESSION' : 'SUSPENDED SESSION'}
        {p.sessions.length > 1 && ` · ${p.index + 1}/${p.sessions.length}`}
      </div>
      <h2 style={{ margin: '6px 0 10px', fontSize: 22 }}>{p.title(p.session)}</h2>
      <p style={{ margin: '0 0 20px', fontSize: 14, opacity: 0.75, lineHeight: 1.5 }}>
        {p.confirming
          ? `This ends the ${p.session.kind === 'app' ? 'application' : 'game'}. Anything it has not saved is lost.`
          : 'Frozen exactly where you left it. No playtime is counting.'}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {p.actions.map((a, i) => (
          <button key={a.id} disabled={p.busy} onFocus={() => p.onFocus(i)}
            onClick={a.run}
            style={{
              padding: '13px 18px', borderRadius: 10, border: 'none', cursor: 'pointer',
              textAlign: 'left', fontSize: 15, color: '#fff',
              background: p.actionIdx === i
                ? (a.danger ? '#b3324a' : '#7c3aed') : 'rgba(255,255,255,0.07)',
            }}>{p.busy ? 'Working…' : a.label}</button>
        ))}
      </div>
      <p style={{ marginTop: 18, fontSize: 11, opacity: 0.5 }}>
        ↑ ↓ Choose · ✕ Confirm · ○ Back
      </p>
    </div>
  )
}

export default function SessionBar(
  { view, menuView }: { view?: ComponentType<SessionBarProps>
                        menuView?: ComponentType<SessionMenuProps> }) {
  const sessions = useStore(s => s.backgroundSessions)
  const foreground = useStore(s => s.sessionGameKey)
  const modalDepth = useStore(s => s.modalDepth)
  const [focusIdx, setFocusIdx] = useState(0)
  const [busy, setBusy] = useState(false)
  const [menu, setMenu] = useState(false)
  const [confirming, setConfirming] = useState(false)

  // `active` is what a theme draws its cursor from: the bar can be acted on
  // right now. It does not mean the bar owns any button — it owns none while it
  // is just a bar, which is the correction. See the L2 effect below.
  const active = sessions.length > 0 && !foreground && modalDepth === 0

  const stateRef = useRef({ sessions, focusIdx, active, busy, menu, confirming })
  stateRef.current = { sessions, focusIdx, active, busy, menu, confirming }

  useEffect(() => {
    if (focusIdx > sessions.length - 1) setFocusIdx(Math.max(0, sessions.length - 1))
  }, [sessions.length, focusIdx])

  const act = async (fn: () => Promise<unknown>) => {
    if (stateRef.current.busy) return
    setBusy(true)
    try { await fn() } catch (e) { console.error('[gamecore] session action failed:', e) }
    finally { setBusy(false) }
  }

  /**
   * Coming back to a frozen game is a launch as far as the player is concerned,
   * so it gets the same ceremony and the same hold.
   *
   * `launch.ms` is the theme's own number and it already means "how long my
   * handover animation runs". Resuming without honouring it was the same defect
   * the launch had before the hold existed: the emulator takes the screen the
   * moment the call returns, and whatever the theme was drawing is cut off
   * mid-frame.
   */
  const ceremonyMs = useThemeCtx()?.manifest?.launch?.ms ?? 0

  const resumeSession = async (s: BackgroundSession) => {
    const store = useStore.getState()
    store.setTransition('resume')
    try {
      if (ceremonyMs > 0) await new Promise(r => setTimeout(r, ceremonyMs))
      await api.games.foreground(s.session)
    } finally {
      store.setTransition(null)
    }
  }

  const resume = (s: BackgroundSession) => act(() => resumeSession(s))

  /** The pointer's way to the menu, guarded exactly as the L2 binding is. */
  const manage = () => {
    const s = useStore.getState()
    if (!s.backgroundSessions.length) return
    if (s.sessionGameKey || s.powerPending || s.standby !== 'off' || s.modalDepth) return
    setConfirming(false)
    setActionIdx(0)
    setMenu(true)
  }
  // A pointer click on Close goes through the same confirmation the pad does:
  // ending a session is the one action here that cannot be undone, and it
  // should not be one stray click away.
  const close = (s: BackgroundSession) => {
    setFocusIdx(sessions.indexOf(s))
    setConfirming(true)
    setActionIdx(0)
    setMenu(true)
  }

  /**
   * L2 opens the menu, and ✕ does NOT act on the bar.
   *
   * Both halves of that are corrections. The bar used to take `gp:confirm`
   * whenever it was on screen — and `HomeScreen` takes it too, so one press
   * resumed the suspended session *and* opened whatever tile the cursor was on.
   * A bar drawn over a live screen cannot borrow that screen's buttons.
   *
   * And Close was reachable with a pointer and nothing else, which on a console
   * is not reachable at all: the player could resume a session forever and
   * never end one. So the actions live in a modal instead. A modal is what
   * makes them safe — `openModal()` raises `modalDepth`, and every host handler
   * already stands down on it — and it is also what gives Close somewhere to
   * ask before doing something that cannot be undone.
   *
   * L2 because the host binds nothing to it. A theme may (Shelf turns its box
   * with it), so it is only taken while something is actually suspended: the
   * rest of the time the press goes through untouched.
   */
  useEffect(() => {
    const off = onGp('gp:l2', () => {
      const s = useStore.getState()
      if (!s.backgroundSessions.length) return
      if (stateRef.current.menu) { setMenu(false); return }
      // Never over a game, a power action, standby, or another modal.
      if (s.sessionGameKey || s.powerPending || s.standby !== 'off' || s.modalDepth) return
      setMenu(true)
    })
    return off
  }, [])

  // Nothing left to manage — closed from elsewhere, or killed from under us.
  useEffect(() => {
    if (!sessions.length && menu) setMenu(false)
  }, [sessions.length, menu])

  const [actionIdx, setActionIdx] = useState(0)
  const current = sessions[Math.min(focusIdx, Math.max(0, sessions.length - 1))]

  const actions: SessionAction[] = !current ? []
    : confirming
      ? [{ id: 'keep', label: 'Keep it running', primary: true,
           run: () => { setConfirming(false); setActionIdx(0) } },
         { id: 'confirm-close', label: `Close ${nounOf(current)}`, danger: true,
           run: () => act(async () => { await api.games.kill(current.session); setMenu(false) }) }]
      : [{ id: 'resume', label: resumeLabel(current), primary: true,
           run: () => act(async () => {
             playSound('launch')
             // The menu closes FIRST, so the theme's ceremony is drawn over the
             // interface rather than behind a dialog that is about to vanish.
             setMenu(false)
             await new Promise(r => setTimeout(r, SESSION_MENU_EXIT_MS))
             await resumeSession(current)
           }) },
         { id: 'close', label: `${closeLabel(current)}…`,
           run: () => { setConfirming(true); setActionIdx(0) } },
         { id: 'back', label: 'Back', run: () => setMenu(false) }]

  const menuRef = useRef({ actions, actionIdx, confirming })
  menuRef.current = { actions, actionIdx, confirming }

  useEffect(() => { setActionIdx(0) }, [confirming, focusIdx])
  useEffect(() => { if (!menu) setConfirming(false) }, [menu])

  /**
   * While the menu is up it owns the pad, and it is allowed to because it is a
   * real modal: `openModal()` raises `modalDepth`, which every host screen
   * already checks before acting on anything.
   */
  useEffect(() => {
    if (!menu) return
    const previous = document.activeElement as HTMLElement | null
    useStore.getState().openModal()
    const depth = useStore.getState().modalDepth
    const mine = () => useStore.getState().modalDepth === depth
    const move = (d: number) => {
      if (!mine()) return
      const n = menuRef.current.actions.length
      if (n) setActionIdx(i => (i + d + n) % n)
    }
    const offs = [
      onGp('gp:dpad-up', () => move(-1)),
      onGp('gp:dpad-down', () => move(1)),
      onGp('gp:dpad-left', () => move(-1)),
      onGp('gp:dpad-right', () => move(1)),
      onGp('gp:confirm', () => {
        if (!mine()) return
        menuRef.current.actions[menuRef.current.actionIdx]?.run()
      }),
      onGp('gp:back', () => {
        if (!mine()) return
        if (menuRef.current.confirming) { setConfirming(false); setActionIdx(0) }
        else setMenu(false)
      }),
      // More than one suspended session: L1/R1 walk between them, which is
      // where that gesture belonged all along — on the bar it competed with a
      // live screen's own page turns.
      onGp('gp:l1', () => { if (mine()) setFocusIdx(i => (i - 1 + sessions.length) % sessions.length) }),
      onGp('gp:r1', () => { if (mine()) setFocusIdx(i => (i + 1) % sessions.length) }),
    ]
    return () => {
      offs.forEach(off => off())
      useStore.getState().closeModal()
      // Focus goes back where it was, or the player lands at the top of the
      // document with a cursor they did not move.
      if (previous?.isConnected) previous.focus({ preventScroll: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [menu, sessions.length])

  const View = view ?? DefaultSessionBarView
  const MenuView = menuView ?? DefaultSessionMenuView
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

  const menuProps: SessionMenuProps = {
    session: current!, sessions, index: Math.min(focusIdx, Math.max(0, sessions.length - 1)),
    confirming, busy, actions, actionIdx, title,
    onFocus: setActionIdx, onClose: () => setMenu(false),
  }

  const viewProps: SessionBarProps = {
    sessions, focusIdx: Math.min(focusIdx, Math.max(0, sessions.length - 1)),
    active, busy, title, onFocus: setFocusIdx, onResume: resume, onClose: close,
    onManage: manage,
  }

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
          {/* A theme can lose the bar by CRASHING as surely as by omitting it,
              and the outcome is identical: a frozen emulator holding gigabytes
              with nothing on screen able to resume or close it, and the
              player's only remaining move the power button. Omitting was
              already covered by the host's default view; this covers throwing.

              The fallback is that same default view, so what the player gets is
              the wrong colours rather than no way out. */}
          <ErrorBoundary fallback={<DefaultSessionBarView {...viewProps} />}>
            <View {...viewProps} />
          </ErrorBoundary>
        </motion.div>
      )}
      {menu && current && (
        <motion.div key="session-menu"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: SESSION_MENU_EXIT_MS / 1000 }}
          style={{
            position: 'fixed', inset: 0, zIndex: 700, display: 'grid',
            placeItems: 'center', background: 'rgba(4,7,14,0.72)',
          }}>
          <ErrorBoundary fallback={<DefaultSessionMenuView {...menuProps} />}>
            <MenuView {...menuProps} />
          </ErrorBoundary>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
