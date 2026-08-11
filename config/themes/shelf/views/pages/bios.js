/**
 * Settings → BIOS & system files.
 *
 * The one category the capture describes exactly as it already exists: two
 * columns of cards, each a system, its verdict, the directory to copy into,
 * and one row per file with its state and the sentence explaining what that
 * file is for. `GET /bios` answers with all of it.
 *
 * Read-only, and that is the design rather than a shortfall. Nothing is
 * downloaded here and nothing can be: these are files the owner must supply,
 * for reasons this project does not get to route around. So the screen's whole
 * job is to say what is missing and exactly where to put it — which is why the
 * absolute path is on screen rather than behind a tooltip.
 *
 * A system the owner has not installed is dimmed, never hidden. It is how
 * somebody learns, before adding PCSX2, that a file will be needed; hiding the
 * row would make the screen answer "what is broken right now" instead of the
 * question people arrive with, which is "what does this box still need".
 */
const STATE = {
  ok: 'PRESENT',
  absent: 'MISSING',
  mismatch: 'WRONG FILE',
}

export const createBiosPage = (sdk) => {
  const { html, useState, useEffect, useRef, React } = sdk.ui
  const Fragment = React.Fragment

  return ({ active, onLeave }) => {
    const [rows, setRows] = useState([])
    const [idx, setIdx] = useState(0)
    const [failed, setFailed] = useState(false)

    useEffect(() => {
      sdk.api.bios.list().then(setRows).catch(() => setFailed(true))
    }, [])

    const ref = useRef({ idx, len: rows.length })
    useEffect(() => { ref.current = { idx, len: rows.length } }, [idx, rows.length])

    // Nothing here is actionable, so ✕ has nothing to do and the cursor exists
    // only to scroll a card into view. ← and ○ leave, which is the whole
    // contract this page needs.
    useEffect(() => {
      if (!active) return
      const len = () => Math.max(1, ref.current.len)
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setIdx((i) => (i - 1 + len()) % len())
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setIdx((i) => (i + 1) % len())
        }),
        sdk.input.onGp('gp:dpad-left', onLeave),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave])

    const ready = rows.filter((r) => r.status === 'ok').length

    return html`
      <${Fragment}>
      <section class="cz-set-main" data-zone=${active ? 'on' : 'off'}>
        <div class="cz-set-h-row">
          <div class="cz-set-h">BIOS & system files</div>
          ${rows.length ? html`<div class="cz-wifi-state">${ready}/${rows.length} READY</div>` : null}
        </div>
        <p class="cz-set-sub">
          Copy files over SSH or from Desktop Mode; nothing is downloaded here.
          The path under each system is where its files go.
        </p>

        ${failed ? html`<div class="cz-wifi-msg">Could not read the BIOS report.</div>` : null}

        <div class="cz-bios-grid">
          ${rows.map((b, i) => html`
            <div key=${b.id} class="cz-bios" data-on=${active && idx === i ? '1' : '0'}
                 data-off=${b.installed ? '0' : '1'}
                 onClick=${() => setIdx(i)}>
              <div class="cz-bios-head">
                <span class="cz-bios-dot" data-ok=${b.status === 'ok' ? '1' : '0'}></span>
                <span class="cz-bios-name">${b.label}</span>
                <span class="cz-bios-state" data-ok=${b.status === 'ok' ? '1' : '0'}>
                  ${b.installed ? (b.status === 'ok' ? 'READY' : STATE[b.status] || 'INCOMPLETE')
                                : 'NOT INSTALLED'}
                </span>
              </div>
              <div class="cz-bios-path">${b.dir}</div>
              <div class="cz-bios-files">
                ${b.files.map((f) => html`
                  <div key=${f.path} class="cz-bios-file">
                    <div class="cz-bios-file-l">
                      <span class="cz-bios-fname">${f.any_file ? 'any image in this directory' : f.file}</span>
                      <span class="cz-bios-fstate" data-ok=${f.status === 'ok' ? '1' : '0'}>
                        ${STATE[f.status] || f.status}${
                          // "present" and "present and its hash matches" are
                          // different assurances, and the screen that exists to
                          // diagnose a black window should not blur them.
                          f.status === 'ok' && f.verified ? ' · MD5 CHECKED' : ''}
                      </span>
                    </div>
                    ${f.note ? html`<div class="cz-bios-note">${f.note}</div>` : null}
                  </div>`)}
              </div>
            </div>`)}
        </div>
      </section>
      <//>`
  }
}
