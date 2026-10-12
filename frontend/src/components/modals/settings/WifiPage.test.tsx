/**
 * The default UI's Wi-Fi radio switch. The themed page has its own test
 * (settings/wifiRadio.test.tsx); this one is the built-in screen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { WifiPage } from './WifiPage'

const box = { radio: true as boolean, wired: false }
const networks = vi.fn()
const setRadio = vi.fn()

vi.mock('../../../api', () => ({
  api: {
    wifi: {
      status: async () => ({ connected: box.radio, ssid: 'Home', ip: '10.0.0.2', iface: 'wlan0',
        radio: box.radio, ethernet: { connected: box.wired, iface: '', ip: '' } }),
      networks: async () => { networks(); return [{ ssid: 'Home', signal: 80, secured: true, connected: true }] },
      setRadio: async (enabled: boolean) => { setRadio(enabled); box.radio = enabled; return { enabled } },
    },
  },
}))
vi.mock('../../../hooks/useGamepad', () => ({ onGp: () => () => {} }))
vi.mock('./useSubPageGamepad', () => ({ useSubPageGamepad: () => {} }))

beforeEach(() => { box.radio = true; box.wired = false; networks.mockReset(); setRadio.mockReset() })
afterEach(() => { cleanup() })

const draw = () => render(<WifiPage onClose={() => {}} onBack={() => {}} />)

describe('default UI Wi-Fi radio switch', () => {
  it('asks twice before going offline, then hides the list', async () => {
    draw()
    await waitFor(() => expect(screen.getByText('Turning it off takes this box offline.')).toBeTruthy())
    fireEvent.click(screen.getByRole('switch'))
    expect(screen.getByText('Press again to turn Wi-Fi off')).toBeTruthy()
    expect(setRadio).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('switch'))
    await waitFor(() => expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false'))
    expect(setRadio).toHaveBeenCalledWith(false)
    expect(screen.getByText(/Wi-Fi is off\./)).toBeTruthy()
    expect(screen.queryByText('Scanning…')).toBeNull()
  })

  it('does not scan while off, and turns on in one press', async () => {
    box.radio = false
    draw()
    await waitFor(() => expect(screen.getByText(/Wi-Fi is off\./)).toBeTruthy())
    expect(networks).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('switch'))
    await waitFor(() => expect(setRadio).toHaveBeenCalledWith(true))
    await waitFor(() => expect(networks).toHaveBeenCalled())
  })
})
