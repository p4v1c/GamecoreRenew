/**
 * Settings → BIOS & system files.
 *
 * A list and one detail. The list has one row per console installed on this
 * box, all the same height: its name and one short verdict, the ones needing
 * a file first. The detail is the row under the cursor only: where to copy,
 * then each file with its state and the one sentence about it. Showing every
 * path and every note at once was the wall of text people got lost in.
 *
 * Consoles that are not installed are left out: a file for an emulator the
 * box does not have is not something this box needs. `GET /bios` still says
 * `installed` for every system; this page only keeps the true ones.
 *
 * Read-only by design. Nothing is downloaded here and nothing can be: these
 * are files the owner supplies, so the page's job is to say what is missing
 * and exactly where it goes, which is why the absolute path is on screen.
 */
import { asList, follow } from './list.js'

const needsFile = (b) => b.status !== 'ok'

/** Installed systems only, the ones needing a file first, then by name. */
export const biosRows = (rows) => asList(rows)
  .filter((b) => b.installed)
  .sort((a, b) => Number(needsFile(b)) - Number(needsFile(a)) || String(a.label).localeCompare(String(b.label)))

/** A system's verdict in two or three words. Optional files never change it. */
export const systemVerdict = (b) => {
  if (b.status === 'ok') return 'Ready'
  if (b.status === 'mismatch') return 'Wrong file'
  const missing = asList(b.files).filter((f) => f.required && f.status !== 'ok').length
  return missing > 1 ? `${missing} files missing` : 'File missing'
}

/** One file's state: `tone` is ok, bad, or quiet for an optional absent file. */
export const fileVerdict = (f) => {
  if (f.status === 'ok') return { tone: 'ok', text: f.verified ? 'Present, MD5 checked' : 'Present' }
  if (f.status === 'mismatch') return { tone: 'bad', text: 'Wrong file' }
  return f.required ? { tone: 'bad', text: 'Missing' } : { tone: 'quiet', text: 'Optional' }
}

/** "4/6 ready" for the category rail, counting installed systems only. */
export const biosSummary = (rows) => {
  const shown = biosRows(rows)
  return `${shown.filter((b) => b.status === 'ok').length}/${shown.length} ready`
}

export const createBiosPage = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  function Detail({ b }) {
    return html`<div class="gcs-bios-detail">
      <div class="gcs-bios-dhead">
        <span class="gcs-bios-dname">${b.label}</span>
        <span class="gcs-bios-state" data-ok=${b.status === 'ok' ? '1' : '0'}>${systemVerdict(b)}</span>
      </div>
      <div class="gcs-bios-label">Copy to</div>
      <div class="gcs-bios-path">${b.dir}</div>
      <div class="gcs-bios-files">
        ${asList(b.files).map((f) => {
          const v = fileVerdict(f)
          return html`<div key=${f.path || f.file} class="gcs-bios-file">
            <div class="gcs-bios-file-l">
              <span class="gcs-bios-fname">${f.any_file ? 'Any image in this folder' : f.file}</span>
              <span class="gcs-bios-fstate" data-tone=${v.tone} data-ok=${v.tone === 'ok' ? '1' : '0'}>${v.text}</span>
            </div>
            ${f.note ? html`<div class="gcs-bios-note">${f.note}</div>` : null}
            ${f.status === 'mismatch' && f.expected_md5
              ? html`<div class="gcs-bios-note gcs-bios-md5">Expected MD5 ${f.expected_md5}, found ${f.actual_md5}</div>`
              : null}
          </div>`
        })}
      </div>
    </div>`
  }

  return ({ active, onLeave, onLeft }) => {
    const [rows, setRows] = useState([])
    const [idx, setIdx] = useState(0)
    const [state, setState] = useState('loading')

    useEffect(() => {
      sdk.api.bios.list()
        .then((r) => { setRows(biosRows(r)); setState('ready') })
        .catch(() => setState('failed'))
    }, [])

    const mainRef = useRef(null)
    useEffect(() => {
      if (active) follow(mainRef.current?.querySelector('.gcs-bios[data-on="1"]'), idx === 0)
    }, [idx, active, rows.length])

    const ref = useRef(rows.length)
    useEffect(() => { ref.current = rows.length }, [rows.length])

    // Nothing here is actionable: the cursor only picks which console the
    // detail shows. ← and ○ leave.
    useEffect(() => {
      if (!active) return
      const len = () => Math.max(1, ref.current)
      const offs = [
        sdk.input.onGp('gp:dpad-up', () => {
          sdk.system.playSound('move'); setIdx((i) => (i - 1 + len()) % len())
        }),
        sdk.input.onGp('gp:dpad-down', () => {
          sdk.system.playSound('move'); setIdx((i) => (i + 1) % len())
        }),
        sdk.input.onGp('gp:dpad-left', onLeft || onLeave),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave])

    const ready = rows.filter((r) => r.status === 'ok').length
    const shown = rows[Math.min(idx, rows.length - 1)]

    return html`
      <section class="gcs-set-main" ref=${mainRef} data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">BIOS & system files</div>
          ${rows.length ? html`<div class="gcs-wifi-state">${ready}/${rows.length} READY</div>` : null}
        </div>
        <p class="gcs-set-sub">
          The consoles installed on this box that need a system file. Copy it over SSH or from
          Desktop Mode into the folder shown; nothing is downloaded here.
        </p>

        ${state === 'failed' ? html`<div class="gcs-wifi-msg">Could not read the BIOS report.</div>` : null}
        ${state === 'ready' && !rows.length
          ? html`<div class="gcs-wifi-msg">No console installed on this box needs a BIOS file.</div>` : null}

        ${rows.length ? html`<div class="gcs-bios-split">
          <div class="gcs-bios-list" role="list">
            ${rows.map((b, i) => html`
              <div key=${b.id} role="listitem" class="gcs-bios" data-on=${active && idx === i ? '1' : '0'}
                   data-sel=${idx === i ? '1' : '0'} onClick=${() => setIdx(i)}>
                <span class="gcs-bios-dot" data-ok=${b.status === 'ok' ? '1' : '0'}></span>
                <span class="gcs-bios-name">${b.label}</span>
                <span class="gcs-bios-state" data-ok=${b.status === 'ok' ? '1' : '0'}>${systemVerdict(b)}</span>
              </div>`)}
          </div>
          ${shown ? html`<${Detail} b=${shown} />` : null}
        </div>` : null}
      </section>`
  }
}
