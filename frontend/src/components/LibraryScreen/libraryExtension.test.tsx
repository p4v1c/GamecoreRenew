/**
 * The extension under each title. A pack with `roms.showExtension: false`
 * (the PC system's `.lutris` stubs) gets `ext: ""` from the backend, and the
 * default and Summer libraries then print nothing rather than an empty badge.
 */
import { render, act, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { createElement } from 'react'
import { buildSdk } from '../../lib/themeSdk'
import { useStore } from '../../store'
import LibraryScreen from './index'

const SUMMER = '../../../../config/themes/summer'

const GAMES: Record<string, unknown[]> = {
  lutris: [{ filename: 'Celeste.lutris', display_name: 'Celeste', path: '/t/Celeste.lutris', size: 40, ext: '' }],
  snes9x: [{ filename: 'Mario.sfc', display_name: 'Mario', path: '/t/Mario.sfc', size: 40, ext: 'SFC' }],
}
const SYSTEMS = [
  { id: 'lutris', label: 'PC', kind: 'emulator' as const },
  { id: 'snes9x', label: 'Super Nintendo', kind: 'emulator' as const },
]

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(typeof input === 'string' ? input : (input as Request).url ?? input)
    const games = url.match(/\/systems\/(\w+)\/games$/)
    const one = url.match(/\/systems\/(\w+)$/)
    const body: unknown =
      url.endsWith('/systems') ? SYSTEMS
        : games ? GAMES[games[1]] ?? []
          : one ? SYSTEMS.find(s => s.id === one[1])
            : url.includes('/metadata') ? { found: false }
              : url.includes('/media') ? { media: {} }
                : url.includes('/settings') ? {}
                  : []
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
})

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

const open = (systemId: string) =>
  act(() => { useStore.setState({ screen: 'library', selectedSystemId: systemId, selectedGameIdx: 0 }) })

describe('the default library', () => {
  it('prints the extension of a dump', async () => {
    open('snes9x')
    const { container } = render(<LibraryScreen />)
    await waitFor(() => expect(container.textContent).toContain('Mario'))
    expect(container.textContent).toContain('SFC')
  })

  it('prints nothing for a launcher entry', async () => {
    open('lutris')
    const { container } = render(<LibraryScreen />)
    await waitFor(() => expect(container.textContent).toContain('Celeste'))
    expect(container.textContent).not.toMatch(/LUTRIS/i)
  })
})

describe('Summer', () => {
  async function view() {
    const { createLibraryView } = await import(/* @vite-ignore */ `${SUMMER}/views/library.js`)
    return createLibraryView(buildSdk('summer', { selectTheme: vi.fn(async () => {}) }))
  }

  it('has no extension line or chip for a launcher entry, and keeps them for a dump', async () => {
    const libraryView = await view()
    open('lutris')
    const pc = render(createElement(LibraryScreen as React.ComponentType<{ view: unknown }>, { view: libraryView }))
    await waitFor(() => expect(pc.container.querySelector('.sm-lib-row')).toBeTruthy())
    expect(pc.container.querySelector('.sm-lib-row-main i')).toBeNull()
    expect(pc.container.querySelector('.sm-lib-chip')).toBeNull()
    cleanup()

    open('snes9x')
    const snes = render(createElement(LibraryScreen as React.ComponentType<{ view: unknown }>, { view: libraryView }))
    await waitFor(() => expect(snes.container.querySelector('.sm-lib-row-main i')?.textContent).toBe('SFC'))
  })
})
