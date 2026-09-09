/**
 * Orbit's suspended-session surface, and the two ways it left a player stuck.
 *
 * The host owns every binding here — `SessionBar.tsx` opens the menu on L2,
 * moves the selection with the d-pad and runs the action on ✕. A theme supplies
 * markup and nothing else. That bargain is exactly what both defects broke, in
 * opposite directions:
 *
 *   · **The dock advertised buttons the host does not bind.** The bar owns no
 *     button at all — ✕ was taken away from it deliberately, because the screen
 *     underneath takes ✕ too and one press resumed the session *and* opened
 *     whatever tile the cursor was on. Orbit went on printing "✕ Resume · ○
 *     Back", and it printed it precisely when the bar became usable: the moment
 *     the player could act, Orbit hid the one binding that works (L2) and
 *     offered two that do nothing.
 *   · **The menu drew no cursor.** The host marks the option the pad is on with
 *     `data-active`; it does not move DOM focus. Orbit styled `:hover` and
 *     `:focus-visible` — neither of which a gamepad produces — and not
 *     `data-active`. So the menu opened, ↑/↓ moved a selection nothing drew,
 *     and ✕ confirmed whichever option the player could not see was chosen,
 *     with Resume and "Close game" one invisible step apart.
 *
 * Shelf has neither defect, which is why it worked and Orbit did not.
 */
import React, { createElement } from 'react'
import { render, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import htm from 'htm'

const THEME = '../../../config/themes/orbit'

const ui = {
  html: htm.bind(React.createElement),
  React, useState: React.useState, useEffect: React.useEffect, useRef: React.useRef,
}

const sdk = {
  ui,
  format: { gameName: (s: string) => s.replace(/\.[^.]+$/, '') },
  nav: { get: () => ({ modalDepth: 0, sessionGameKey: null, powerPending: null, standby: 'off' }) },
  system: { asset: (p: string) => `/themes/orbit/${p}` },
}

const SESSION = {
  session: 1, gameKey: 'Zelda_(USA).iso', systemId: 'dolphin', kind: 'game' as const,
}

async function orbitSession() {
  vi.resetModules()
  const { createSession } = await import(/* @vite-ignore */ `${THEME}/lib/session.js`)
  return createSession(sdk)
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

// ── the dock ────────────────────────────────────────────────────────────────

describe('the dock, while the bar can be acted on', () => {
  const dock = async (active: boolean) => {
    const sessions = await orbitSession()
    return render(createElement(sessions.Bar, {
      sessions: [SESSION], focusIdx: 0, active, busy: false,
      onResume: vi.fn(), onClose: vi.fn(),
    }))
  }

  it('names L2, which is the only button the host binds here', async () => {
    const r = await dock(true)
    const hint = r.container.querySelector('.session-dock-active-hint')
    expect(hint?.textContent).toMatch(/L2/)
  })

  it('does not tell the player to press ✕ or ○, which do nothing on the bar', async () => {
    // The defect, exactly. `active` is true whenever the bar is usable, and
    // the CSS shows this span only then — so this text was what the player
    // saw at the one moment they were trying to act.
    const r = await dock(true)
    const hint = r.container.querySelector('.session-dock-active-hint')?.textContent ?? ''
    expect(hint).not.toMatch(/✕/)
    expect(hint).not.toMatch(/○/)
  })

  it('still names L2 when the bar is only sitting there', async () => {
    const r = await dock(false)
    expect(r.container.querySelector('.session-dock-idle-hint')?.textContent).toMatch(/L2/)
  })

  it('keeps the badge that says the same thing', async () => {
    const r = await dock(true)
    expect(r.container.querySelector('.session-dock-shortcut')?.textContent).toBe('L2')
  })
})

// ── the menu ────────────────────────────────────────────────────────────────

describe('the menu, and which option the pad is on', () => {
  const menu = async (actionIdx: number) => {
    const sessions = await orbitSession()
    const actions = [
      { id: 'resume', label: 'Resume game', primary: true, run: vi.fn() },
      { id: 'close', label: 'Close game…', run: vi.fn() },
      { id: 'back', label: 'Back', run: vi.fn() },
    ]
    return render(createElement(sessions.Menu, {
      session: SESSION, sessions: [SESSION], index: 0, confirming: false,
      busy: false, actions, actionIdx, title: (s: typeof SESSION) => s.gameKey,
    }))
  }

  it('marks the option the host says the pad is on', async () => {
    const r = await menu(1)
    const marked = r.container.querySelectorAll('.session-menu-option[data-active="true"]')
    expect(marked).toHaveLength(1)
    expect(marked[0].textContent).toContain('Close game')
  })

  it('moves the mark with the selection, and marks only one', async () => {
    for (const [i, label] of [[0, 'Resume game'], [2, 'Back']] as const) {
      cleanup()
      const r = await menu(i)
      const marked = r.container.querySelectorAll('[data-active="true"]')
      expect(marked).toHaveLength(1)
      expect(marked[0].textContent).toContain(label)
    }
  })

  it('offers the three actions the host resolved, in order', async () => {
    const r = await menu(0)
    const labels = [...r.container.querySelectorAll('.session-menu-option')]
      .map(b => b.textContent?.trim())
    expect(labels).toEqual(['Resume game', 'Close game…', 'Back'])
  })

  // Whether the stylesheet actually DRAWS that mark is asserted in
  // backend/tests/test_theme_session_cursor.py: jsdom applies no external CSS,
  // so a render here can only prove the attribute is set — which it always
  // was. Nothing drawing it was the defect.

  it('does not rely on hover or focus, which a gamepad never produces', async () => {
    // The host tracks `actionIdx`; it never calls .focus() on these buttons.
    const r = await menu(1)
    expect(document.activeElement).toBe(document.body)
    expect(r.container.querySelector('[data-active="true"]')).toBeTruthy()
  })
})

describe('the confirmation step', () => {
  it('marks its option too, so Close is never confirmed blind', async () => {
    const sessions = await orbitSession()
    const actions = [
      { id: 'keep', label: 'Keep it running', primary: true, run: vi.fn() },
      { id: 'confirm-close', label: 'Close game', danger: true, run: vi.fn() },
    ]
    const r = render(createElement(sessions.Menu, {
      session: SESSION, sessions: [SESSION], index: 0, confirming: true,
      busy: false, actions, actionIdx: 1, title: (s: typeof SESSION) => s.gameKey,
    }))
    const marked = r.container.querySelector('[data-active="true"]')
    expect(marked?.textContent).toContain('Close game')
    expect(marked?.className).toContain('session-danger')
  })
})
