/** The splash after a wake: never one committed frame "done" for the new wake. */
import { act, render } from '@testing-library/react'
import { useLayoutEffect } from 'react'
import { expect, it } from 'vitest'
import { useWakeSplash } from './useWakeSplash'

it('a new wake commits with the splash already back', () => {
  const committed: boolean[] = []
  let finish = () => {}
  const Probe = ({ wake }: { wake: number }) => {
    const [done, f] = useWakeSplash(wake)
    finish = f
    useLayoutEffect(() => { committed.push(done) })
    return null
  }
  const { rerender } = render(<Probe wake={0} />)
  act(() => finish())
  expect(committed).toEqual([false, true])
  const stale = finish
  rerender(<Probe wake={1} />)
  expect(committed).toEqual([false, true, false])
  act(() => stale())                    // the previous splash's late onDone
  expect(committed[committed.length - 1]).toBe(false)
})
