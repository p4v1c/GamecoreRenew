/**
 * Summer — a beach at the hour it actually is.
 *
 * Ported from the "GameCore Summer" design mockup. The mockup was one 700-line
 * vanilla component that owned everything, including its own gamepad polling
 * and fake data; here the ocean renderer is kept nearly verbatim (ocean.js) and
 * the screens are rebuilt on the theme SDK, so they run on the box's real
 * systems, playtime and controllers, and share the host's single input bus.
 *
 * Surfaces: background · topbar · home · settings.
 * Everything else stays on the default theme — that is what partial override
 * is for.
 *
 * Contract: docs/themes/README.md
 */
import { createOcean, todColors, currentTod } from './ocean.js'

export default (sdk) => {
  const { html, useState, useEffect, useRef, useMemo } = sdk.ui

  // ── Shared: is the machine busy or asleep? ─────────────────────────────────
  // Decor and animation must stop while a game runs or the box is in standby.
  const useIdle = () => {
    const [asleep, setAsleep] = useState(false)
    useEffect(() => {
      const offs = [
        sdk.system.onWsEvent('standby:screensaver', () => setAsleep(true)),
        sdk.system.onWsEvent('standby:sleep', () => setAsleep(true)),
        sdk.system.onWsEvent('standby:exit', () => setAsleep(false)),
      ]
      return () => offs.forEach(off => off())
    }, [])
    const playing = sdk.nav.use(s => !!s.sessionGameKey)
    return asleep || playing
  }

  // ── background: the ocean ─────────────────────────────────────────────────
  const Background = () => {
    const ref = useRef(null)
    const oceanRef = useRef(null)
    const idle = useIdle()

    useEffect(() => {
      if (!ref.current) return
      oceanRef.current = createOcean(ref.current)
      return () => oceanRef.current?.stop()
    }, [])

    useEffect(() => { oceanRef.current?.setPaused(idle) }, [idle])

    return html`<canvas ref=${ref} class="sm-ocean" aria-hidden="true" />`
  }

  // ── topbar ────────────────────────────────────────────────────────────────
  const TopBar = ({ onSettings, onPower }) => {
    const [info, setInfo] = useState(null)
    const [clock, setClock] = useState('')
    const [tod, setTod] = useState(() => currentTod().tod)

    useEffect(() => {
      const load = () => sdk.api.sysinfo().then(setInfo).catch(() => {})
      load()
      const t = setInterval(load, 60000)
      // Same push the default bar uses — no polling for controller state.
      const offs = [
        sdk.system.onWsEvent('gp:connected', load),
        sdk.system.onWsEvent('gp:disconnected', load),
        sdk.system.onWsEvent('gp:controllers', (d) => {
          if (d?.controllers) setInfo(p => (p ? { ...p, controllers: d.controllers } : p))
        }),
      ]
      return () => { clearInterval(t); offs.forEach(off => off()) }
    }, [])

    useEffect(() => {
      const tick = () => {
        const d = new Date()
        setClock(`${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`)
        setTod(currentTod().tod)
      }
      tick()
      const t = setInterval(tick, 10000)
      return () => clearInterval(t)
    }, [])

    const pads = (info?.controllers || []).slice(0, 4)
    return html`
      <div class="sm-topbar">
        <div class="sm-brand"><span class="sm-diamond" /> GAMECORE</div>
        <div class="sm-top-right">
          ${pads.map((p, i) => html`
            <div key=${i} class="sm-chip sm-pad">
              <span class="sm-pad-n">P${p.player ?? i + 1}</span>
              <span class="sm-bat" data-low=${p.level < 15 ? '1' : p.level < 30 ? 'w' : '0'}>
                <i style=${{ width: `${Math.max(4, p.level)}%` }} />
              </span>
              ${p.charging ? html`<span class="sm-bolt">⚡</span>` : null}
            </div>`)}
          ${info?.ip ? html`<div class="sm-chip sm-ip">${info.ip}</div>` : null}
          <div class="sm-clock"><span class="sm-glyph">${TOD_GLYPH(tod)}</span>${clock}</div>
          <button class="sm-icon" onClick=${onSettings} title="Settings">⚙</button>
          <button class="sm-icon sm-icon-power" onClick=${onPower} title="Power">⏻</button>
        </div>
      </div>`
  }

  const TOD_GLYPH = (t) => (t === 'night' || t === 'sunset' ? '☾' : '☀')

  // ── home ──────────────────────────────────────────────────────────────────
  const PER_PAGE = 8

  const Home = () => {
    const [systems, setSystems] = useState([])
    const [playtime, setPlaytime] = useState({})
    const [counts, setCounts] = useState({})
    const [focus, setFocus] = useState(0)
    const [page, setPage] = useState(0)
    const modalDepth = sdk.nav.use(s => s.modalDepth)
    const screen = sdk.nav.use(s => s.screen)

    useEffect(() => {
      sdk.api.systems.list().then(list => {
        setSystems(list)
        list.forEach(s => {
          if (s.kind === 'app') return
          sdk.api.games.list(s.id)
            .then(g => setCounts(c => ({ ...c, [s.id]: g.length })))
            .catch(() => {})
        })
      }).catch(() => {})
      sdk.api.playtime.all().then(rows => {
        const m = {}
        for (const r of rows) m[r.system_id] = (m[r.system_id] || 0) + (r.total_secs || 0)
        setPlaytime(m)
      }).catch(() => {})
    }, [])

    const pages = Math.max(1, Math.ceil(systems.length / PER_PAGE))
    const shown = systems.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE)

    // Navigation. Blocked while a modal is open or we are not on this screen —
    // the same guard the default screens use.
    useEffect(() => {
      const blocked = () => screen !== 'home' || modalDepth > 0
      const move = (d) => {
        if (blocked()) return
        sdk.system.playSound('move')
        setFocus(f => Math.max(0, Math.min(shown.length - 1, f + d)))
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => move(-1)),
        sdk.input.onGp('gp:dpad-right', () => move(1)),
        sdk.input.onGp('gp:dpad-up', () => move(-4)),
        sdk.input.onGp('gp:dpad-down', () => move(4)),
        sdk.input.onGp('gp:l1', () => { if (!blocked()) { setPage(p => Math.max(0, p - 1)); setFocus(0) } }),
        sdk.input.onGp('gp:r1', () => { if (!blocked()) { setPage(p => Math.min(pages - 1, p + 1)); setFocus(0) } }),
        sdk.input.onGp('gp:confirm', () => {
          if (blocked()) return
          const sy = shown[focus]
          if (!sy) return
          sdk.system.playSound('confirm')
          if (sy.kind === 'app' || sy.type === 'application') sdk.api.games.launch(sy.id).catch(() => {})
          else sdk.nav.goLibrary(sy.id)
        }),
      ]
      return () => offs.forEach(off => off())
    }, [shown, focus, pages, screen, modalDepth])

    const fmt = (secs) => {
      if (!secs) return '0m'
      const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60)
      return h ? `${h}h ${m}m` : `${m}m`
    }
    const totalGames = useMemo(
      () => Object.values(counts).reduce((a, b) => a + b, 0), [counts])
    const totalPlay = useMemo(
      () => Object.values(playtime).reduce((a, b) => a + b, 0), [playtime])

    return html`
      <div class="sm-home">
        <div class="sm-stats">
          <div><b>${systems.length}</b><span>SYSTEMS</span></div>
          <div><b>${totalGames}</b><span>GAMES</span></div>
          <div><b>${fmt(totalPlay)}</b><span>PLAYED</span></div>
        </div>

        <div class="sm-grid">
          ${shown.map((sy, i) => html`
            <div key=${sy.id} class="sm-tile" data-on=${focus === i ? '1' : '0'}
                 style=${{ '--tile-accent': sy.color || '#1D7E93' }}>
              <div class="sm-tile-head">
                <span class="sm-sq">${(sy.platform || sy.label || '??').slice(0, 2).toUpperCase()}</span>
                <span class="sm-badge">${sy.platform || ''}</span>
              </div>
              <div class="sm-tile-name">${sy.label}</div>
              <div class="sm-tile-meta">
                ${counts[sy.id] ?? 0} games · ${fmt(playtime[sy.id])}
              </div>
              <i class="sm-tile-rule" />
            </div>`)}
        </div>

        <div class="sm-dots">
          ${Array.from({ length: pages }, (_, i) => html`
            <span key=${i} class="sm-dot" data-on=${i === page ? '1' : '0'} />`)}
        </div>

        <div class="sm-hint">↑↓←→ Navigate · L1/R1 Page · ✕ Open · □ Controller</div>
      </div>`
  }

  // ── settings ──────────────────────────────────────────────────────────────
  // Not in the design brief — the mockup predates the surface. Built here in
  // the same glass-on-ocean language so it does not look bolted on.
  const MENU = [
    { id: 'wifi', icon: '📶', label: 'Wi-Fi', sub: 'Networks' },
    { id: 'audio', icon: '🔊', label: 'Audio', sub: 'Volume & output' },
    { id: 'bluetooth', icon: '◉', label: 'Bluetooth', sub: 'Devices & pairing' },
    { id: 'standby', icon: '🌙', label: 'Standby', sub: 'Screensaver & low power' },
    { id: 'themes', icon: '🎨', label: 'Themes', sub: 'Change the look' },
    { id: 'update', icon: '↑', label: 'Update', sub: 'Check for updates' },
    { id: 'desktop', icon: '⎋', label: 'Desktop', sub: 'Return to system', danger: true },
  ]

  const Settings = ({ onClose }) => {
    const [page, setPage] = useState(null)
    const [focus, setFocus] = useState(0)
    const Pages = sdk.defaults.DefaultSettingsPages

    useEffect(() => {
      if (page) return   // the sub-page brings its own bindings
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setFocus(f => (f - 1 + MENU.length) % MENU.length)
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setFocus(f => (f + 1) % MENU.length)
        }),
        sdk.input.onGp('gp:confirm', () => {
          sdk.system.playSound('confirm'); setFocus(f => { setPage(MENU[f].id); return f })
        }),
        sdk.input.onGp('gp:back', onClose),
      ]
      return () => offs.forEach(off => off())
    }, [page, onClose])

    // The real pages do the real work — nobody should reimplement Wi-Fi
    // scanning to restyle a menu.
    if (page) {
      const P = Pages[page]
      return html`
        <div class="sm-modal-wrap">
          <div class="sm-panel sm-panel-wide">
            <${P} onClose=${onClose} onBack=${() => setPage(null)} />
          </div>
        </div>`
    }

    return html`
      <div class="sm-modal-wrap" onClick=${(e) => e.target === e.currentTarget && onClose()}>
        <div class="sm-panel">
          <div class="sm-panel-title">SETTINGS</div>
          ${MENU.map((it, i) => html`
            <div key=${it.id} class="sm-row" data-on=${focus === i ? '1' : '0'}
                 data-danger=${it.danger ? '1' : '0'} onClick=${() => setPage(it.id)}>
              <span class="sm-row-icon">${it.icon}</span>
              <span class="sm-row-text"><b>${it.label}</b><i>${it.sub}</i></span>
              <span class="sm-row-chevron">›</span>
            </div>`)}
          <div class="sm-hint sm-hint-modal">↑↓ Navigate · ✕ Select · ○ Close</div>
        </div>
      </div>`
  }

  return { background: Background, topbar: TopBar, home: Home, settings: Settings }
}
