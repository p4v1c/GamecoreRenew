/**
 * Is the machine busy or asleep?
 *
 * Shared by the ocean and the dune: both must stop animating while a game runs
 * or the box is in standby, or they burn a core behind a screen nobody sees.
 */
export const createUseIdle = (sdk) => {
  const { useState, useEffect } = sdk.ui
  return () => {
    const [asleep, setAsleep] = useState(false)
    useEffect(() => {
      const offs = [
        sdk.system.onWsEvent('standby:screensaver', () => setAsleep(true)),
        sdk.system.onWsEvent('standby:sleep', () => setAsleep(true)),
        sdk.system.onWsEvent('standby:exit', () => setAsleep(false)),
      ]
      return () => offs.forEach(off => off())
    }, [])
    const playing = sdk.nav.use(s => !!s.sessionGameKey)
    return asleep || playing
  }
}
