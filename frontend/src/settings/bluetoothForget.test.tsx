/**
 * Settings → Bluetooth: Forget, on a paired device.
 *
 * The page could pair, connect and disconnect, and had no way to dissociate a
 * device — the backend route existed and nothing on screen called it. What is
 * held here is what a player meets with a pad in hand:
 *
 *   · → from a paired row reaches its Forget button, a second → still crosses
 *     to Nearby, and ← walks back one step at a time;
 *   · Forget takes two presses, and moving away in between disarms it;
 *   · the second press reaches the adapter, and the list is read back from it.
 *
 * No device is touched: every endpoint is answered by the stub below.
 */
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { buildSdk } from '../lib/themeSdk'

// Variable paths: `npm run build` typechecks this file and these are plain .js
// modules with no declarations.
const BT = './bluetooth.js'
const SLOW = './slow.js'
const { createBluetoothPage } = await import(/* @vite-ignore */ BT)
const { createUseSlow } = await import(/* @vite-ignore */ SLOW)

const PAD = { mac: 'E4:17:D8:2A:9C:03', name: 'DualSense Wireless Controller', connected: true, paired: true }
const NEAR = { mac: '7C:ED:8D:12:04:B1', name: '8BitDo Pro 2', connected: false, paired: false }
let paired = [PAD]
let near = [NEAR]
let calls: { method: string, url: string }[] = []

beforeEach(() => {
  paired = [PAD]
  near = [NEAR]
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method || 'GET'
    calls.push({ method, url })
    let body: unknown = {}
    if (method === 'DELETE') { paired = []; body = { ok: true, message: 'Forgotten — pair it again to reconnect' } }
    else if (url.endsWith('/bluetooth/devices')) body = paired
    else if (url.endsWith('/bluetooth/scan')) body = { ok: true, seconds: 10, found: near }
    else body = { ok: true }
    return { ok: true, status: 200, statusText: 'OK', json: async () => body }
  }))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const press = async (name: string) => {
  await act(async () => { window.dispatchEvent(new CustomEvent(`gp:${name}`)) })
}

async function page() {
  const sdk = buildSdk('shelf', { selectTheme: vi.fn(async () => {}) })
  const Page = createBluetoothPage(sdk, createUseSlow(sdk))
  const onLeave = vi.fn()
  const r = render(createElement(Page, { active: true, onLeave, seed: paired }))
  await waitFor(() => expect(r.container.querySelector('.gcs-bt-forget')).toBeTruthy())
  await waitFor(() => expect(r.container.textContent).toContain('8BitDo Pro 2'))
  return { ...r, onLeave }
}

const forgetBtn = (c: HTMLElement) => c.querySelector('.gcs-bt-forget') as HTMLElement

describe('Forget, on a paired device', () => {
  it('sits between the row and Nearby, and ← walks back one step at a time', async () => {
    const { container, onLeave } = await page()
    await press('dpad-right')
    expect(forgetBtn(container).getAttribute('data-on')).toBe('1')
    await press('dpad-right')                              // on to Nearby
    expect(container.querySelector('.gcs-bt-row[data-on="1"]')?.textContent).toContain('8BitDo Pro 2')
    await press('dpad-left'); await press('dpad-right')    // Paired row → its Forget
    expect(forgetBtn(container).getAttribute('data-on')).toBe('1')
    await press('dpad-left')                               // back onto the row, not the rail
    expect(onLeave).not.toHaveBeenCalled()
    expect(container.querySelector('.gcs-bt-row[data-on="1"]')?.textContent).toContain(PAD.name)
  })

  it('takes two presses, and moving away in between disarms it', async () => {
    const { container } = await page()
    await press('dpad-right'); await press('confirm')
    expect(forgetBtn(container).textContent).toContain('Press again to forget')
    expect(calls.some(c => c.method === 'DELETE')).toBe(false)

    await press('dpad-left')
    expect(forgetBtn(container).textContent?.trim()).toBe('Forget')
    await press('dpad-right'); await press('confirm')
    expect(calls.some(c => c.method === 'DELETE')).toBe(false)
  })

  it('removes the pairing on the adapter on the second press, then reads the list back', async () => {
    const { container } = await page()
    await press('dpad-right'); await press('confirm'); await press('confirm')

    await waitFor(() => expect(calls.some(c => c.method === 'DELETE')).toBe(true))
    expect(calls.find(c => c.method === 'DELETE')!.url)
      .toContain(`/settings/bluetooth/devices/${encodeURIComponent(PAD.mac)}`)
    await waitFor(() => expect(container.textContent).toContain('forgotten. Pair it again to reconnect'))
    await waitFor(() => expect(container.textContent).toContain('Nothing is paired yet.'))
  })

  it('arms from a click too, and does not connect or disconnect the device', async () => {
    const { container } = await page()
    await act(async () => { forgetBtn(container).click() })
    expect(forgetBtn(container).textContent).toContain('Press again to forget')
    await act(async () => { forgetBtn(container).click() })
    await waitFor(() => expect(calls.some(c => c.method === 'DELETE')).toBe(true))
    expect(calls.some(c => c.url.endsWith('/bluetooth/disconnect'))).toBe(false)
  })
})

describe('the lists follow the pad', () => {
  it('scrolls the Nearby column to the row under the cursor, and back to its top', async () => {
    // The column scrolls on its own; nothing followed the cursor before, so a
    // pad could walk it off the bottom of the screen.
    near = [NEAR,
      { mac: '7C:ED:8D:12:04:B2', name: 'Second pad', connected: false, paired: false },
      { mac: '7C:ED:8D:12:04:B3', name: 'Third pad', connected: false, paired: false }]
    const seen: string[] = []
    const proto = Element.prototype as unknown as { scrollIntoView?: unknown }
    const had = proto.scrollIntoView
    proto.scrollIntoView = function (this: Element) { seen.push(this.textContent || '') }
    try {
      const { container } = await page()
      await press('dpad-right'); await press('dpad-right')   // Forget → Nearby
      await press('dpad-down'); await press('dpad-down')
      expect(seen[seen.length - 1]).toContain('Third pad')

      const list = container.querySelector('.gcs-bt-col[data-col="nearby"] .gcs-bt-list') as HTMLElement
      Object.defineProperty(list, 'scrollHeight', { value: 900 })
      Object.defineProperty(list, 'clientHeight', { value: 300 })
      list.scrollTop = 250
      await press('dpad-up'); await press('dpad-up')         // back on the first
      expect(list.scrollTop).toBe(0)
    } finally {
      proto.scrollIntoView = had
    }
  })
})
