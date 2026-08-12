/**
 * Settings → Display.
 *
 * Resolution and refresh rate, and the confirmation that makes them safe to
 * offer at all.
 *
 * ## Why there is a countdown on this screen and nowhere else
 *
 * A mode the television refuses is a black screen, and this is a box driven
 * from a sofa. So the backend arms a revert when it applies a mode and puts the
 * old one back unless something confirms — see `routers/settings/display.py`.
 * The countdown here is that timer made visible; pressing ✕ is what cancels it.
 *
 * The confirmation is deliberately a PRESS, never an automatic call on render.
 * A screen that confirmed itself would confirm a picture nobody can see, which
 * is the entire failure this exists to prevent. If the mode is unreadable, the
 * player does nothing — and doing nothing is what brings the picture back.
 *
 * ## Where this departs from the capture
 *
 * · **No VSync.** The capture offers it. It is written per emulator by
 *   configgen, into thirteen generated configs, and nothing global governs it —
 *   so one switch here would misstate what it controls and fight the files that
 *   actually do. It is the same refusal as the emulator "Update all" button:
 *   the row is easy, the thing behind it does not exist.
 * · **One output.** Two screens need a layout, not a mode, and choosing between
 *   them blind would move a picture the owner cannot see.
 *
 * The list comes from whichever tool owns the outputs — `kscreen-doctor` on a
 * Wayland session, `xrandr` on X11 — and this file does not know which. It
 * asks for a width, a height and a rate; the router resolves that to whatever
 * handle its tool uses.
 */
export const createDisplayPage = (sdk, Rows) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  const label = (m) => `${m.width} × ${m.height}`
  const rateLabel = (r) => `${Number(r).toFixed(2).replace(/\.00$/, '')} Hz`
  const same = (a, b) => a && b && a.width === b.width && a.height === b.height
    && Math.abs(a.rate - b.rate) < 0.01

  return ({ active, onLeave }) => {
    const [info, setInfo] = useState(null)
    const [failed, setFailed] = useState(false)
    const [msg, setMsg] = useState('')
    const [busy, setBusy] = useState(false)
    // Seconds left before the backend puts the old mode back. Non-null means
    // the screen is asking whether it can be read.
    const [left, setLeft] = useState(null)

    const load = () => sdk.api.display.get()
      .then((d) => { setInfo(d); setFailed(false) })
      .catch(() => setFailed(true))

    useEffect(() => { load() }, [])

    // The countdown is a mirror of the backend's timer, never its source. It
    // runs a second short so it can never claim time the backend has already
    // spent — the picture coming back on its own is the honest end of it.
    const leftRef = useRef(left)
    useEffect(() => { leftRef.current = left }, [left])
    useEffect(() => {
      if (left === null) return
      if (left <= 0) { setLeft(null); setMsg('Reverted — that mode could not be confirmed.'); load(); return }
      const t = setTimeout(() => setLeft((n) => (n === null ? null : n - 1)), 1000)
      return () => clearTimeout(t)
    }, [left])

    const modes = (info && info.modes) || []
    // One entry per resolution, largest first; the rates belong to whichever is
    // chosen, because a flat list of every pair is forty rows on some monitors.
    const sizes = []
    for (const m of modes) {
      const key = `${m.width}x${m.height}`
      let s = sizes.find((x) => x.key === key)
      if (!s) { s = { key, width: m.width, height: m.height, rates: [] }; sizes.push(s) }
      if (!s.rates.some((r) => Math.abs(r - m.rate) < 0.01)) s.rates.push(m.rate)
    }
    sizes.sort((a, b) => b.width * b.height - a.width * a.height)
    for (const s of sizes) s.rates.sort((a, b) => b - a)

    const cur = info && info.current
    const [pick, setPick] = useState(null)
    // The chosen row follows the live mode until the player moves it.
    const chosen = pick || (cur ? { width: cur.width, height: cur.height, rate: cur.rate } : null)
    const sizeIdx = Math.max(0, sizes.findIndex((s) => chosen && s.width === chosen.width && s.height === chosen.height))
    const rates = (sizes[sizeIdx] && sizes[sizeIdx].rates) || []
    const rateIdx = Math.max(0, rates.findIndex((r) => chosen && Math.abs(r - chosen.rate) < 0.01))

    const apply = (next) => {
      if (busy) return
      setBusy(true); setMsg('')
      sdk.api.display.setMode(next.width, next.height, next.rate)
        .then((r) => {
          if (r.changed) setLeft(r.revert_secs)
          else setMsg('That is already the mode on screen.')
          load()
        })
        // The router's own words: "a game is running", "not a mode this output
        // advertises". Both are actionable and neither is a bug.
        .catch((e) => setMsg(String((e && e.message) || 'Could not change the mode.')))
        .finally(() => setBusy(false))
    }

    const keep = () => {
      setLeft(null)
      sdk.api.display.confirm().then(() => { setMsg('Mode kept.'); load() }).catch(() => {})
    }
    const undo = () => {
      setLeft(null)
      sdk.api.display.revert().then(() => { setMsg('Back to the previous mode.'); load() }).catch(() => {})
    }

    // While the countdown is up it owns the buttons: ✕ keeps, ○ goes back now.
    // The rows are not reachable then, which is deliberate — there is exactly
    // one question on screen and it has two answers.
    useEffect(() => {
      if (!active || left === null) return
      const offs = [
        sdk.input.onGp('gp:confirm', keep),
        sdk.input.onGp('gp:back', undo),
      ]
      return () => offs.forEach((off) => off())
    }, [active, left])

    if (left !== null) {
      return html`
        <section class="gcs-set-main" data-zone=${active ? 'on' : 'off'}>
          <div class="gcs-set-h">Can you read this?</div>
          <p class="gcs-set-sub">
            ${chosen ? `${label(chosen)} at ${rateLabel(chosen.rate)}. ` : ''}If you do
            nothing, the previous mode comes back in ${left} second${left === 1 ? '' : 's'}.
          </p>
          <div class="gcs-countdown"><i style=${{ width: `${(left / ((info && info.revert_secs) || 12)) * 100}%` }}></i></div>
          <div class="gcs-row2" data-on="1" onClick=${keep}>
            <span class="gcs-row2-text"><b>Keep this mode</b><i>✕</i></span>
            <span class="gcs-act">Keep</span>
          </div>
          <div class="gcs-row2" data-danger="1" onClick=${undo}>
            <span class="gcs-row2-text"><b>Go back now</b><i>○</i></span>
            <span class="gcs-act" data-danger="1">Revert</span>
          </div>
        </section>`
    }

    const rows = sizes.length ? [
      {
        id: 'res', type: 'value', value: sizeIdx,
        options: sizes.map((s) => label(s)),
        label: 'Resolution',
        desc: info && info.output ? `Output ${info.output}` : '',
      },
      {
        id: 'rate', type: 'value', value: rateIdx,
        options: rates.map(rateLabel),
        label: 'Refresh rate', desc: 'Vertical frequency',
      },
      {
        id: 'apply', type: 'action', label: 'Apply this mode',
        label2: chosen && same(chosen, cur) ? 'Current' : 'Apply',
        busy: busy ? 'Applying…' : '',
        desc: 'The previous mode returns by itself if you cannot confirm the new one',
        confirm: false,
      },
    ] : []

    const onSet = (id, v) => {
      if (id === 'res') {
        const s = sizes[v]
        if (!s) return
        // Keep the rate if the new resolution offers it; otherwise its highest,
        // which is the one a television is most likely to accept.
        const keepRate = chosen && s.rates.find((r) => Math.abs(r - chosen.rate) < 0.01)
        setPick({ width: s.width, height: s.height, rate: keepRate || s.rates[0] })
      } else if (id === 'rate') {
        const s = sizes[sizeIdx]
        if (s && s.rates[v] != null) setPick({ width: s.width, height: s.height, rate: s.rates[v] })
      }
    }

    return html`
      <${Rows} rows=${rows} active=${active} onLeave=${onLeave}
        onSet=${onSet} onAct=${() => chosen && apply(chosen)}
        title="Display"
        state=${cur ? `${cur.width}×${cur.height}` : ''}
        sub=${failed
          ? 'This box cannot reach a display right now.'
          : sizes.length
            ? 'Changing the mode affects the whole front end. Nothing changes while a game is running.'
            : 'No output is reporting any mode.'}
        aside=${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null} />`
  }
}
