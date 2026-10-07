/**
 * One profile's page, over the whole screen: who it is on the left (animal,
 * name, what it has played, Switch / Rename / Delete), how it looks on the
 * right (picture, colour, theme, controllers), every choice in view instead
 * of behind a dialog.
 *
 * The pad moves in two dimensions: ↑/↓ between the left column's buttons, or
 * between the picture rows, the colours, the themes and the controllers; ←/→
 * along a row, and from the first of a row back to the left column. ✕ applies
 * a choice at once; Delete takes two presses; ○ cancels adding a controller,
 * else goes back to the list.
 */
import { AVATARS, avatarFace } from './avatars.js'
import { PadHints } from '../lib/padKey.js'
import { PAD_COLUMNS, createProfilePads, padTiles } from './profilePads.js'

const COLUMNS = 6
const PICTURES = [[null, 'Initial'], ...AVATARS.map(([key, label]) => [key, label])]

/** The cursor's next tile in the controllers row, or where ↑ leaves it for. */
const padStep = (i, dx, dy, len, above) => {
  if (dx < 0 && i % PAD_COLUMNS === 0) return { zone: 'side', i: 0 }
  if (dx !== 0) return i + dx >= 0 && i + dx < len ? { zone: 'pad', i: i + dx } : null
  if (dy < 0) return i >= PAD_COLUMNS ? { zone: 'pad', i: i - PAD_COLUMNS } : { zone: above.zone, i: Math.min(i, above.len - 1) }
  return i + PAD_COLUMNS < len ? { zone: 'pad', i: i + PAD_COLUMNS } : null
}

export const createProfileDetail = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui
  const Pads = createProfilePads(sdk)

  /**
   * @param profile  the profile shown; `playing` when it is the active one
   * @param palette  [{color, name}]; looks [{id, name, preview}] (id null: built-in)
   * @param stats    {secs, games} for the profile playing, else null
   * @param onPick   ({avatar} | {color} | {theme}); onSwitch, onRename, onDelete, onBack ()
   * @param pads     the connected pads; owners {pad id: other profile's name}
   * @param adding   picking a pad to add; onAddStart (), onAddPad (id), onRemovePad (id), onAddEnd ()
   */
  return ({ profile, playing, palette, looks, stats, msg, active, pads, owners, adding,
            onPick, onSwitch, onRename, onDelete, onBack,
            onAddStart, onAddPad, onRemovePad, onAddEnd }) => {
    const side = [
      ...(playing ? [] : [['switch', `Switch to ${profile.name}`]]),
      ['rename', 'Rename'],
      ...(profile.primary ? [] : [['delete', `Delete ${profile.name}`]]),
    ]
    const [cur, setCur] = useState({ zone: 'pic', i: Math.max(0, PICTURES.findIndex(([k]) => k === (profile.avatar || null))) })
    const [armed, setArmed] = useState(false)
    const tiles = padTiles({ mine: profile.controllers || [], pads, owners, adding })
    const ref = useRef({})
    // The pad handlers are bound once; they read the latest callbacks here.
    ref.current = { cur, side, armed, palette, looks, tiles, adding,
      onPick, onSwitch, onRename, onDelete, onAddStart, onAddPad, onRemovePad, onAddEnd }
    const box = useRef(null)
    useEffect(() => { if (cur.zone !== 'side' || side[cur.i]?.[0] !== 'delete') setArmed(false) }, [cur.zone, cur.i])
    // Into the pick list on its first tile; back out onto "Add controller".
    const was = useRef(adding)
    useEffect(() => {
      if (was.current === adding) return
      was.current = adding
      setCur({ zone: 'pad', i: adding ? 0 : tiles.length - 1 })
    }, [adding])
    // A removed pad shortens the row under the cursor.
    useEffect(() => {
      setCur((c) => (c.zone === 'pad' && c.i >= tiles.length ? { zone: 'pad', i: tiles.length - 1 } : c))
    }, [tiles.length])
    // A fourth pad wraps to a second row, below the fold on a 1080p screen.
    useEffect(() => {
      const el = cur.zone === 'pad' && box.current && box.current.querySelector('.gcs-prof-pad[data-on="1"]')
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' })
    }, [cur.zone, cur.i])

    const worn = 'theme' in profile ? profile.theme : undefined
    const run = (zone, i) => {
      const c = ref.current
      if (zone === 'side') {
        const verb = c.side[i] && c.side[i][0]
        if (verb === 'switch') c.onSwitch()
        else if (verb === 'rename') c.onRename()
        else if (verb === 'delete') { if (c.armed) c.onDelete(); else setArmed(true) }
      } else if (zone === 'pic') c.onPick({ avatar: PICTURES[i][0] })
      else if (zone === 'col' && c.palette[i]) c.onPick({ color: c.palette[i].color })
      else if (zone === 'theme' && c.looks[i]) c.onPick({ theme: c.looks[i].id })
      else if (zone === 'pad' && c.tiles[i]) {
        const t = c.tiles[i]
        if (t.kind === 'pad') c.onRemovePad(t.key)
        else if (t.kind === 'pick') c.onAddPad(t.key)
        else if (t.kind === 'add') c.onAddStart()
        else c.onAddEnd()
      }
    }

    useEffect(() => {
      if (!active) return undefined
      const go = (next) => { if (next) { sdk.system.playSound('move'); setCur(next) } }
      const step = (dx, dy) => {
        const { cur: { zone, i }, side: s, palette: pal, looks: lk, tiles: tl } = ref.current
        const themed = lk.length > 1
        const row = Math.floor(i / COLUMNS)
        const col = i % COLUMNS
        if (zone === 'side') {
          if (dx > 0) return { zone: 'pic', i: 0 }
          const n = i + dy
          return dx === 0 && n >= 0 && n < s.length ? { zone, i: n } : null
        }
        if (zone === 'pad') return padStep(i, dx, dy, tl.length, themed ? { zone: 'theme', len: lk.length } : { zone: 'col', len: pal.length })
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
          return themed ? { zone: 'theme', i: Math.min(i, lk.length - 1) } : { zone: 'pad', i: Math.min(i, PAD_COLUMNS - 1, tl.length - 1) }
        }
        if (dy > 0) return { zone: 'pad', i: Math.min(i, PAD_COLUMNS - 1, tl.length - 1) }
        return pal.length ? { zone: 'col', i: Math.min(i, pal.length - 1) } : null
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => go(step(-1, 0))),
        sdk.input.onGp('gp:dpad-right', () => go(step(1, 0))),
        sdk.input.onGp('gp:dpad-up', () => go(step(0, -1))),
        sdk.input.onGp('gp:dpad-down', () => go(step(0, 1))),
        sdk.input.onGp('gp:confirm', () => { sdk.system.playSound('confirm'); run(ref.current.cur.zone, ref.current.cur.i) }),
        sdk.input.onGp('gp:back', () => {
          sdk.system.playSound('back')
          if (ref.current.adding) ref.current.onAddEnd()
          else onBack()
        }),
      ]
      return () => offs.forEach((off) => off())
    }, [active])

    const on = (zone, i) => (cur.zone === zone && cur.i === i ? '1' : '0')
    const click = (zone, i) => { setCur({ zone, i }); run(zone, i) }
    const kind = cur.zone === 'pad' && tiles[cur.i] ? tiles[cur.i].kind : ''
    const hint = `✕ ${kind === 'pad' ? 'Remove' : kind === 'pick' ? 'Add' : 'Choose'} · ○ ${adding ? 'Cancel' : 'Back'}`
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

          <div class="gcs-prof-looks" ref=${box}>
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
            <${Pads} tiles=${tiles} title=${profile.name} adding=${adding}
              on=${(i) => on('pad', i)} onClick=${(i) => click('pad', i)} />
            ${msg ? html`<p class="gcs-prof-msg" role="status">${msg}</p>` : null}
          </div>
        </div>
        <div class="gcs-prof-hint"><${PadHints} text=${hint} /></div>
      </div>`
  }
}
