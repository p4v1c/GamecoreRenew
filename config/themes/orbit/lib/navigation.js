/** Spatial navigation over the actual controls; the host retains modal ownership. */
export function createNavigation(sdk) {
  const {useEffect, useRef} = sdk.ui
  return function useNavigation(root, enabled, {confirm, back, tab, initial} = {}) {
    const live = useRef(null)
    live.current = {enabled, confirm, back, tab, initial}
    useEffect(() => {
      const allowed = () => {
        const state = sdk.nav.get()
        return live.current.enabled && !state.modalDepth && !state.sessionGameKey
          && !state.powerPending && state.standby === 'off'
      }
      const controls = () => [...(root.current?.querySelectorAll('button:not(:disabled),input,select') || [])]
        .filter(el => !el.closest('[hidden]') && getComputedStyle(el).display !== 'none')
      const focus = el => {
        root.current?.querySelectorAll('.pad-focus').forEach(node => node.classList.remove('pad-focus'))
        el?.classList.add('pad-focus')
        el?.focus({preventScroll: true})
        el?.scrollIntoView?.({block: 'nearest', inline: 'nearest'})
      }
      const current = () => {
        const active = document.activeElement
        return root.current?.contains(active) ? active
          : root.current?.querySelector(live.current.initial || '[data-active="true"]') || controls()[0]
      }
      const move = (dx, dy) => {
        if (!allowed()) return
        const from = current()
        if (!from) return
        const rect = from.getBoundingClientRect()
        const candidates = controls().filter(el => el !== from).map(el => {
          const r = el.getBoundingClientRect()
          const x = (r.left + r.right - rect.left - rect.right) / 2
          const y = (r.top + r.bottom - rect.top - rect.bottom) / 2
          const forward = dx * x + dy * y
          const sideways = Math.abs(dy * x + dx * y)
          return {el, forward, score: forward + sideways * 3}
        }).filter(c => c.forward > 2).sort((a, b) => a.score - b.score)
        focus(candidates[0]?.el || from)
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => move(-1, 0)),
        sdk.input.onGp('gp:dpad-right', () => move(1, 0)),
        sdk.input.onGp('gp:dpad-up', () => move(0, -1)),
        sdk.input.onGp('gp:dpad-down', () => move(0, 1)),
        sdk.input.onGp('gp:confirm', () => {
          if (!allowed()) return
          const active = document.activeElement
          if (root.current?.contains(active) && active.matches('button,input,select')) active.click()
          else live.current.confirm?.()
        }),
        sdk.input.onGp('gp:back', () => { if (allowed()) live.current.back?.() }),
        sdk.input.onGp('gp:l1', () => { if (allowed()) live.current.tab?.(-1) }),
        sdk.input.onGp('gp:r1', () => { if (allowed()) live.current.tab?.(1) }),
      ]
      return () => offs.forEach(off => off())
    }, [])
  }
}
