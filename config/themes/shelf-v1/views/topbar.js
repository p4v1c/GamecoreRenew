/**
 * The status bar, as a shelf label.
 *
 * The reference capture puts one thing up here — the platform you are browsing,
 * set small and letter-spaced like the tab on a record divider. GameCore needs
 * more than that: the clock, the address, the free space and the battery of up
 * to four pads are the reason anyone looks at the top of this screen. So the
 * left-hand tab is kept exactly as the capture has it, and everything else is
 * pushed right and set in the same small monospace, so it reads as filing
 * marks rather than as a dashboard.
 *
 * Controllers arrive by push, not by poll: the backend already broadcasts
 * connect, disconnect and battery, and re-asking every second for four numbers
 * that change once an hour is how a launcher ends up warm to the touch.
 */
const SEGMENTS = 4
const segsFor = (level) => Math.max(0, Math.min(SEGMENTS, Math.ceil((level || 0) / (100 / SEGMENTS))))

export const createTopBar = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return ({ onSettings, onPower }) => {
    const [info, setInfo] = useState(null)
    const [clock, setClock] = useState('')
    const [system, setSystem] = useState(null)

    const screen = sdk.nav.use((s) => s.screen)
    const systemId = sdk.nav.use((s) => s.selectedSystemId)

    useEffect(() => {
      const load = () => sdk.api.sysinfo().then(setInfo).catch(() => {})
      load()
      const t = setInterval(load, 60000)
      const offs = [
        sdk.system.onWsEvent('gp:connected', load),
        sdk.system.onWsEvent('gp:disconnected', load),
        sdk.system.onWsEvent('gp:controllers', (d) => {
          if (d?.controllers) setInfo((p) => (p ? { ...p, controllers: d.controllers } : p))
        }),
      ]
      return () => { clearInterval(t); offs.forEach((off) => off()) }
    }, [])

    useEffect(() => {
      const tick = () => {
        const d = new Date()
        setClock(`${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`)
      }
      tick()
      const t = setInterval(tick, 15000)
      return () => clearInterval(t)
    }, [])

    // The tab names the shelf you are standing at. On the dashboard there is no
    // single shelf, so it names the machine instead.
    useEffect(() => {
      if (!systemId) { setSystem(null); return }
      let live = true
      sdk.api.systems.get(systemId).then((s) => { if (live) setSystem(s) }).catch(() => {})
      return () => { live = false }
    }, [systemId])

    const tab = screen === 'library'
      ? (system?.platform || system?.label || systemId || '').toUpperCase()
      : 'GAMECORE'

    const pads = (info?.controllers || []).slice(0, 4)
    const extra = (info?.controllers || []).length - pads.length
    const used = info?.storage_total_gb ? info.storage_used_gb / info.storage_total_gb : 0

    return html`
      <div class="cz-top">
        <div class="cz-tab">${tab || 'GAMECORE'}</div>

        <div class="cz-top-right">
          ${pads.map((p, i) => {
            const n = segsFor(p.level)
            const low = n <= 1
            return html`
              <span key=${i} class="cz-pad" data-low=${low ? '1' : '0'} title=${`${p.level}%`}>
                <b>P${p.player ?? i + 1}</b>
                <span class="cz-bat">
                  ${Array.from({ length: SEGMENTS }, (_, k) => html`
                    <i key=${k} data-fill=${k < n ? '1' : '0'} />`)}
                </span>
                ${p.charging ? html`<em class="cz-bolt">⚡</em>` : null}
              </span>`
          })}
          ${extra > 0 ? html`<span class="cz-pad cz-pad-more">+${extra}</span>` : null}

          ${info?.storage_total_gb ? html`
            <span class="cz-store" title="Storage">
              <span class="cz-store-bar">
                <i style=${{ width: `${Math.min(100, Math.round(used * 100))}%` }}
                   data-level=${used > 0.85 ? 'alert' : used > 0.65 ? 'warn' : 'ok'} />
              </span>
              ${Math.round(info.storage_free_gb)}G free
            </span>` : null}

          ${info?.ip ? html`<span class="cz-ip">${info.ip}</span>` : null}
          <span class="cz-clock">${clock}</span>

          <button class="cz-tool" onClick=${onSettings} title="Settings" aria-label="Settings">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
                 strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3.2" />
              <path d="M19.2 14.4a1.6 1.6 0 0 0 .32 1.76l.06.06a1.9 1.9 0 1 1-2.7 2.7l-.05-.06a1.6 1.6 0 0 0-1.77-.32 1.6 1.6 0 0 0-.97 1.47V20a1.9 1.9 0 0 1-3.8 0v-.1a1.6 1.6 0 0 0-1.04-1.46 1.6 1.6 0 0 0-1.77.32l-.05.06a1.9 1.9 0 1 1-2.7-2.7l.06-.06a1.6 1.6 0 0 0 .32-1.76 1.6 1.6 0 0 0-1.47-.98H4a1.9 1.9 0 0 1 0-3.8h.1a1.6 1.6 0 0 0 1.46-1.04 1.6 1.6 0 0 0-.32-1.76l-.06-.06a1.9 1.9 0 1 1 2.7-2.7l.05.06a1.6 1.6 0 0 0 1.77.32H10a1.6 1.6 0 0 0 .97-1.47V4a1.9 1.9 0 1 1 3.8 0v.1a1.6 1.6 0 0 0 .97 1.47 1.6 1.6 0 0 0 1.77-.32l.05-.06a1.9 1.9 0 1 1 2.7 2.7l-.06.06a1.6 1.6 0 0 0-.32 1.76V10a1.6 1.6 0 0 0 1.47.97H22a1.9 1.9 0 1 1 0 3.8h-.1a1.6 1.6 0 0 0-1.47.97Z" />
            </svg>
          </button>
          <button class="cz-tool cz-tool-power" onClick=${onPower} title="Power" aria-label="Power">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round">
              <path d="M12 3v9M6.3 6.3a9 9 0 1 0 11.4 0" />
            </svg>
          </button>
        </div>
      </div>`
  }
}
