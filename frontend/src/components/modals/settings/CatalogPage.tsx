import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { VirtualKeyboard } from '../../ui/VirtualKeyboard'
import { api, type CatalogEntry } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { onWsEvent } from '../../../hooks/useWebSocket'
import { playSound } from '../../../lib/sounds'
import { useSubPageGamepad } from './useSubPageGamepad'

/**
 * Add an emulator to a box that is already running, or take one off it.
 *
 * Before this screen the catalogue was frozen at install time: adding a system
 * meant re-running the installer over SSH, which overwrote config/systems.json
 * and took the box's own grid with it.
 *
 * One action at a time — the backend answers 409 to a second one — so the
 * whole list is disabled while something is running rather than letting a
 * player queue up four installs and watch three of them fail.
 *
 * ── What this screen has to survive ────────────────────────────────────────
 * It is the longest list in the settings modal and the only one that grows: a
 * box with the shipped catalogue plus local packs shows more rows than fit on
 * a television. Three things follow from that, and none of them were true
 * before:
 *
 *  · **The focus has to drag the list with it.** The D-pad moved a highlight
 *    that the scroll container knew nothing about, so past the seventh row you
 *    were steering something off-screen. No other settings page is long enough
 *    for this to bite, which is why the pattern was missing here.
 *
 *  · **Installed and available are different questions.** One flat list mixed
 *    "what do I have" with "what could I add", and answering either meant
 *    reading every row. They are two sections now, each with its count.
 *
 *  · **Removing is destructive and was one button press.** ✕ on a focused row
 *    removed a system with no confirmation, and the focused row is wherever
 *    the cursor happened to be. It now takes a second press, and moving the
 *    cursor disarms it.
 *
 *  · **Past a screenful, walking the list stops being navigation.** △ opens the
 *    same virtual keyboard the library search uses, and the filter runs over
 *    the label, the emulator's own name, the platform and the id — "dolphin"
 *    finds the GameCube slot, and so does "gamecube".
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const mix = (pct: number) => `color-mix(in srgb, ${ACCENT} ${pct}%, transparent)`
const DANGER = '#f87171'

export function CatalogPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [rows, setRows] = useState<CatalogEntry[] | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const [log, setLog] = useState<string[]>([])
  const [focusIdx, setFocusIdx] = useState(0)
  // The id whose removal is armed. Removal is the one irreversible thing on
  // this screen, so it asks twice; nothing else here does.
  const [armed, setArmed] = useState('')
  const [filter, setFilter] = useState('')
  const [showSearch, setShowSearch] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const focusRowRef = useRef<HTMLDivElement>(null)

  /**
   * Installed first, then available, each alphabetical.
   *
   * The order is derived rather than stored because the list reorders itself
   * the moment an action lands — install something and it moves sections. The
   * cursor is therefore restored by id below, not by index, or finishing an
   * install would jump the highlight to whatever slid into that slot.
   */
  const ordered = useMemo(() => {
    const by = (a: CatalogEntry, b: CatalogEntry) => a.label.localeCompare(b.label)
    const q = filter.trim().toLowerCase()
    // Every name a player might reach for. The slot is called "GameCube" and
    // runs "Dolphin"; someone who knows one does not necessarily know the other.
    const hit = (r: CatalogEntry) => !q || [
      r.label, r.emulatorName, r.platform, r.id, r.description,
    ].some(f => String(f || '').toLowerCase().includes(q))
    const all = (rows ?? []).filter(hit)
    return [...all.filter(r => r.installed).sort(by), ...all.filter(r => !r.installed).sort(by)]
  }, [rows, filter])

  const installedCount = ordered.filter(r => r.installed).length

  const rowsRef = useRef(ordered)
  const busyRef = useRef(busyId)
  const focusRef = useRef(focusIdx)
  const armedRef = useRef(armed)
  useEffect(() => { rowsRef.current = ordered }, [ordered])
  useEffect(() => { busyRef.current = busyId }, [busyId])
  useEffect(() => { focusRef.current = focusIdx }, [focusIdx])
  useEffect(() => { armedRef.current = armed }, [armed])
  // The handlers below are bound once; without this they would read the value
  // of `showSearch` captured on the first render and keep stepping the list
  // underneath an open keyboard.
  const searchRef = useRef(showSearch)
  useEffect(() => { searchRef.current = showSearch }, [showSearch])

  useSubPageGamepad(onBack, onClose, !showSearch)

  const load = useCallback(async () => {
    try {
      setRows(await api.catalog.list())
      setError('')
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  // A new filter is a new list; leaving the cursor at row 9 of a two-row result
  // hides it off the end.
  useEffect(() => { setFocusIdx(0); setArmed('') }, [filter])

  // A list that has just reordered can be shorter than where the cursor was —
  // remove the last row and the index points past the end, which reads as the
  // highlight vanishing.
  useEffect(() => {
    if (ordered.length && focusIdx > ordered.length - 1) setFocusIdx(ordered.length - 1)
  }, [ordered.length, focusIdx])

  // Drag the list to the cursor. `block: 'nearest'` scrolls only when the row
  // is actually out of view, so walking the middle of the list does not jerk
  // the container on every step.
  useEffect(() => {
    focusRowRef.current?.scrollIntoView({ block: 'nearest' })
  }, [focusIdx, ordered.length])

  // Progress arrives on the WebSocket the addons screen already uses, so a
  // long Flatpak download shows something rather than a frozen row.
  useEffect(() => {
    const offs = [
      onWsEvent('catalog:log', d =>
        setLog(l => [...l.slice(-200), String(d.line ?? '')])),
      onWsEvent('catalog:done', d => {
        setBusyId('')
        if (!d.success) setError('The operation reported an error — see the log below.')
        void load()
      }),
    ]
    return () => offs.forEach(o => o())
  }, [load])

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [log])

  const act = useCallback(async (row: CatalogEntry) => {
    if (busyRef.current) return
    // Installing is additive and reversible from this same screen. Removing is
    // not, so it is armed first and confirmed second.
    if (row.installed && armedRef.current !== row.id) {
      setArmed(row.id)
      playSound('move')
      return
    }
    setArmed('')
    setBusyId(row.id)
    setLog([])
    setError('')
    playSound('confirm')
    try {
      await (row.installed ? api.catalog.remove(row.id) : api.catalog.install(row.id))
    } catch (e) {
      setBusyId('')
      setError(String(e))
    }
  }, [])

  const actRef = useRef(act)
  useEffect(() => { actRef.current = act }, [act])

  useEffect(() => {
    const move = (d: number) => {
      const n = rowsRef.current.length
      if (!n) return
      setArmed('')                       // stepping away is how you say no
      setFocusIdx(i => Math.max(0, Math.min(n - 1, i + d)))
      playSound('move')
    }
    const offs = [
      onGp('gp:dpad-up', () => { if (searchRef.current) return; move(-1) }),
      onGp('gp:dpad-down', () => { if (searchRef.current) return; move(1) }),
      onGp('gp:confirm', () => {
        if (searchRef.current) return
        const row = rowsRef.current[focusRef.current]
        if (row) void actRef.current(row)
      }),
      onGp('gp:y', () => { if (!busyRef.current) setShowSearch(true) }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  const section = (label: string, count: number) => (
    <div style={{
      display: 'flex', alignItems: 'baseline', gap: 8,
      padding: '0.9rem 0 0.45rem', fontSize: '0.72rem', letterSpacing: '0.12em',
      textTransform: 'uppercase', opacity: 0.55, fontWeight: 700,
    }}>
      <span>{label}</span>
      <span style={{ opacity: 0.7, letterSpacing: 0 }}>{count}</span>
    </div>
  )

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="EMULATORS & APPS" onBack={onBack} />

      {filter.trim() && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, margin: '0 1.5rem 0.5rem',
          padding: '0.4rem 0.75rem', borderRadius: 999, background: mix(20),
          border: `1px solid ${mix(45)}`, fontSize: '0.78rem', width: 'fit-content',
        }}>
          <span style={{ opacity: 0.6 }}>filter</span>
          <b style={{ color: 'var(--gc-accent-bright, #c4b5fd)' }}>{filter.trim()}</b>
          <span style={{ opacity: 0.55 }}>
            {ordered.length} of {rows?.length ?? 0}
          </span>
        </div>
      )}

      {error && <div style={{ color: DANGER, padding: '0 1.5rem 0.5rem' }}>{error}</div>}
      {rows === null && !error && (
        <div style={{ padding: '0 1.5rem', opacity: 0.6 }}>Loading the catalogue…</div>
      )}

      <div style={{ overflowY: 'auto', padding: '0 1.5rem', flex: 1, minHeight: 0 }}>
        {ordered.map((row, i) => {
          const running = busyId === row.id
          const focused = i === focusIdx
          const isArmed = armed === row.id
          const head = i === 0 || ordered[i - 1].installed !== row.installed

          return (
            <div key={row.id}>
              {head && section(
                row.installed ? 'On the grid' : 'Available',
                row.installed ? installedCount : ordered.length - installedCount,
              )}

              <div
                ref={focused ? focusRowRef : undefined}
                onClick={() => void act(row)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.9rem',
                  padding: '0.7rem 0.9rem', marginBottom: '0.4rem', borderRadius: 12,
                  cursor: busyId ? 'default' : 'pointer',
                  opacity: busyId && !running ? 0.35 : 1,
                  background: isArmed ? 'rgba(248,113,113,0.14)'
                    : focused ? mix(18) : 'rgba(255,255,255,0.045)',
                  border: `1px solid ${isArmed ? 'rgba(248,113,113,0.55)'
                    : focused ? mix(55) : 'transparent'}`,
                  transition: 'background 120ms ease, border-color 120ms ease',
                }}
              >
                {/* The system's own colour, the same one its tile carries on the
                    grid — the fastest way to find a row you already know. */}
                <div style={{
                  width: 4, alignSelf: 'stretch', minHeight: 34, borderRadius: 2,
                  background: row.color, flexShrink: 0,
                }} />

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 600, display: 'flex', alignItems: 'center',
                    gap: 8, minWidth: 0,
                  }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.label}
                    </span>
                    {row.kind === 'app' && (
                      <span style={{
                        fontSize: '0.6rem', letterSpacing: '0.08em', padding: '2px 6px',
                        borderRadius: 999, background: 'rgba(255,255,255,0.1)',
                        opacity: 0.75, flexShrink: 0,
                      }}>APP</span>
                    )}
                    {row.origin === 'local' && (
                      <span style={{
                        fontSize: '0.6rem', letterSpacing: '0.08em', padding: '2px 6px',
                        borderRadius: 999, background: mix(28),
                        color: 'var(--gc-accent-bright, #c4b5fd)', flexShrink: 0,
                      }}>LOCAL</span>
                    )}
                  </div>

                  <div style={{
                    fontSize: '0.78rem', opacity: 0.55, overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {row.description || row.emulatorName}
                  </div>

                  {row.restricted.length > 0 && (
                    // A local pack is data only unless the operator opted in.
                    // Saying which blocks were ignored is what stops "why did my
                    // generator not run" being a mystery.
                    <div style={{ fontSize: '0.7rem', color: '#ffb347', marginTop: 2 }}>
                      ignored (local pack): {row.restricted.join(', ')}
                    </div>
                  )}
                </div>

                <div style={{
                  fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.04em',
                  whiteSpace: 'nowrap', padding: '0.35rem 0.7rem', borderRadius: 999,
                  flexShrink: 0,
                  background: isArmed ? 'rgba(248,113,113,0.22)'
                    : row.installed ? 'rgba(255,255,255,0.07)' : mix(30),
                  color: isArmed ? DANGER
                    : row.installed ? 'rgba(255,255,255,0.75)'
                    : 'var(--gc-accent-bright, #c4b5fd)',
                  border: `1px solid ${isArmed ? 'rgba(248,113,113,0.5)' : 'transparent'}`,
                }}>
                  {running ? 'Working…' : isArmed ? 'Confirm?' : row.installed ? 'Remove' : 'Install'}
                </div>
              </div>
            </div>
          )
        })}

        {rows !== null && ordered.length === 0 && !error && (
          <div style={{ padding: '1rem 0', opacity: 0.6 }}>
            {filter.trim()
              ? `Nothing matches "${filter.trim()}".`
              : 'The catalogue is empty — no packs are installed on this box.'}
          </div>
        )}
      </div>

      <div style={{
        padding: '0.5rem 1.5rem 0', fontSize: '0.72rem', opacity: 0.45,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {busyId
          ? 'Working — the list is held until this finishes.'
          : armed
            ? 'Press ✕ again to remove it · any direction cancels'
            : `✕ install or remove · △ ${filter.trim() ? 'change filter' : 'search'} · ○ back`}
      </div>

      {showSearch && (
        <VirtualKeyboard
          title="Search emulators & apps"
          initialValue={filter}
          placeholder="name, platform or emulator…"
          onConfirm={(val) => { setFilter(val.trim()); setShowSearch(false) }}
          onCancel={() => setShowSearch(false)}
        />
      )}

      {log.length > 0 && (
        <pre style={{
          margin: '0.5rem 1.5rem 1rem', padding: '0.75rem', maxHeight: '9rem',
          overflowY: 'auto', fontSize: '0.72rem', lineHeight: 1.4,
          background: 'rgba(0,0,0,0.35)', borderRadius: 8, whiteSpace: 'pre-wrap',
        }}>
          {log.join('\n')}
          <div ref={logEndRef} />
        </pre>
      )}
    </Overlay>
  )
}
