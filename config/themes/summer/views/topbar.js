/** The status bar: controllers, storage, address, clock, and the two buttons. */
import { currentTod } from '../lib/ocean.js'

const TOD_GLYPH = (t) => (t === 'night' || t === 'sunset' ? '☾' : '☀')

/**
 * Battery as a 4-segment bar — DESIGN-BRIEF.md §3.5.
 *
 * Segments, not a continuous fill: from a couch you read "three bars left" at a
 * glance, where a bar that is 62% full is just a shape. At one segment or less
 * the filled segments turn alert and the whole pill takes an alert border, so
 * the warning survives a washed-out TV that eats the colour change.
 */
const SEGMENTS = 4
const segsFor = (level) => Math.max(0, Math.min(SEGMENTS, Math.ceil((level || 0) / (100 / SEGMENTS))))

export const createTopBar = (sdk) => {
  const { html, useState, useEffect } = sdk.ui
  return ({ onSettings, onPower }) => {
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

    const all = info?.controllers || []
    const pads = all.slice(0, 4)
    // 5th pad and beyond: never a 5th bar — the row's width is fixed.
    const extra = all.length - pads.length
    const used = info?.storage_total_gb ? info.storage_used_gb / info.storage_total_gb : 0
    return html`
      <div class="sm-topbar">
        <div class="sm-brand"><span class="sm-diamond" /> GAMECORE</div>
        <div class="sm-top-right">
          ${pads.map((p, i) => {
            const n = segsFor(p.level)
            const low = n <= 1
            return html`
              <div key=${i} class="sm-chip sm-pad" data-low=${low ? '1' : '0'}>
                <span class="sm-pad-n">P${p.player ?? i + 1}</span>
                <span class="sm-pad-glyph" aria-hidden="true">
                  <svg viewBox="0 0 24 16" width="20" height="14">
                    <path d="M7 3.2h10a5 5 0 0 1 4.8 6.4l-.9 3A2.6 2.6 0 0 1 16.6 13L15 11H9l-1.6 2a2.6 2.6 0 0 1-4.3-.4l-.9-3A5 5 0 0 1 7 3.2Z"
                          fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
                  </svg>
                </span>
                <span class="sm-bat" title=${`${p.level}%`}>
                  ${Array.from({ length: SEGMENTS }, (_, k) => html`
                    <i key=${k} data-fill=${k < n ? '1' : '0'} />`)}
                </span>
                ${p.charging ? html`<span class="sm-bolt">⚡</span>` : null}
              </div>`
          })}
          ${extra > 0 ? html`<div class="sm-chip sm-pad-more">+${extra}</div>` : null}
          ${info?.storage_total_gb ? html`
            <div class="sm-chip sm-storage" title="Storage">
              <span class="sm-store-bar">
                <i style=${{
                  width: `${Math.min(100, Math.round(used * 100))}%`,
                  background: used > 0.85 ? 'var(--state-alert)'
                            : used > 0.65 ? 'var(--state-warn)' : 'var(--sea-brand)',
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
}
