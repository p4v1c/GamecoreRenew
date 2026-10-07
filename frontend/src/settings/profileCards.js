/**
 * Settings → Profiles, the list: one card per profile (animal, name, theme,
 * Switch and Edit), an "Add profile" card, then "Log in automatically" as an
 * ordinary settings row.
 *
 * The pad walks the cards' buttons left and right, in reading order, and ↓
 * drops to the row; ↑ comes back to the button it left. ← past the first
 * button goes to the rail.
 */
import { avatarFace } from './avatars.js'
import { follow } from './list.js'
import { wornTheme } from './themeNames.js'

export const createProfileCards = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  /**
   * @param list       the profiles; `activeId` the one playing
   * @param themeName  (id) → the theme's name (themeNames.js)
   * @param onSelect / onEdit (profile id), onAdd (), onAutoLogin (on)
   */
  return ({ list, activeId, themeName, autoLogin, autoDesc, title, state, sub, msg,
            active, onLeave, onLeft, onSelect, onEdit, onAdd, onAutoLogin }) => {
    // Every button on the cards, left to right: [verb, profile id].
    const buttons = [
      ...list.flatMap((p) => (p.id === activeId ? [['edit', p.id]] : [['select', p.id], ['edit', p.id]])),
      ['add', null],
    ]
    const [at, setAt] = useState(Math.max(0, buttons.findIndex(([v, id]) => v === 'edit' && id === activeId)))
    const [onRow, setOnRow] = useState(false)
    const ref = useRef({})
    ref.current = { at, onRow, buttons, autoLogin }
    const rowRef = useRef(null)

    useEffect(() => { if (at >= buttons.length) setAt(buttons.length - 1) }, [buttons.length, at])
    useEffect(() => { if (active && onRow) follow(rowRef.current, false) }, [active, onRow])

    const press = ([verb, id]) => {
      if (verb === 'select') onSelect(id)
      else if (verb === 'edit') onEdit(id)
      else onAdd()
    }

    useEffect(() => {
      if (!active) return undefined
      const move = (fn) => { sdk.system.playSound('move'); fn() }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => {
          const c = ref.current
          if (c.onRow || c.at === 0) onLeft()
          else move(() => setAt(c.at - 1))
        }),
        sdk.input.onGp('gp:dpad-right', () => {
          const c = ref.current
          if (!c.onRow && c.at < c.buttons.length - 1) move(() => setAt(c.at + 1))
        }),
        sdk.input.onGp('gp:dpad-down', () => { if (!ref.current.onRow) move(() => setOnRow(true)) }),
        sdk.input.onGp('gp:dpad-up', () => { if (ref.current.onRow) move(() => setOnRow(false)) }),
        sdk.input.onGp('gp:confirm', () => {
          const c = ref.current
          sdk.system.playSound('confirm')
          if (c.onRow) onAutoLogin(!c.autoLogin)
          else if (c.buttons[c.at]) press(c.buttons[c.at])
        }),
        sdk.input.onGp('gp:back', onLeave),
      ]
      return () => offs.forEach((off) => off())
    }, [active, onLeave, onLeft])

    const focused = (verb, id) => active && !onRow && buttons[at] && buttons[at][0] === verb && buttons[at][1] === id
    const button = (verb, id, label) => html`
      <button type="button" class="gcs-pcard-btn"
              data-on=${focused(verb, id) ? '1' : '0'}
              onClick=${() => { setOnRow(false); setAt(buttons.findIndex(([v, i]) => v === verb && i === id)); press([verb, id]) }}>
        ${label}
      </button>`

    return html`
      <section class="gcs-set-main gcs-pcards-page" data-zone=${active ? 'on' : 'off'}>
        <div class="gcs-set-h-row">
          <div class="gcs-set-h">${title}</div>
          ${state ? html`<div class="gcs-wifi-state">${state}</div>` : null}
        </div>
        ${sub ? html`<p class="gcs-set-sub">${sub}</p>` : null}
        ${msg ? html`<div class="gcs-wifi-msg">${msg}</div>` : null}

        <div class="gcs-pcards">
          ${list.map((p) => {
            const playing = p.id === activeId
            const on = active && !onRow && buttons[at] && buttons[at][1] === p.id
            return html`
              <article key=${p.id} class="gcs-pcard" data-on=${on ? '1' : '0'}>
                <span class="gcs-pcard-face" aria-hidden="true" style=${{ background: p.color }}>${avatarFace(html, p)}</span>
                <b class="gcs-pcard-name">${p.name}</b>
                ${playing ? html`<span class="gcs-pcard-now">Playing now</span>` : null}
                <i class="gcs-pcard-theme">${wornTheme(p, themeName)}</i>
                <span class="gcs-pcard-btns">
                  ${playing ? null : button('select', p.id, 'Switch')}
                  ${button('edit', p.id, 'Edit')}
                </span>
              </article>`
          })}
          <button type="button" class="gcs-pcard gcs-pcard-add" data-on=${focused('add', null) ? '1' : '0'}
                  onClick=${() => { setOnRow(false); setAt(buttons.length - 1); onAdd() }}>
            <span class="gcs-pcard-plus" aria-hidden="true">+</span>
            <b class="gcs-pcard-name">Add profile</b>
            <i class="gcs-pcard-theme">Name, animal, colour</i>
          </button>
        </div>

        <div class="gcs-row2" data-on=${active && onRow ? '1' : '0'} data-type="toggle" role="switch"
             aria-label="Log in automatically" aria-checked=${String(!!autoLogin)} ref=${rowRef}
             onClick=${() => { setOnRow(true); onAutoLogin(!autoLogin) }}>
          <span class="gcs-row2-text"><b>Log in automatically</b><i>${autoDesc}</i></span>
          <span class="gcs-tgl" data-v=${autoLogin ? '1' : '0'}><i></i></span>
        </div>
      </section>`
  }
}
