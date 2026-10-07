/**
 * The picture picker of Settings → Profiles: every animal at once, on the
 * profile's colour, in a grid the d-pad walks in two directions. Cycling
 * eleven pictures with ←/→ on one row hid all but one of them.
 *
 * The first tile is the initial, for a profile that wants no picture.
 * ✕ picks, ○ leaves the picture as it was.
 */
import { AVATARS, avatarFace } from './avatars.js'
import { PadHints } from '../lib/padKey.js'

const COLUMNS = 6
// The press that opened the picker must not pick (the dialog's own rule).
const ARM_MS = 350

export const createAvatarPicker = (sdk, Dialog) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  /** `profile` gives the colour and name; onPick(key | null), onCancel(). */
  return ({ profile, onPick, onCancel }) => {
    const keys = [null, ...AVATARS.map(([key]) => key)]
    const labels = ['Initial', ...AVATARS.map(([, label]) => label)]
    const [idx, setIdx] = useState(Math.max(0, keys.indexOf(profile.avatar || null)))
    const ref = useRef({ idx })
    useEffect(() => { ref.current = { idx } })
    const openedAt = useRef(Date.now())

    useEffect(() => {
      const n = keys.length
      const move = (d) => {
        sdk.system.playSound('move')
        setIdx((i) => {
          const next = i + d
          // Up and down stay in the column; left and right wrap the rows.
          if (Math.abs(d) === COLUMNS) return next < 0 || next >= n ? i : next
          return (next + n) % n
        })
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => move(-1)),
        sdk.input.onGp('gp:dpad-right', () => move(1)),
        sdk.input.onGp('gp:dpad-up', () => move(-COLUMNS)),
        sdk.input.onGp('gp:dpad-down', () => move(COLUMNS)),
        sdk.input.onGp('gp:confirm', () => {
          if (Date.now() - openedAt.current < ARM_MS) return
          sdk.system.playSound('confirm')
          onPick(keys[ref.current.idx])
        }),
        sdk.input.onGp('gp:back', () => { sdk.system.playSound('back'); onCancel() }),
      ]
      return () => offs.forEach((off) => off())
    }, [])

    return html`
      <${Dialog} kicker=${profile.name} title="Choose a picture" wide=${true} ownsInput=${true} onCancel=${onCancel}>
        <div class="gcs-pick-grid" role="listbox" aria-label="Pictures">
          ${keys.map((key, i) => html`
            <button key=${key || 'initial'} type="button" class="gcs-pick-tile" role="option"
                    aria-selected=${idx === i} data-on=${idx === i ? '1' : '0'}
                    onClick=${() => { setIdx(i); onPick(key) }}>
              <span class="gcs-pick-face" aria-hidden="true" style=${{ background: profile.color }}>
                ${avatarFace(html, { name: profile.name, avatar: key })}
              </span>
              <span class="gcs-pick-label">${labels[i]}</span>
            </button>`)}
        </div>
        <div class="gcs-pick-hint"><${PadHints} text="✕ Choose · ○ Back" /></div>
      <//>`
  }
}
