/**
 * "It is taking a while" — the second thing a waiting screen has to say.
 *
 * A spinner that never changes its mind is indistinguishable from a spinner
 * that is stuck, and the settings screen has two waits that are genuinely slow
 * on purpose: the Bluetooth scan runs for ten seconds by design, and the Wi-Fi
 * list waits on a rescan. So the wait says what it is doing, and after a while
 * it says so differently.
 *
 * Deliberately NOT an error state. Nothing has failed at this point — the whole
 * value of the second message is that it reassures rather than alarms, so the
 * caller can keep waiting instead of being told to go away.
 */
export const createUseSlow = (sdk) => {
  const { useState, useEffect } = sdk.ui

  /**
   * @param waiting  whether the wait is currently on
   * @param afterMs  how long is "a while" for THIS wait — a scan that always
   *                 takes ten seconds must not call itself slow at four
   * @returns        true once the wait has run longer than that
   */
  return (waiting, afterMs) => {
    const [slow, setSlow] = useState(false)

    useEffect(() => {
      if (!waiting) { setSlow(false); return }
      const t = setTimeout(() => setSlow(true), afterMs)
      return () => clearTimeout(t)
    }, [waiting, afterMs])

    return waiting && slow
  }
}
