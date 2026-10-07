/**
 * "Who's playing?": one tile per profile, then "Add profile". Markup and the
 * pad's cursor only; when to show it and what a pick does are the host's
 * (components/WhoIsPlaying.tsx), so every theme gets the same screen.
 *
 * ←/→ move, ✕ picks, ○ keeps the profile already active.
 */
import { avatarFace } from './avatars.js'
import { PadHints } from '../lib/padKey.js'

export const createWhoIsPlaying = (sdk, parts = {}) => {
  const { html, useState, useEffect, useRef } = sdk.ui
  const skin = parts.skin ? ` ${parts.skin}` : ''

  /**
   * @param profiles  the list from `GET /profiles`
   * @param activeId  where the cursor starts
   * @param active    false while something above (the keyboard) owns the pad
   * @param onPick    (id) a profile; onAdd () the last tile; onSkip () ○
   */
  const View = ({ profiles, activeId, active, msg, onPick, onAdd, onSkip }) => {
    const count = profiles.length + 1
    const [idx, setIdx] = useState(Math.max(0, profiles.findIndex((p) => p.id === activeId)))
    const ref = useRef({ idx, profiles })
    useEffect(() => { ref.current = { idx, profiles } })

    const choose = (i) => {
      sdk.system.playSound('confirm')
      const p = ref.current.profiles[i]
      if (p) onPick(p.id)
      else onAdd()
    }

    useEffect(() => {
      if (!active) return
      const move = (d) => { sdk.system.playSound('move'); setIdx((i) => (i + d + count) % count) }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => move(-1)),
        sdk.input.onGp('gp:dpad-right', () => move(1)),
        sdk.input.onGp('gp:confirm', () => choose(ref.current.idx)),
        sdk.input.onGp('gp:back', () => { sdk.system.playSound('back'); onSkip() }),
      ]
      return () => offs.forEach((off) => off())
    }, [active, count])

    return html`
      <div class=${`gcs-who${skin}`} role="dialog" aria-modal="true" aria-labelledby="gcs-who-title">
        <h1 class="gcs-who-title" id="gcs-who-title">Who’s using this controller?</h1>
        <div class="gcs-who-tiles">
          ${profiles.map((p, i) => html`
            <button key=${p.id} type="button" class="gcs-who-tile"
                    data-on=${idx === i ? '1' : '0'} onClick=${() => { setIdx(i); choose(i) }}>
              <span class="gcs-who-avatar" aria-hidden="true" style=${{ background: p.color }}>${avatarFace(html, p)}</span>
              <b>${p.name}</b>
            </button>`)}
          <button type="button" class="gcs-who-tile" data-add="1"
                  data-on=${idx === profiles.length ? '1' : '0'}
                  onClick=${() => { setIdx(profiles.length); choose(profiles.length) }}>
            <span class="gcs-who-avatar" aria-hidden="true">+</span>
            <b>Add profile</b>
          </button>
        </div>
        <p class="gcs-who-msg" role="status">${msg || ''}</p>
        <div class="gcs-who-hint"><${PadHints} text="←→ Move · ✕ Select · ○ Skip" /></div>
      </div>`
  }
  // The class the host puts on its keyboard, so it wears the same palette.
  View.skin = parts.skin || ''
  return View
}
