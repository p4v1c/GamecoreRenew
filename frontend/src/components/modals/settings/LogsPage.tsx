import { useEffect, useRef, useState } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { onGp } from '../../../hooks/useGamepad'
import { api, type LogsUsage } from '../../../api'
import { useSubPageGamepad } from './useSubPageGamepad'
import { PadHints } from '../../../lib/padKey'

const megabytes = (b: number) => `${(b / 1048576).toFixed(b < 10485760 ? 1 : 0)} MB`

/** The legacy list's Logs page: size, and a purge that takes two presses. */
export function LogsPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [usage, setUsage] = useState<LogsUsage | null>(null)
  const [armed, setArmed] = useState(false)
  const [msg, setMsg] = useState('')
  const pressRef = useRef<() => void>(() => {})

  useEffect(() => { api.logs.usage().then(setUsage).catch(() => setMsg('Could not read the logs.')) }, [])

  pressRef.current = () => {
    if (!usage || !usage.files) return
    if (!armed) { setArmed(true); return }
    setArmed(false)
    api.logs.purge()
      .then((r) => { setUsage({ files: 0, bytes: 0 }); setMsg(`Logs purged, ${megabytes(r.freed.bytes)} freed.`) })
      .catch(() => setMsg('Could not purge the logs.'))
  }

  useSubPageGamepad(onBack, onClose)
  useEffect(() => onGp('gp:confirm', () => pressRef.current()), [])

  const desc = usage === null ? 'Reading…' : usage.files ? `${usage.files} files, ${megabytes(usage.bytes)}` : 'Empty'
  return (
    <Overlay onClose={onClose}>
      <BackHeader label="Logs" onBack={onBack} />
      <div style={{ padding: '14px 18px', borderRadius: 12, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', marginBottom: 24, color: 'var(--gc-ink-2)', fontSize: 15, lineHeight: 1.7 }}>
        {desc}
      </div>
      <div onClick={() => pressRef.current()} style={{ padding: 16, borderRadius: 14, cursor: 'pointer', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5', fontWeight: 700, textAlign: 'center', fontSize: 16 }}>
        {armed ? 'Press ✕ again to purge logs' : '✕ Purge logs'}
      </div>
      {msg ? <div style={{ marginTop: 12, textAlign: 'center', fontSize: 15, color: 'var(--gc-ink-2)' }}>{msg}</div> : null}
      <div style={{ marginTop: 8, textAlign: 'center', fontSize: 14, color: 'var(--gc-ink-3)' }}>
        <PadHints text="✕ Purge · ○ Back" />
      </div>
    </Overlay>
  )
}
