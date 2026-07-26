/**
 * Summer — a beach at the hour it actually is.
 *
 * Ported from the "GameCore Summer" design mockup. The mockup was one 700-line
 * vanilla component that owned everything, including its own gamepad polling
 * and fake data; here the ocean renderer is kept nearly verbatim (ocean.js) and
 * the screens are rebuilt on the theme SDK, so they run on the box's real
 * systems, playtime and controllers, and share the host's single input bus.
 *
 * It returns a `shell`: the whole frontend body. The pieces it does not
 * rewrite (library, screensaver, power and controller screens) come from
 * sdk.defaults.Shell, which takes them as overrides — so this file changes four
 * screens without reimplementing a launcher, and the default screens keep the
 * container and stacking they were written for.
 *
 * Contract: docs/themes/README.md
 */
import { createOcean, todColors, currentTod, shade } from './ocean.js'

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

    // No z-index here on purpose: the shell puts this behind everything.
    return html`<canvas ref=${ref} class="sm-ocean" aria-hidden="true" />`
  }

  // ── decor: the dune foreground ─────────────────────────────────────────────
  // Grass blades are generated exactly as the mockup did — a seeded PRNG so the
  // dune is identical on every boot — and swayed in CSS. Shells are the mockup's
  // seven hand-placed positions. No surfer: the brief's narrative element was
  // dropped on request.
  const makeBlades = (seed, count, spread) => {
    let s = seed
    const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647 }
    const out = []
    for (let i = 0; i < count; i++) {
      const back = i % 3 === 0
      const u = i / count
      const x = -40 + Math.pow(u, 1.8) * spread + rnd() * 22
      const near = 1.35 - 0.65 * u
      const h = ((back ? 80 : 130) + rnd() * (back ? 80 : 160)) * near
      const lean = (rnd() - 0.5) * (h * 0.42)
      const w = ((back ? 4 : 5.5) + rnd() * 4) * near
      const cx = x + lean * 0.28, cy = 300 - h * 0.52
      const d = `M${(x - w).toFixed(1)} 300 Q${(cx - w * 0.35).toFixed(1)} ${cy.toFixed(1)} `
              + `${(x + lean).toFixed(1)} ${(300 - h).toFixed(1)} `
              + `Q${(cx + w * 0.4).toFixed(1)} ${(cy + 4).toFixed(1)} ${(x + w).toFixed(1)} 300 Z`
      out.push({
        d, depth: back ? 0.5 + rnd() * 0.16 : 0.78 + rnd() * 0.42,
        kf: `smB${h > 230 ? 3 : h > 150 ? 2 : 1}`,
        dur: (1.7 + rnd() * 1.5).toFixed(2),
        delay: (-(x / spread) * 1.6 - rnd() * 0.5).toFixed(2),
      })
    }
    return out.sort((a, b) => a.depth - b.depth)
  }

  // left, top, size, rotation — the mockup's placement, kept
  const SHELLS = [
    [13, 86, 34, -14], [27, 81, 24, 9], [41, 94, 40, -6], [52, 84, 26, 22],
    [63, 90, 32, -19], [76, 82, 22, 6], [88, 92, 36, 15],
  ]

  const Decor = () => {
    const idle = useIdle()
    // The dune belongs to the beach view. Over the library it just sits on top
    // of the cover art, so it stays on the dashboard.
    const screen = sdk.nav.use(s => s.screen)
    const left = useMemo(() => makeBlades(12345, 38, 760), [])
    const right = useMemo(() => makeBlades(987654, 34, 720), [])
    const [c, setC] = useState(() => todColors())
    useEffect(() => {
      const t = setInterval(() => setC(todColors()), 60000)
      return () => clearInterval(t)
    }, [])
    if (idle || screen !== 'home') return null

    const blade = (b, i, tint) => html`
      <path key=${i} d=${b.d} fill=${shade(c.grass, b.depth * tint)}
        style=${{
          transformBox: 'fill-box', transformOrigin: '50% 100%',
          animation: `${b.kf} ${b.dur}s cubic-bezier(.36,.07,.19,.97) ${b.delay}s infinite`,
        }} />`

    return html`
      <div class="sm-decor">
        ${SHELLS.map((v, i) => html`
          <svg key=${i} class="sm-shell" viewBox="0 0 40 32"
               style=${{ left: `${v[0]}%`, top: `${v[1]}%`, width: `${v[2]}px`,
                         transform: `rotate(${v[3]}deg)` }}>
            <path d="M20 31 C6 31 1 21 2 13 C3 6 10 1 20 1 C30 1 37 6 38 13 C39 21 34 31 20 31 Z"
                  fill=${shade(c.sandNear, 1.08)} stroke=${shade(c.sandWet, 0.88)} stroke-width="1.2" />
            <path d="M20 31 L20 2 M20 31 L9 6 M20 31 L31 6 M20 31 L4 14 M20 31 L36 14"
                  stroke=${shade(c.sandWet, 0.92)} stroke-width="1" fill="none" opacity="0.75" />
          </svg>`)}
        <svg class="sm-grass sm-grass-l" viewBox="0 0 760 300" preserveAspectRatio="none">
          ${left.map((b, i) => blade(b, i, 1))}
        </svg>
        <svg class="sm-grass sm-grass-r" viewBox="0 0 720 300" preserveAspectRatio="none">
          ${right.map((b, i) => blade(b, i, 0.96))}
        </svg>
      </div>`
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
          ${info?.storage_total_gb ? html`
            <div class="sm-chip sm-storage" title="Storage">
              <span class="sm-store-bar">
                <i style=${{
                  width: `${Math.min(100, Math.round(info.storage_used_gb / info.storage_total_gb * 100))}%`,
                  background: info.storage_used_gb / info.storage_total_gb > 0.85
                    ? 'var(--state-alert)'
                    : info.storage_used_gb / info.storage_total_gb > 0.65
                      ? 'var(--state-warn)' : 'var(--sea-brand)',
                }} />
              </span>
              <span class="sm-store-txt">${Math.round(info.storage_free_gb)}G free</span>
            </div>` : null}
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
                 data-empty=${(counts[sy.id] ?? 0) === 0 ? '1' : '0'}
                 style=${{ '--tile-accent': sy.color || '#1D7E93' }}>
              <div class="sm-tile-head">
                <span class="sm-sq">${(sy.platform || sy.label || '??').slice(0, 2).toUpperCase()}</span>
                <span class="sm-badge">${sy.platform || ''}</span>
              </div>
              <div class="sm-tile-name">${sy.label}</div>
              <div class="sm-tile-meta">
                ${(counts[sy.id] ?? 0) === 0
                  ? 'No games'
                  : `${counts[sy.id]} games · ${fmt(playtime[sy.id])}`}
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
    // The sub-pages are fragments written for the default Overlay — width,
    // padding and scrolling all come from it. Dropping them into our own box is
    // what broke the Wi-Fi page.
    if (page) {
      const P = Pages[page]
      return html`
        <${sdk.defaults.SettingsOverlay} onClose=${onClose} width=${560}>
          <${P} onClose=${onClose} onBack=${() => setPage(null)} />
        <//>`
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

  // ── the shell ─────────────────────────────────────────────────────────────
  // Everything not listed here stays default, inside the default shell — which
  // owns the stacking and the modal stack, so nothing of ours can paint over a
  // screen we did not replace.
  const ShellC = () => html`
    <${sdk.defaults.Shell}
      background=${Background}
      decor=${Decor}
      topbar=${TopBar}
      home=${Home}
      settings=${Settings} />`

  return { shell: ShellC }
}
