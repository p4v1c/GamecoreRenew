/**
 * The autoconfig switch on the shared Controllers page.
 *
 * Two things are being pinned, and both are about what somebody can SEE:
 *
 *   1. It is on the shared page, so Shelf, Summer and the built-in default all
 *      get it. A switch that lived in one theme would disappear when the theme
 *      changed while the setting stayed in force — a box with no autoconfig and
 *      no surviving way to turn it back on.
 *   2. Off is visible, and both directions warn before they fire. Neither has
 *      an undo: off empties the controller setup GameCore wrote, on replaces
 *      whatever the owner made by hand.
 *
 * What is NOT tested here, and cannot be: whether the wording reads clearly on
 * a television from three metres. That one is the owner's to check.
 */
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { buildSdk } from '../lib/themeSdk'
// `../settings/...`, not `./...`: see index.d.ts — the ambient declarations
// match on the specifier, and it has to carry the directory name.
import { createControllersPage } from '../settings/controllers'
import { createRows } from '../settings/rows'

const PACKS = [
  { id: 'dolphin', label: 'GameCube / Wii', enabled: true, effective: true },
  { id: 'rpcs3', label: 'PlayStation 3', enabled: true, effective: true },
]

/** The backend, with the switch in a given position. */
const backend = (enabled: boolean, packs = PACKS, extra: object = {}) => {
  const posts: { body: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes('/controllers/autoconfig')) {
      if (init?.method === 'POST') {
        posts.push({ body: JSON.parse(String(init.body)) })
        const body = JSON.parse(String(init.body))
        return {
          ok: true, status: 200, statusText: 'OK',
          json: async () => ({
            ok: true, enabled: body.pack ? enabled : body.enabled,
            packs, ...extra,
          }),
        }
      }
      return {
        ok: true, status: 200, statusText: 'OK',
        json: async () => ({ ok: true, enabled, packs }),
      }
    }
    return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) }
  }))
  return posts
}

const page = () => {
  const sdk = buildSdk('', { selectTheme: vi.fn(async () => {}) })
  const Page = createControllersPage(sdk, createRows(sdk))
  return render(<Page active={false} onLeave={() => {}} />)
}

beforeEach(() => {
  // Explicit: this project does not run vitest with `globals: true`, so the
  // auto-cleanup testing-library installs from its global hooks never fires and
  // every render stacks in the same document. The symptom is "found multiple
  // elements", one per earlier test, which reads like a duplicated row.
  cleanup()
  // One pad, so the "connected but not configured" warning has something to be
  // about. The page reads the Gamepad API directly — `sysinfo.controllers` is
  // a sysfs battery scan that cannot see a wired pad.
  vi.stubGlobal('navigator', { ...navigator, getGamepads: () => [{ index: 0, id: 'PS4 Controller' }] })
})

describe('the switch itself', () => {
  it('is on the shared page, so every theme gets it without changing', async () => {
    backend(true)
    page()
    // The label says what it DOES. "Autoconfig" alone means nothing to somebody
    // opening this screen for the first time.
    expect(await screen.findByText('Set up controllers automatically')).toBeTruthy()
  })

  it('says so on the heading when it is off, not only on its own row', async () => {
    backend(false)
    page()
    // The failure this feature had to be designed around: somebody turns it off
    // to fiddle, forgets, and three weeks later a new pad does nothing. The
    // heading is what a person chasing a dead controller actually reads.
    expect(await screen.findByText('AUTO SETUP OFF')).toBeTruthy()
    expect(await screen.findByText(/not configured in any emulator/)).toBeTruthy()
  })

  it('says nothing alarming while the answer is still in flight', () => {
    backend(false)
    page()
    // Before the backend replies the switch is neither on nor off. Assuming OFF
    // would flash a warning at every player on every visit.
    expect(screen.queryByText('AUTO SETUP OFF')).toBeNull()
  })
})

describe('the two destructive directions', () => {
  it('warns what will be lost before turning it off', async () => {
    const posts = backend(true)
    page()
    const row = (await screen.findByText('Set up controllers automatically')).closest('.gcs-row2')!

    fireEvent.click(row)
    // Armed, not fired: the first press has to say what the second one costs.
    expect(posts).toHaveLength(0)
    expect(screen.getByText(/this clears the controller setup GameCore wrote/)).toBeTruthy()

    fireEvent.click(screen.getByText(/this clears the controller setup GameCore wrote/).closest('.gcs-row2')!)
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).toEqual({ enabled: false })
  })

  it('warns that turning it back on replaces what the owner made', async () => {
    const posts = backend(false)
    page()
    const row = (await screen.findByText('Set up controllers automatically')).closest('.gcs-row2')!

    fireEvent.click(row)
    expect(posts).toHaveLength(0)
    // The opposite loss, so the opposite sentence. One `confirm` flag with a
    // fixed message would have warned about clearing a setup while it was about
    // to overwrite one.
    expect(screen.getByText(/this replaces the controller setup you made yourself/)).toBeTruthy()
  })

  it('reports what was actually emptied, by name', async () => {
    backend(true, PACKS, { released: ['dolphin: GCPad1 unbound'] })
    page()
    const row = (await screen.findByText('Set up controllers automatically')).closest('.gcs-row2')!
    fireEvent.click(row)
    fireEvent.click(row)
    // "10 released" is not something anyone can check.
    expect(await screen.findByText(/dolphin: GCPad1 unbound/)).toBeTruthy()
  })
})

describe('the per-emulator exception', () => {
  it('is not on the way to anything — it has to be opened', async () => {
    backend(true)
    page()
    await screen.findByText('Set up controllers automatically')
    expect(screen.queryByText('GameCube / Wii')).toBeNull()

    fireEvent.click(screen.getByText('Per-emulator exceptions').closest('.gcs-row2')!)
    expect(await screen.findByText('GameCube / Wii')).toBeTruthy()
  })

  it('shows no switch it cannot honour while the global one is off', async () => {
    backend(false)
    page()
    await screen.findByText('Set up controllers automatically')
    fireEvent.click((await screen.findByText('Per-emulator exceptions')).closest('.gcs-row2')!)

    // Present, so nobody wonders where their exceptions went — but a reading,
    // not a control. The global switch wins, and a row that moves and changes
    // nothing on the box is a setting that governs nothing.
    const row = (await screen.findByText('GameCube / Wii')).closest('.gcs-row2')!
    expect(row.querySelector('.gcs-tgl')).toBeNull()
    expect(row.textContent).toContain('turn the switch above back on first')
    // A reading, and it says what it reads.
    expect(row.querySelector('.gcs-row2-info')?.textContent).toBe('Off')
  })

  it('addresses one emulator, and says which one it cleared', async () => {
    const posts = backend(true, PACKS, { released: ['dolphin: GCPad1 unbound'] })
    page()
    await screen.findByText('Set up controllers automatically')
    fireEvent.click((await screen.findByText('Per-emulator exceptions')).closest('.gcs-row2')!)

    const row = (await screen.findByText('GameCube / Wii')).closest('.gcs-row2')!
    fireEvent.click(row)
    expect(posts).toHaveLength(0)          // armed first, like the global one
    fireEvent.click(row)

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).toEqual({ enabled: false, pack: 'dolphin' })
    // Named, because "set your pads up inside each emulator now" is wrong when
    // only one of them was handed back.
    expect(await screen.findByText(/inside GameCube \/ Wii now/)).toBeTruthy()
  })

  it('names the emulators taken over by hand without opening the list', async () => {
    backend(true, [
      { id: 'dolphin', label: 'GameCube / Wii', enabled: false, effective: false },
      { id: 'rpcs3', label: 'PlayStation 3', enabled: true, effective: true },
    ])
    page()
    // Named rather than counted: "1 exception" says there is something to find
    // without saying where, and finding out means opening a list the owner may
    // not know exists.
    expect(await screen.findByText('GameCube / Wii')).toBeTruthy()
    expect(await screen.findByText(/GameCore does not touch them/)).toBeTruthy()
  })
})
