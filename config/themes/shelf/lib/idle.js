/**
 * Is anyone actually looking at this?
 *
 * The wall drifts, slowly, for hours. It must stop the moment a game takes the
 * screen or the box goes to sleep — a paused animation costs nothing, a running
 * one behind an emulator costs a core.
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
      return () => offs.forEach((off) => off())
    }, [])
    const playing = sdk.nav.use((s) => !!s.sessionGameKey)
    return asleep || playing
  }
}
