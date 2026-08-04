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
 * a television. Four things follow from that:
 *
 *  · **The focus has to drag the list with it.** The D-pad moved a highlight
 *    that the scroll container knew nothing about, so past the seventh row you
 *    were steering something off-screen.
 *
 *  · **Twenty systems in one column is a wall.** They are grouped by who made
 *    the hardware and the groups start CLOSED, so the screen opens on four
 *    lines — Microsoft, Nintendo, Sony, Applications — and you open the one you
 *    want. The grouping comes from `family` in pack.json, not from a table of
 *    ids in here: a pack for a machine nobody anticipated names its own maker
 *    and is grouped with its siblings without a line of this file changing.
 *
 *  · **A sticky heading hides the row underneath it.** `scrollIntoView` knows
 *    nothing about `position: sticky`: it aligns the row with the top of the
 *    scroll box, which is exactly where the heading is painted, so walking back
 *    up put the focused row behind it. `scroll-margin-top` is the seam for
 *    that — it tells the scroller the row starts higher than it does.
 *
 *  · **Removing is destructive and was one button press.** ✕ on a focused row
 *    removed a system with no confirmation, and the focused row is wherever
 *    the cursor happened to be. It now takes a second press, and moving the
 *    cursor disarms it.
 *
 *  · **Past a screenful, walking the list stops being navigation.** △ opens the
 *    virtual keyboard, and the filter runs over the label, the emulator's own
 *    name, the maker, the platform and the id — "dolphin" finds the GameCube
 *    slot, and so do "gamecube" and "nintendo".
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const mix = (pct: number) => `color-mix(in srgb, ${ACCENT} ${pct}%, transparent)`
const DANGER = '#f87171'

// Height a sticky heading occupies. scrollIntoView aligns a stop with the top
// of the scroll box, which is where the heading is painted, so every stop
// reserves this much above itself or walking back up hides the focused row
// behind it. That was the bug in the screenshot: the Xbox row sat under
// MICROSOFT with the heading nowhere to be seen.
const HEAD_H = '3.2rem'

const APPS = 'Applications'
const OTHER = 'Other'

interface Group { family: string; rows: CatalogEntry[]; installed: number }

/** What the cursor walks: the headings are stops too, because opening a maker
 *  is an action and the pad has no other way to reach one. */
type Item =
  | { kind: 'head'; family: string; group: Group }
  | { kind: 'row'; row: CatalogEntry }

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
  // Which makers are unfolded. Closed is the default: the point of grouping is
  // that the screen opens on four lines instead of twenty.
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  const logEndRef = useRef<HTMLDivElement>(null)
  const focusRowRef = useRef<HTMLDivElement>(null)

  /**
   * The catalogue, filtered and grouped by maker.
   *
   * Apps are their own group whatever they declare: Steam and YouTube have no
   * hardware maker, and filing them under the company that happens to own them
   * would put YouTube beside a games console.
   *
   * Makers are alphabetical, then Other, then Applications last — the two
   * catch-alls sink rather than interleave, so the shape of the screen does not
   * change when a pack forgets to declare a family.
   */
  const groups = useMemo<Group[]>(() => {
    const q = filter.trim().toLowerCase()
    // Every name a player might reach for. The slot is called "GameCube" and
    // runs "Dolphin"; someone who knows one does not necessarily know the other.
    const hit = (r: CatalogEntry) => !q || [
      r.label, r.emulatorName, r.platform, r.family, r.id, r.description,
    ].some(f => String(f || '').toLowerCase().includes(q))

    const buckets = new Map<string, CatalogEntry[]>()
    for (const r of (rows ?? []).filter(hit)) {
      const key = r.kind === 'app' ? APPS : (r.family?.trim() || OTHER)
      const b = buckets.get(key)
      if (b) b.push(r)
      else buckets.set(key, [r])
    }

    const rank = (f: string) => (f === APPS ? 2 : f === OTHER ? 1 : 0)
    return [...buckets.entries()]
      .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
      .map(([family, list]) => ({
        family,
        // Installed first inside a maker: "what do I have" is the question
        // asked most often, and the pill says which is which either way.
        rows: list.sort((x, y) =>
          Number(y.installed) - Number(x.installed) || x.label.localeCompare(y.label)),
        installed: list.filter(r => r.installed).length,
      }))
  }, [rows, filter])

  // Searching opens everything: a filter that matched three systems and left
  // them folded inside closed makers would look like it had found nothing.
  const searching = filter.trim().length > 0

  // One flat sequence for the cursor — headings included, so the pad walks
  // straight from "Nintendo" into its systems and out the other side.
  const items = useMemo<Item[]>(() => {
    const out: Item[] = []
    for (const g of groups) {
      out.push({ kind: 'head', family: g.family, group: g })
      if (searching || open.has(g.family)) {
        for (const r of g.rows) out.push({ kind: 'row', row: r })
      }
    }
    return out
  }, [groups, open, searching])

  const rowCount = useMemo(() => groups.reduce((n, g) => n + g.rows.length, 0), [groups])

  const toggle = useCallback((family: string) => {
    setArmed('')
    playSound('confirm')
    setOpen(prev => {
      const next = new Set(prev)
      if (!next.delete(family)) next.add(family)
      return next
    })
  }, [])

  const flatRef = useRef(items)
  const toggleRef = useRef(toggle)
  useEffect(() => { toggleRef.current = toggle }, [toggle])
  const busyRef = useRef(busyId)
  const focusRef = useRef(focusIdx)
  const armedRef = useRef(armed)
  useEffect(() => { flatRef.current = items }, [items])
  useEffect(() => { busyRef.current = busyId }, [busyId])
  useEffect(() => { focusRef.current = focusIdx }, [focusIdx])
  useEffect(() => { armedRef.current = armed }, [armed])

  // ○ closes the keyboard first, the page second — and the page's own handlers
  // are off while it is open.
  useSubPageGamepad(
    showSearch ? () => setShowSearch(false) : onBack,
    onClose,
    !showSearch,
  )

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
    if (items.length && focusIdx > items.length - 1) setFocusIdx(items.length - 1)
  }, [items.length, focusIdx])

  // Drag the list to the cursor. `block: 'nearest'` scrolls only when the row
  // is actually out of view, so walking the middle of the list does not jerk
  // the container on every step.
  useEffect(() => {
    focusRowRef.current?.scrollIntoView({ block: 'nearest' })
  }, [focusIdx, items.length])

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

  // Bound and unbound with the keyboard rather than guarded inside it: while it
  // is open these must not exist at all, or ✕ picks a letter AND acts on
  // whatever the list had focused.
  useEffect(() => {
    if (showSearch) return
    const move = (d: number) => {
      const n = flatRef.current.length
      if (!n) return
      setArmed('')                       // stepping away is how you say no
      setFocusIdx(i => Math.max(0, Math.min(n - 1, i + d)))
      playSound('move')
    }
    const offs = [
      onGp('gp:dpad-up', () => move(-1)),
      onGp('gp:dpad-down', () => move(1)),
      onGp('gp:confirm', () => {
        const it = flatRef.current[focusRef.current]
        if (!it) return
        if (it.kind === 'head') toggleRef.current(it.family)
        else void actRef.current(it.row)
      }),
      onGp('gp:y', () => { if (!busyRef.current) setShowSearch(true) }),
    ]
    return () => offs.forEach(o => o())
  }, [showSearch])

  /**
   * The keyboard replaces the page rather than sitting inside it.
   *
   * Rendered as a child of this page's Overlay it had nowhere to go: the list
   * above owns the flex height, so the keyboard came out squashed to nothing
   * and △ looked like it did nothing at all. WifiPage has always returned its
   * own Overlay for exactly this reason.
   */
  if (showSearch) {
    return (
      <Overlay onClose={onClose}>
        <BackHeader label="SEARCH" onBack={() => setShowSearch(false)} />
        <VirtualKeyboard
          title="Search emulators & apps"
          initialValue={filter}
          placeholder="name, maker, platform…"
          onConfirm={(val) => { setFilter(val.trim()); setShowSearch(false) }}
          onCancel={() => setShowSearch(false)}
        />
      </Overlay>
    )
  }

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
          <span style={{ opacity: 0.55 }}>{rowCount} of {rows?.length ?? 0}</span>
        </div>
      )}

      {error && <div style={{ color: DANGER, padding: '0 1.5rem 0.5rem' }}>{error}</div>}
      {rows === null && !error && (
        <div style={{ padding: '0 1.5rem', opacity: 0.6 }}>Loading the catalogue…</div>
      )}

      <div style={{ overflowY: 'auto', padding: '0 1.5rem', flex: 1, minHeight: 0 }}>
        {items.map((item, i) => {
          const focused = i === focusIdx
          // The seam that fixes walking back up into a sticky heading: the
          // scroller is told each stop begins HEAD_H higher than it draws, so
          // aligning it to the top leaves the heading its own room.
          const stop = { scrollMarginTop: HEAD_H }

          if (item.kind === 'head') {
            const g = item.group
            const isOpen = searching || open.has(g.family)
            return (
              <div
                key={`head:${g.family}`}
                ref={focused ? focusRowRef : undefined}
                onClick={() => toggle(g.family)}
                style={{
                  ...stop,
                  display: 'flex', alignItems: 'center', gap: 10,
                  margin: '0.6rem 0 0.35rem', padding: '0.55rem 0.8rem',
                  borderRadius: 12, cursor: 'pointer',
                  position: 'sticky', top: 0, zIndex: 1,
                  fontSize: '0.74rem', letterSpacing: '0.12em',
                  textTransform: 'uppercase', fontWeight: 700,
                  background: focused ? mix(26) : 'var(--gc-overlay-bg, rgba(12,10,20,0.96))',
                  border: `1px solid ${focused ? mix(60) : 'transparent'}`,
                  transition: 'background 120ms ease, border-color 120ms ease',
                }}
              >
                <span style={{
                  display: 'inline-block', width: '0.7em', flexShrink: 0,
                  transform: isOpen ? 'rotate(90deg)' : 'none',
                  transition: 'transform 140ms ease', opacity: 0.75,
                }}>▶</span>
                <span style={{ flex: 1, minWidth: 0 }}>{g.family}</span>
                <span style={{ letterSpacing: 0, opacity: 0.6, fontWeight: 600 }}>
                  {g.installed}/{g.rows.length}
                </span>
              </div>
            )
          }

          const row = item.row
          const running = busyId === row.id
          const isArmed = armed === row.id

          return (
            <div
              key={row.id}
              ref={focused ? focusRowRef : undefined}
              onClick={() => void act(row)}
              style={{
                ...stop,
                display: 'flex', alignItems: 'center', gap: '0.9rem',
                padding: '0.7rem 0.9rem', marginBottom: '0.4rem', borderRadius: 12,
                marginLeft: '1.1rem',           // indented: it belongs to the maker above
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
          )
        })}

        {rows !== null && rowCount === 0 && !error && (
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
            : `✕ ${items[focusIdx]?.kind === 'head' ? 'open or close' : 'install or remove'}`
              + ` · △ ${filter.trim() ? 'change filter' : 'search'} · ○ back`}
      </div>

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
