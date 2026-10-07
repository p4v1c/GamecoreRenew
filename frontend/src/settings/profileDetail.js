/**
 * One profile's page, over the whole screen: who it is on the left (animal,
 * name, what it has played, Switch / Rename / Delete), how it looks on the
 * right (picture, colour, theme), every choice in view instead of behind a
 * dialog.
 *
 * The pad moves in two dimensions: ↑/↓ between the left column's buttons, or
 * between the picture rows, the colours and the themes; ←/→ along a row, and
 * from the first of a row back to the left column. ✕ applies a choice at
 * once; Delete takes two presses; ○ goes back to the list.
 */
import { AVATARS, avatarFace } from './avatars.js'
import { PadHints } from '../lib/padKey.js'

const COLUMNS = 6
const PICTURES = [[null, 'Initial'], ...AVATARS.map(([key, label]) => [key, label])]

export const createProfileDetail = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  /**
   * @param profile  the profile shown; `playing` when it is the active one
   * @param palette  [{color, name}]; looks [{id, name, preview}] (id null: built-in)
   * @param stats    {secs, games} for the profile playing, else null
   * @param onPick   ({avatar} | {color} | {theme}); onSwitch, onRename, onDelete, onBack ()
   */
  return ({ profile, playing, palette, looks, stats, msg, active,
            onPick, onSwitch, onRename, onDelete, onBack }) => {
    const side = [
      ...(playing ? [] : [['switch', `Switch to ${profile.name}`]]),
      ['rename', 'Rename'],
      ...(profile.primary ? [] : [['delete', `Delete ${profile.name}`]]),
    ]
    const [cur, setCur] = useState({ zone: 'pic', i: Math.max(0, PICTURES.findIndex(([k]) => k === (profile.avatar || null))) })
    const [armed, setArmed] = useState(false)
    const ref = useRef({})
    ref.current = { cur, side, armed, palette, looks }
    useEffect(() => { if (cur.zone !== 'side' || side[cur.i]?.[0] !== 'delete') setArmed(false) }, [cur.zone, cur.i])

    const worn = 'theme' in profile ? profile.theme : undefined
    const run = (zone, i) => {
      const c = ref.current
      if (zone === 'side') {
        const verb = c.side[i] && c.side[i][0]
        if (verb === 'switch') onSwitch()
        else if (verb === 'rename') onRename()
        else if (verb === 'delete') { if (c.armed) onDelete(); else setArmed(true) }
      } else if (zone === 'pic') onPick({ avatar: PICTURES[i][0] })
      else if (zone === 'col' && c.palette[i]) onPick({ color: c.palette[i].color })
      else if (zone === 'theme' && c.looks[i]) onPick({ theme: c.looks[i].id })
    }

    useEffect(() => {
      if (!active) return undefined
      const go = (next) => { if (next) { sdk.system.playSound('move'); setCur(next) } }
      const step = (dx, dy) => {
        const { cur: { zone, i }, side: s, palette: pal, looks: lk } = ref.current
        const row = Math.floor(i / COLUMNS)
        const col = i % COLUMNS
        if (zone === 'side') {
          if (dx > 0) return { zone: 'pic', i: 0 }
          const n = i + dy
          return dx === 0 && n >= 0 && n < s.length ? { zone, i: n } : null
        }
        if (dx < 0 && (zone === 'pic' ? col === 0 : i === 0)) return { zone: 'side', i: 0 }
        if (dx !== 0) {
          const len = zone === 'pic' ? PICTURES.length : zone === 'col' ? pal.length : lk.length
          const n = i + dx
          if (zone === 'pic' && Math.floor(n / COLUMNS) !== row) return null
          return n >= 0 && n < len ? { zone, i: n } : null
        }
        if (zone === 'pic') {
          if (dy < 0) return row > 0 ? { zone, i: i - COLUMNS } : null
          return i + COLUMNS < PICTURES.length ? { zone, i: i + COLUMNS }
            : pal.length ? { zone: 'col', i: Math.min(col, pal.length - 1) } : null
        }
        if (zone === 'col') {
          if (dy < 0) return { zone: 'pic', i: COLUMNS + Math.min(i, COLUMNS - 1) }
          return lk.length > 1 ? { zone: 'theme', i: Math.min(i, lk.length - 1) } : null
        }
        return dy < 0 && pal.length ? { zone: 'col', i: Math.min(i, pal.length - 1) } : null
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => go(step(-1, 0))),
        sdk.input.onGp('gp:dpad-right', () => go(step(1, 0))),
        sdk.input.onGp('gp:dpad-up', () => go(step(0, -1))),
        sdk.input.onGp('gp:dpad-down', () => go(step(0, 1))),
        sdk.input.onGp('gp:confirm', () => { sdk.system.playSound('confirm'); run(ref.current.cur.zone, ref.current.cur.i) }),
        sdk.input.onGp('gp:back', () => { sdk.system.playSound('back'); onBack() }),
      ]
      return () => offs.forEach((off) => off())
    }, [active])

    const on = (zone, i) => (cur.zone === zone && cur.i === i ? '1' : '0')
    const click = (zone, i) => { setCur({ zone, i }); run(zone, i) }
    const picName = (PICTURES.find(([k]) => k === (profile.avatar || null)) || PICTURES[0])[1]
    const colName = (palette.find((c) => c.color === profile.color) || {}).name || ''

    return html`
      <div class="gcs-prof" role="dialog" aria-modal="true" aria-label=${profile.name}>
        <div class="gcs-prof-crumb">Settings · Profiles</div>
        <div class="gcs-prof-body">
          <section class="gcs-prof-hero">
            <span class="gcs-prof-face" aria-hidden="true" style=${{ background: profile.color }}>${avatarFace(html, profile)}</span>
            <h1 class="gcs-prof-name">${profile.name}</h1>
            <div class="gcs-prof-tags">
              ${playing ? html`<span class="gcs-pcard-now">Playing now</span>` : null}
              ${worn !== undefined ? html`<span>${(looks.find((t) => t.id === worn) || { name: 'Default' }).name} theme</span>` : null}
            </div>
            ${stats ? html`
              <div class="gcs-prof-stats">
                <div><b>${sdk.format.time(stats.secs)}</b><i>Played</i></div>
                <div><b>${stats.games}</b><i>Games</i></div>
              </div>` : null}
            <div class="gcs-prof-grow"></div>
            <div class="gcs-prof-side">
              ${side.map(([verb, label], i) => html`
                <button key=${verb} type="button" class="gcs-prof-btn" data-on=${on('side', i)}
                        data-danger=${verb === 'delete' ? '1' : '0'} data-primary=${verb === 'switch' ? '1' : '0'}
                        onClick=${() => click('side', i)}>
                  ${verb === 'delete' && armed ? `Press again to delete ${profile.name}` : label}
                </button>`)}
              ${profile.primary ? html`<p class="gcs-prof-note">Keeps the saves made before profiles, so it stays.</p>`
                : html`<p class="gcs-prof-note">Games stay. ${profile.name}’s saves are kept on the console, but no profile opens them again.</p>`}
            </div>
          </section>

          <div class="gcs-prof-looks">
            <section aria-label="Picture">
              <div class="gcs-prof-h"><h2>Picture</h2><span>${picName}</span></div>
              <div class="gcs-prof-pics">
                ${PICTURES.map(([key, label], i) => html`
                  <button key=${key || 'initial'} type="button" class="gcs-prof-pic" aria-label=${label}
                          data-on=${on('pic', i)} data-sel=${(profile.avatar || null) === key ? '1' : '0'}
                          onClick=${() => click('pic', i)}>
                    <span class="gcs-prof-pic-face" style=${{ background: profile.color }}>
                      ${avatarFace(html, { name: profile.name, avatar: key })}
                    </span>
                  </button>`)}
              </div>
            </section>

            <section aria-label="Colour">
              <div class="gcs-prof-h"><h2>Colour</h2><span>${colName}</span></div>
              <div class="gcs-prof-cols">
                ${palette.map((c, i) => html`
                  <button key=${c.color} type="button" class="gcs-prof-col" aria-label=${c.name}
                          data-on=${on('col', i)} data-sel=${c.color === profile.color ? '1' : '0'}
                          style=${{ background: c.color }} onClick=${() => click('col', i)}></button>`)}
              </div>
            </section>

            ${looks.length > 1 ? html`
              <section aria-label="Theme">
                <div class="gcs-prof-h"><h2>Theme</h2>
                  <span>${playing ? 'Changes the look now' : `Put on when ${profile.name} plays`}</span></div>
                <div class="gcs-prof-themes">
                  ${looks.map((t, i) => html`
                    <button key=${t.id || 'default'} type="button" class="gcs-prof-theme"
                            data-on=${on('theme', i)} data-sel=${worn !== undefined && worn === t.id ? '1' : '0'}
                            onClick=${() => click('theme', i)}>
                      ${t.preview
                        ? html`<img src=${t.preview} alt="" />`
                        : html`<span class="gcs-prof-theme-plain" aria-hidden="true"><i></i><i></i><i></i></span>`}
                      <b>${t.name}</b>
                    </button>`)}
                </div>
              </section>` : null}
            ${msg ? html`<p class="gcs-prof-msg" role="status">${msg}</p>` : null}
          </div>
        </div>
        <div class="gcs-prof-hint"><${PadHints} text="✕ Choose · ○ Back" /></div>
      </div>`
  }
}
