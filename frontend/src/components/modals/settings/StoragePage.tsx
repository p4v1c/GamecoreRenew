import { useState, useEffect, useRef, useCallback } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { api, type StorageVolume } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

/**
 * Settings → Storage: the external disks, and the way to take one out safely.
 *
 * "I plug my ROM disk in" is one of the first three things anyone expects from
 * a console in a living room, and before this the box did nothing at all with
 * one. Three things this screen has to get right:
 *
 *  · **Eject is the point.** Pulling a disk with unwritten data is how a save
 *    is lost, and "has it finished writing" is not a question anyone can answer
 *    by looking at it. The button flushes and detaches; that is the whole
 *    reason this is a screen rather than a paragraph of documentation asking
 *    players to be careful.
 *
 *  · **The stable path, not the mount point.** udisks names the second mount of
 *    the same disk `ROMS 1`, so a library recorded against the real mount point
 *    scans nothing the day someone replugs it. What is shown here — and what a
 *    romsPath should be written against — is `<DATA>/volumes/<label>`.
 *
 *  · **exFAT and NTFS are not a fault, and not nothing either.** They carry no
 *    POSIX permissions, so ROMs are fine and emulator saves are not. Amber and
 *    a sentence, never red: a disk formatted the way every disk in a shop is
 *    formatted must not read as broken.
 *
 * The list repolls, because a disk arriving generates no event the browser can
 * see and the owner is standing there with a cable in their hand.
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const GOOD = '#4ade80'
const WARN = '#fbbf24'
const DIM = 'rgba(255,255,255,0.3)'

export function StoragePage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [rows, setRows] = useState<StorageVolume[]>([])
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [focus, setFocus] = useState(0)
  const refs = useRef<(HTMLDivElement | null)[]>([])
  const count = useRef(0)
  const rowsRef = useRef<StorageVolume[]>([])
  const focusRef = useRef(0)
  useEffect(() => { count.current = rows.length; rowsRef.current = rows }, [rows])
  useEffect(() => { focusRef.current = focus }, [focus])

  const refresh = useCallback(() => api.storage.list()
    .then(r => { setRows(r.volumes ?? []); setError(false) })
    .catch(() => setError(true)), [])

  useEffect(() => {
    refresh()
    // Polled: a disk being plugged in produces no event this page can hear,
    // and the owner is standing in front of the box with the cable in hand.
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [refresh])

  useSubPageGamepad(onBack, onClose)

  const eject = useCallback((v: StorageVolume) => {
    setBusy(v.device)
    setMessage('')
    api.storage.unmount(v.device)
      .then(() => { setMessage(`${v.label || v.device} can be unplugged.`); refresh() })
      // udisks's own words: "target is busy" is actionable — a game is still
      // reading the disk. A generic failure would leave nothing to act on.
      .catch((e: Error) => setMessage(e.message || 'Could not eject this disk.'))
      .finally(() => setBusy(''))
  }, [refresh])

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => setFocus(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocus(i => Math.min(Math.max(0, count.current - 1), i + 1))),
      onGp('gp:confirm', () => {
        const v = rowsRef.current[focusRef.current]
        if (v?.mounted) eject(v)
      }),
    ]
    return () => offs.forEach(o => o())
  }, [eject])

  useEffect(() => { refs.current[focus]?.scrollIntoView({ block: 'nearest' }) }, [focus])

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="STORAGE" onBack={onBack} />

      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginBottom: 14, lineHeight: 1.5 }}>
        {error
          ? 'Could not read the attached disks.'
          : rows.length === 0
            ? 'No external disk is attached. Plug one in and it is mounted automatically — point a system’s ROM folder at the path shown here and its games appear without restarting.'
            : 'Always eject before unplugging: it flushes anything still being written.'}
      </div>

      {message && (
        <div style={{
          fontSize: 12, color: WARN, marginBottom: 12, padding: '9px 12px',
          borderRadius: 8, background: 'rgba(251,191,36,0.08)',
        }}>{message}</div>
      )}

      {rows.map((v, i) => (
        <div
          key={v.device}
          ref={el => { refs.current[i] = el }}
          style={{
            padding: '14px 18px', borderRadius: 12, marginBottom: 10,
            background: focus === i ? `color-mix(in srgb, ${ACCENT} 15%, transparent)` : 'rgba(255,255,255,0.04)',
            border: focus === i ? `1px solid color-mix(in srgb, ${ACCENT} 40%, transparent)` : '1px solid rgba(255,255,255,0.07)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{
              width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
              background: v.mounted ? GOOD : DIM,
            }} />
            <div style={{ fontSize: 15, fontWeight: 600, color: '#fff', flex: 1 }}>
              {v.label || v.device}
            </div>
            <div style={{ fontSize: 12, color: DIM }}>{v.size} · {v.fstype}</div>
          </div>

          {/* What a romsPath should be written against — never the mount point,
              which udisks renames to "ROMS 1" on the second plug. */}
          {v.mounted && v.stable_path && (
            <div style={{
              fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 6,
              fontFamily: 'monospace', wordBreak: 'break-all',
            }}>
              {v.stable_path}
            </div>
          )}

          {!v.keeps_permissions && (
            <div style={{ fontSize: 11, color: WARN, marginTop: 8, lineHeight: 1.5 }}>
              {v.saves_warning}
            </div>
          )}

          {v.mounted && (
            <button
              onClick={() => eject(v)}
              disabled={busy === v.device}
              style={{
                marginTop: 10, padding: '8px 14px', borderRadius: 9,
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.12)', color: '#fff',
                fontSize: 12, fontWeight: 700, cursor: 'pointer', font: 'inherit',
              }}
            >
              {busy === v.device ? 'Ejecting…' : 'Eject safely'}
            </button>
          )}
        </div>
      ))}

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Navigate · ✕ Eject · ○ Back
      </div>
    </Overlay>
  )
}
