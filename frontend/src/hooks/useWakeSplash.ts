import { useState } from 'react'

/**
 * Whether the boot animation is over, for this wake only. Derived, not reset
 * in an effect: the wake that lifts the black layer starts the splash in the
 * same render, so not one frame of Home shows between the two. A late onDone
 * from the previous wake's splash names an old wake and changes nothing.
 */
export function useWakeSplash(wakeCount: number): [done: boolean, finish: () => void] {
  const [doneFor, setDoneFor] = useState<number | null>(null)
  return [doneFor === wakeCount, () => setDoneFor(wakeCount)]
}
