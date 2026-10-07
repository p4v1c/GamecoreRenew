/**
 * A profile's controllers, on its page: the pads it shows, then "Add
 * controller"; while adding, the connected pads it does not show, then
 * Cancel. For display only: no save, theme or login follows a pad. Markup
 * only; the cursor and the presses are profileDetail.js's.
 */
import { ICONS } from './icons.js'

export const PAD_COLUMNS = 3
const PLUS = 'M12 5v14M5 12h14'
const OVER = { Bluetooth: 'Connected over Bluetooth', USB: 'Connected over USB', Wired: 'Connected by cable' }
const connected = (pad) => OVER[pad.connection] || 'Connected'

/**
 * The tiles in pad order: [{key, kind, name, note}], kind one of
 * 'pad' (shown here; ✕ removes), 'add', 'pick' (✕ adds), 'cancel'.
 * @param mine     the profile's `controllers` ([{id, name}])
 * @param pads     the connected pads (`GET /controllers/pads`)
 * @param owners   {controller id: the name of the other profile showing it}
 */
export const padTiles = ({ mine, pads, owners, adding }) => {
  if (adding) {
    return [
      ...pads.filter((p) => !mine.some((c) => c.id === p.id)).map((p) => ({
        key: p.id, kind: 'pick', name: p.name,
        note: owners[p.id] ? `Shown on ${owners[p.id]}` : connected(p),
      })),
      { key: 'cancel', kind: 'cancel', name: 'Cancel', note: '' },
    ]
  }
  return [
    ...mine.map((c) => {
      const live = pads.find((p) => p.id === c.id)
      return { key: c.id, kind: 'pad', name: live ? live.name : c.name, note: live ? connected(live) : 'Not connected' }
    }),
    { key: 'add', kind: 'add', name: 'Add controller', note: '' },
  ]
}

export const createProfilePads = (sdk) => {
  const { html } = sdk.ui
  const Icon = ({ d }) => html`
    <svg class="gcs-prof-pad-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d=${d} /></svg>`
  const VERB = { pad: 'Remove', pick: 'Add' }

  /** @param on (i) '1' when tile i holds the cursor; onClick (i) */
  return ({ tiles, title, adding, on, onClick }) => {
    const count = tiles.length - 1
    const state = adding ? `Pick one to show on ${title}`
      : count ? `${count} controller${count > 1 ? 's' : ''}` : 'None yet'
    return html`
      <section aria-label="Controllers">
        <div class="gcs-prof-h"><h2>Controllers</h2><span>${state}</span></div>
        <div class="gcs-prof-pads">
          ${tiles.map((t, i) => html`
            <button key=${t.key} type="button" class="gcs-prof-pad" data-kind=${t.kind} data-on=${on(i)}
                    aria-label=${VERB[t.kind] ? `${VERB[t.kind]} ${t.name}` : t.name} onClick=${() => onClick(i)}>
              ${t.kind === 'cancel' ? null : html`<${Icon} d=${t.kind === 'add' ? PLUS : ICONS.controllers} />`}
              <span class="gcs-prof-pad-text"><b>${t.name}</b>${t.note ? html`<i>${t.note}</i>` : null}</span>
              ${VERB[t.kind] ? html`<span class="gcs-prof-pad-verb">${VERB[t.kind]}</span>` : null}
            </button>`)}
        </div>
      </section>`
  }
}
