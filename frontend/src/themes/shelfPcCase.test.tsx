/**
 * Shelf's PC case: a PC game is drawn in the house template (blue band, white
 * plastic, printed reverse), never in a console's box and cartridge. No PC
 * pack ships yet; these pin what the theme does once one does.
 */
import React from 'react'
import { render, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import htm from 'htm'

const THEME = '../../../config/themes/shelf'

const ui = { html: htm.bind(React.createElement), React, useState: React.useState, useEffect: React.useEffect }
const sdk = {
  ui,
  api: { media: { url: (s: string, f: string, t: string) => `/api/media/${s}/${f}/media/${t}` } },
}

async function load() {
  vi.resetModules()
  const [pc, pcCase, cartridge] = await Promise.all([
    import(/* @vite-ignore */ `${THEME}/lib/pc.js`),
    import(/* @vite-ignore */ `${THEME}/views/pc-case.js`),
    import(/* @vite-ignore */ `${THEME}/views/cartridge.js`),
  ])
  return { ...pc, ...pcCase, ...cartridge }
}

const image = (...types: string[]) => Object.fromEntries(types.map(t => [t, { kind: 'image' }]))
const GAME = { filename: 'Hades.lutris', display_name: 'Hades' }

afterEach(() => { cleanup() })

describe('a PC game', () => {
  it('is a PC system by pack id, whatever the case', async () => {
    const { isPc } = await load()
    expect(isPc('lutris')).toBe(true)
    expect(isPc('LUTRIS')).toBe(true)
    expect(isPc('pcsx2')).toBe(false)
  })

  it('ships on a disc, not a cartridge', async () => {
    const { shellFor } = await load()
    expect(shellFor('.lutris', 'lutris')).toBe('disc')
  })
})

describe('the printed PC reverse', () => {
  it('sets the logo over the key art, the blurb, the shots and the spec panel', async () => {
    const { createPcCase } = await load()
    const { PcBack } = createPcCase(sdk)
    const meta = {
      description: 'Defy the god of the dead.', developer: 'Supergiant Games', year: '2020', genres: ['Action'],
      requirements: { os: 'Windows 7 SP1', ram: '4 GB' },
    }
    const media = image('clear-logo', 'fanart-background', 'screenshot-gameplay', 'screenshot-game-title')
    const { container } = render(React.createElement(PcBack, { systemId: 'lutris', game: GAME, meta, media }))

    expect(container.querySelector('.pc-logo')?.getAttribute('src')).toContain('/media/clear-logo')
    expect((container.querySelector('.pc-hero') as HTMLElement).style.backgroundImage).toContain('fanart-background')
    expect(container.querySelectorAll('.pc-shots img')).toHaveLength(2)
    expect(container.querySelector('.pc-blurb')?.textContent).toBe('Defy the god of the dead.')
    const rows = [...container.querySelectorAll('.pc-req dt')].map(n => n.textContent)
    expect(rows).toEqual(['OS', 'RAM'])
    expect(container.querySelector('.pc-credit')?.textContent).toContain('2020, Action')
  })

  it('never shows the key art twice, and prints the name when there is no logo', async () => {
    const { createPcCase } = await load()
    const { PcBack } = createPcCase(sdk)
    const { container } = render(React.createElement(PcBack, {
      systemId: 'lutris', game: GAME, meta: {}, media: image('screenshot-gameplay'),
    }))
    expect((container.querySelector('.pc-hero') as HTMLElement).style.backgroundImage).toContain('screenshot-gameplay')
    expect(container.querySelector('.pc-shots')).toBeNull()
    expect(container.querySelector('.pc-req')).toBeNull()
    expect(container.querySelector('.pc-logo-text')?.textContent).toBe('Hades')
  })
})
