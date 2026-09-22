/**
 * `versionLabel` — one `v`, whatever the box answered.
 *
 * An installed box's VERSION is the release tag, `v1.2.60`, and the settings
 * rail, the System page and its update line all printed `v${version}`: the
 * owner read "vv1.2.60" on the TV.
 */
import { describe, expect, it, vi } from 'vitest'

// Through a variable path, like the other tests of these plain .js modules:
// `npm run build` typechecks this file and list.js has no declarations.
const LIST = './list.js'
const { versionLabel, follow } = await import(/* @vite-ignore */ LIST) as {
  versionLabel: (v?: string) => string
  follow: (el: Element | null, first?: boolean) => void
}

describe('versionLabel', () => {
  it('shows one v whether or not the box wrote one', () => {
    expect(versionLabel('v1.2.60')).toBe('v1.2.60')
    expect(versionLabel('1.2.60')).toBe('v1.2.60')
    expect(versionLabel('V1.2.60')).toBe('v1.2.60')
  })

  it('shows nothing rather than a bare v when there is no version', () => {
    expect(versionLabel('')).toBe('')
    expect(versionLabel(undefined)).toBe('')
  })
})

describe('follow — the pad\'s cursor stays on screen', () => {
  // jsdom has no layout: give each box the sizes a real one would have.
  const box = (cls: string, scrollHeight: number, clientHeight: number) => {
    const el = document.createElement('div')
    el.className = cls
    Object.defineProperty(el, 'scrollHeight', { value: scrollHeight })
    Object.defineProperty(el, 'clientHeight', { value: clientHeight })
    el.scrollTop = 120
    return el
  }

  it('reveals a row with the least scroll it can', () => {
    const row = document.createElement('div')
    const spy = vi.fn()
    ;(row as unknown as { scrollIntoView: typeof spy }).scrollIntoView = spy
    follow(row)
    expect(spy).toHaveBeenCalledWith({ block: 'nearest' })
  })

  it('takes every scroller back to the top on the first row, up to its page and no further', () => {
    // The bug: back on the first row, the title above it stayed scrolled away,
    // and only a mouse wheel could bring it back.
    const outside = box('gcs-set-body', 900, 400)
    const page = box('gcs-set-main', 900, 400)
    const list = box('gcs-bt-list', 900, 400)
    const row = document.createElement('div')
    outside.appendChild(page); page.appendChild(list); list.appendChild(row)

    follow(row, true)

    expect(list.scrollTop).toBe(0)
    expect(page.scrollTop).toBe(0)
    expect(outside.scrollTop).toBe(120)
  })

  it('does nothing without a row', () => {
    expect(() => follow(null)).not.toThrow()
  })
})
