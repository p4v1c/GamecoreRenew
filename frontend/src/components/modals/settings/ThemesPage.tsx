import { useEffect, useState } from 'react'
import { Overlay, BackHeader } from '../../ui'
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

  /**
   * What you are using, first; everything else after. Default is one of the
   * rows, not a separate concept — switching back to it is the same gesture as
   * switching to anything else.
   *
   * Ordered once per load rather than on every change: a list that reshuffles
   * under the cursor is unusable with a d-pad.
   */
  const [order, setOrder] = useState<(string | null)[]>([null])
  useEffect(() => {
    const ids: (string | null)[] = [null, ...items.map(t => t.id)]
    setOrder([...ids].sort((a, b) => (a === active ? -1 : b === active ? 1 : 0)))
    setFocus(0)   // the active theme, now that it leads
  }, [items, active])   // eslint-disable-line react-hooks/exhaustive-deps

  const rows = order.length

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
    const id = order[idx]
    const target = id === null ? null : items.find(t => t.id === id) ?? null
    if (id !== null && !target?.compatible) return
    // Re-applying what is already on screen would tear the frontend down and
    // rebuild it identically — a long blink that looks like a crash.
    if ((target?.id ?? null) === active) { playSound('move'); return }
    setBusy(true); setError('')
    try {
      await theme.select(id)
      setActive(id)
      playSound('confirm')
    } catch {
      setError('Could not apply that theme')
    } finally {
      setBusy(false)
    }
  }

  const row = (i: number, title: string, sub: string, disabled = false) => {
    const focused = focus === i
    const current = order[i] === active
    return (
      <div key={i} onClick={() => apply(i)} style={{
        display: 'flex', alignItems: 'center', gap: 14, padding: '12px 14px',
        borderRadius: 12, marginBottom: 8, cursor: disabled ? 'default' : 'pointer',
        background: focused ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 18%, transparent)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${focused ? 'color-mix(in srgb, var(--gc-accent, #7c3aed) 55%, transparent)' : 'rgba(255,255,255,0.07)'}`,
        opacity: disabled ? 0.45 : 1, transition: 'all 0.15s',
      }}>
        {/* A filled dot for the theme in use, a hollow ring for the rest: the
            marker is a shape before it is a colour, so it survives a TV. */}
        <span style={{
          width: 16, height: 16, borderRadius: 8, flexShrink: 0,
          background: current ? 'var(--gc-accent, #7c3aed)' : 'transparent',
          border: `2px solid ${current ? 'var(--gc-accent, #7c3aed)' : 'rgba(255,255,255,0.25)'}`,
          boxShadow: current ? '0 0 0 3px color-mix(in srgb, var(--gc-accent, #7c3aed) 25%, transparent)' : 'none',
        }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>{title}</div>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>{sub}</div>
        </div>
        {current && (
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: 1, padding: '3px 9px',
            borderRadius: 999, color: 'var(--gc-accent-bright, #c4b5fd)',
            background: 'color-mix(in srgb, var(--gc-accent, #7c3aed) 22%, transparent)',
            border: '1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 45%, transparent)',
          }}>IN USE</span>
        )}
      </div>
    )
  }

  return (
    <Overlay onClose={onClose}>
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

      {order.map((id, i) => {
        if (id === null) return row(i, 'Default', 'The built-in GameCore look')
        const t = items.find(x => x.id === id)
        if (!t) return null
        return row(
          i,
          t.name,
          t.compatible
            ? `v${t.version}${t.author ? ` · ${t.author}` : ''}${t.description ? ` · ${t.description}` : ''}`
            // The backend knows why — an old SDK, or a theme that does not dress
            // every surface. Saying "needs a newer build" for the second would
            // send the author looking in the wrong place.
            : t.warnings.join(' · ') || `needs SDK v${t.api} — this build is older`,
          !t.compatible,
        )
      })}

      {!items.length && (
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', padding: '10px 2px' }}>
          No theme installed. Drop a folder in <code>config/themes/</code> and it shows up here.
        </div>
      )}

      {error && <div style={{ fontSize: 12, color: '#fca5a5', marginTop: 10 }}>{error}</div>}

      <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1, marginTop: 16 }}>
        Hold L1 + R1 for 2s anywhere to force the default theme
      </div>
    </Overlay>
  )
}
