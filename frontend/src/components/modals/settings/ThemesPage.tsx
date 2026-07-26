import { useEffect, useState } from 'react'
import { BackHeader } from '../../ui'
import { useSubPageGamepad } from './useSubPageGamepad'
import { onGp } from '../../../hooks/useGamepad'
import { playSound } from '../../../lib/sounds'
import { useThemeCtx } from '../../ThemeSurface'
import { fetchThemeIndex, type ThemeManifest } from '../../../lib/themeLoader'

/** Settings → Themes: list what is installed, apply one, get back to default. */
export function ThemesPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const theme = useThemeCtx()
  const [items, setItems] = useState<ThemeManifest[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [focus, setFocus] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useSubPageGamepad(onBack, onClose, !busy)

  const refresh = () => {
    fetchThemeIndex()
      .then(i => { setItems(i.themes); setActive(i.active) })
      .catch(() => setError('Could not read the theme list'))
  }
  useEffect(refresh, [])

  // Row 0 is always "Default", then one row per installed theme.
  const rows = 1 + items.length

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => { playSound('move'); setFocus(f => (f - 1 + rows) % rows) }),
      onGp('gp:dpad-down', () => { playSound('move'); setFocus(f => (f + 1) % rows) }),
      onGp('gp:confirm', () => {
        setFocus(f => { apply(f); return f })
      }),
    ]
    return () => offs.forEach(o => o())
  }, [rows, items])   // eslint-disable-line react-hooks/exhaustive-deps

  const apply = async (idx: number) => {
    if (busy || !theme) return
    const target = idx === 0 ? null : items[idx - 1]
    if (target && !target.compatible) return
    setBusy(true); setError('')
    try {
      await theme.select(target ? target.id : null)
      setActive(target ? target.id : null)
      playSound('confirm')
    } catch {
      setError('Could not apply that theme')
    } finally {
      setBusy(false)
    }
  }

  const row = (i: number, title: string, sub: string, disabled = false) => {
    const focused = focus === i
    const current = (i === 0 && !active) || (i > 0 && items[i - 1]?.id === active)
    return (
      <div key={i} onClick={() => apply(i)} style={{
        display: 'flex', alignItems: 'center', gap: 14, padding: '12px 14px',
        borderRadius: 12, marginBottom: 8, cursor: disabled ? 'default' : 'pointer',
        background: focused ? 'rgba(124,58,237,0.18)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${focused ? 'rgba(124,58,237,0.55)' : 'rgba(255,255,255,0.07)'}`,
        opacity: disabled ? 0.45 : 1, transition: 'all 0.15s',
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>{title}</div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>{sub}</div>
        </div>
        {current && <span style={{ fontSize: 11, fontWeight: 700, color: '#a78bfa' }}>ACTIVE</span>}
      </div>
    )
  }

  return (
    <>
      <BackHeader label="THEMES" onBack={onBack} />

      {/* Why the user landed back on the default look, if they did. */}
      {theme?.safeMode?.active && (
        <div style={{
          padding: '10px 12px', borderRadius: 10, marginBottom: 14,
          background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)',
          fontSize: 12, color: '#fca5a5',
        }}>
          <b>{theme.safeMode.themeId}</b> was disabled — {theme.safeMode.reason}.
          Pick it again to retry.
        </div>
      )}

      {row(0, 'Default', 'The built-in GameCore look')}

      {items.map((t, i) => row(
        i + 1,
        t.name,
        t.compatible
          ? `v${t.version}${t.author ? ` · ${t.author}` : ''}${t.description ? ` · ${t.description}` : ''}`
          : `needs SDK v${t.api} — this build is older`,
        !t.compatible,
      ))}

      {!items.length && (
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', padding: '10px 2px' }}>
          No theme installed. Drop a folder in <code>config/themes/</code> and it shows up here.
        </div>
      )}

      {error && <div style={{ fontSize: 12, color: '#fca5a5', marginTop: 10 }}>{error}</div>}

      <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1, marginTop: 16 }}>
        Hold L1 + R1 for 2s anywhere to force the default theme
      </div>
    </>
  )
}
