/**
 * Is anyone actually looking at this?
 *
 * The wall drifts, slowly, for hours. It must stop the moment a game takes the
 * screen or the box goes to sleep — a paused animation costs nothing, a running
 * one behind an emulator costs a core.
 */
/**
 * Read out of the store, not rebuilt from the three `standby:*` events.
 *
 * The host swallows the first press on a sleeping box into a wake, and lets go
 * after a grace period if the box never answers — so the store is the only
 * place that knows whether the box is REALLY still asleep. A copy assembled
 * from the events here would go on saying "asleep" after the host had given
 * up, and the wall would stay frozen with a live cursor moving over it.
 */
export const createUseIdle = (sdk) => {
  return () => {
    const asleep = sdk.nav.use((s) => s.standby !== 'off')
    const playing = sdk.nav.use((s) => !!s.sessionGameKey)
    return asleep || playing
  }
}
