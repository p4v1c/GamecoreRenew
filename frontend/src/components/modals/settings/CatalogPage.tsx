import { useState, useEffect, useRef, useCallback } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { api, type CatalogEntry } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { onWsEvent } from '../../../hooks/useWebSocket'
import { useSubPageGamepad } from './useSubPageGamepad'

/**
 * Add an emulator to a box that is already running.
 *
 * Before this screen the catalogue was frozen at install time: adding a system
 * meant re-running the installer over SSH, which overwrote config/systems.json
 * and took the box's own grid with it.
 *
 * One action at a time — the backend answers 409 to a second one — so the
 * whole list is disabled while something is running rather than letting a
 * player queue up four installs and watch three of them fail.
 */
export function CatalogPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [rows, setRows] = useState<CatalogEntry[] | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const [log, setLog] = useState<string[]>([])
  const [focusIdx, setFocusIdx] = useState(0)
  const logEndRef = useRef<HTMLDivElement>(null)

  const rowsRef = useRef(rows)
  const busyRef = useRef(busyId)
  const focusRef = useRef(focusIdx)
  useEffect(() => { rowsRef.current = rows }, [rows])
  useEffect(() => { busyRef.current = busyId }, [busyId])
  useEffect(() => { focusRef.current = focusIdx }, [focusIdx])

  useSubPageGamepad(onBack, onClose)

  const load = useCallback(async () => {
    try {
      setRows(await api.catalog.list())
      setError('')
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => { void load() }, [load])

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
    setBusyId(row.id)
    setLog([])
    setError('')
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
    const count = () => rowsRef.current?.length ?? 0
    const offs = [
      onGp('gp:dpad-up', () => setFocusIdx(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocusIdx(i => Math.min(count() - 1, i + 1))),
      onGp('gp:confirm', () => {
        const row = rowsRef.current?.[focusRef.current]
        if (row) void actRef.current(row)
      }),
    ]
    return () => offs.forEach(o => o())
  }, [])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="EMULATORS & APPS" onBack={onBack} />

      {error && <div style={{ color: '#ff6b6b', padding: '0 1.5rem 0.5rem' }}>{error}</div>}
      {rows === null && !error && (
        <div style={{ padding: '0 1.5rem', opacity: 0.6 }}>Loading the catalogue…</div>
      )}

      <div style={{ overflowY: 'auto', padding: '0 1.5rem' }}>
        {(rows ?? []).map((row, i) => {
          const running = busyId === row.id
          return (
            <div
              key={row.id}
              onClick={() => void act(row)}
              style={{
                display: 'flex', alignItems: 'center', gap: '1rem',
                padding: '0.75rem 1rem', marginBottom: '0.5rem', borderRadius: 10,
                cursor: busyId ? 'default' : 'pointer',
                opacity: busyId && !running ? 0.4 : 1,
                background: i === focusIdx ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.04)',
                borderLeft: `4px solid ${row.color}`,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>
                  {row.label}
                  {row.origin === 'local' && (
                    <span style={{ marginLeft: 8, fontSize: '0.7rem', opacity: 0.6 }}>local</span>
                  )}
                </div>
                <div style={{ fontSize: '0.8rem', opacity: 0.6 }}>
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
              <div style={{ fontSize: '0.85rem', opacity: 0.9, whiteSpace: 'nowrap' }}>
                {running ? '…' : row.installed ? 'Remove' : 'Install'}
              </div>
            </div>
          )
        })}
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
