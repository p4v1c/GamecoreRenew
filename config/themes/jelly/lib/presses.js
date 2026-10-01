/** Which screen owns a press, judged by the store as it was when it began.
 *
 * One press reaches the host's listeners and Jelly's in turn; when the host's
 * ○ takes the library home, a later listener would read `home` and act twice.
 * A capturing listener keeps the state from before, until the dispatch ends. */
const now = (sdk) => ({...sdk.nav.get(), transition: sdk.nav.use.getState?.().transition ?? null})

let pressed = null
let watching = false

export function watchPresses(sdk) {
  if (watching || typeof window === 'undefined') return
  watching = true
  for (const name of sdk.input.events || []) {
    window.addEventListener(name, () => {
      pressed = now(sdk)
      queueMicrotask(() => { pressed = null })
    }, {capture: true})
  }
}

const atPress = (sdk) => pressed || now(sdk)

/** The press being dispatched, or null between presses; a new object each time. */
export const currentPress = () => pressed

const idle = (s) => !s.sessionGameKey && !s.powerPending && s.standby === 'off'

/** The dashboard owns the pad: nothing above it, no game, no launch. */
export const homeOwnsPad = (sdk) => {
  const s = atPress(sdk)
  return s.screen === 'home' && !s.modalDepth && s.transition !== 'launch' && idle(s)
}

/** The library screen owns the pad, and nothing is over it. */
export const libraryOwnsPad = (sdk) => {
  const s = atPress(sdk)
  return s.screen === 'library' && !s.modalDepth && s.transition !== 'launch' && idle(s)
}

/** A layer opened at this modal depth owns the pad, and nothing is above it. */
export const layerOwnsPad = (sdk, depth) => {
  const s = atPress(sdk)
  return depth > 0 && s.modalDepth === depth && idle(s)
}
