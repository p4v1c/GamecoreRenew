/**
 * The page's own ground, before the bundle runs.
 *
 * index.html paints before any module executes. Hardcoded dark, it put a dark
 * frame between Shelf's paper window and its paper splash at every start.
 */
import { afterEach, describe, expect, it } from 'vitest'
import page from '../index.html?raw'

function loadPage(bootBackground: unknown): void {
  ;(window as unknown as { gamecore?: unknown }).gamecore = { bootBackground }
  const doc = new DOMParser().parseFromString(page, 'text/html')
  document.head.innerHTML = doc.head.innerHTML
  document.body.innerHTML = doc.body.innerHTML
  document.documentElement.removeAttribute('style')
  // innerHTML never runs scripts; run the classic (non-module) ones by hand.
  doc.querySelectorAll('script:not([type="module"])').forEach(s => {
    new Function(s.textContent ?? '')()
  })
}

function background(el: Element): string {
  return getComputedStyle(el).backgroundColor
}

afterEach(() => {
  delete (window as unknown as { gamecore?: unknown }).gamecore
})

describe('index.html boot ground', () => {
  it('paints the shell’s boot colour on the first frame', () => {
    loadPage('#F4F2ED')
    expect(background(document.documentElement)).toBe('rgb(244, 242, 237)')
  })

  it('leaves body and #root clear so they do not cover it', () => {
    loadPage('#F4F2ED')
    for (const el of [document.body, document.getElementById('root')!]) {
      expect(['', 'transparent', 'rgba(0, 0, 0, 0)']).toContain(background(el))
    }
  })

  it('keeps the default dark ground outside Electron or on a bad value', () => {
    for (const value of [undefined, 'red; color: blue', 'url(x)']) {
      loadPage(value)
      expect(background(document.documentElement)).toBe('rgb(9, 9, 15)')
    }
  })
})
