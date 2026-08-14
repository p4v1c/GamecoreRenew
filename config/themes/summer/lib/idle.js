/**
 * Is the machine busy or asleep?
 *
 * Shared by the ocean and the dune: both must stop animating while a game runs
 * or the box is in standby, or they burn a core behind a screen nobody sees.
 *
 * Read out of the store, not rebuilt from the three `standby:*` events. The
 * host swallows the first press on a sleeping box into a wake and lets go after
 * a grace period if the box never answers, so the store is the only place that
 * knows whether it is REALLY still asleep. A copy assembled here would go on
 * saying "asleep" after the host had given up.
 */
export const createUseIdle = (sdk) => {
  return () => {
    const asleep = sdk.nav.use(s => s.standby !== 'off')
    const playing = sdk.nav.use(s => !!s.sessionGameKey)
    return asleep || playing
  }
}
