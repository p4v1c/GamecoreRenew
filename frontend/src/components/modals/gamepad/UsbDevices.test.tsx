/**
 * The peripherals list on the controller screen.
 *
 * The player slots above it answer "who is player 2". They cannot answer "is
 * the GameCube adapter plugged in": Dolphin drives that adapter over raw
 * libusb, so it has no evdev node and never enters the roster. Without this
 * list, an adapter that is unplugged and one the sandbox cannot see look
 * identical from a sofa — and only one of them is fixed by touching the cable.
 *
 * The three states it has to tell apart are the ones tested here: present,
 * absent, and "no system on this box declares any", which must draw nothing.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import DefaultGamepadView from './DefaultGamepadView'
import type { UsbDevice } from '../../../api'

afterEach(cleanup)

function device(over: Partial<UsbDevice> = {}): UsbDevice {
  return {
    system_id: 'gc', system_label: 'GameCube', vid_pid: '057e:0337',
    class: 'adapter', label: 'GameCube adapter',
    note: 'Check the switch is on Wii U.',
    detected_as: '', status: 'absent', ...over,
  }
}

const draw = (usbDevices: UsbDevice[]) => render(
  <DefaultGamepadView
    layout="generic"
    name="Test pad"
    layoutLabel="Standard layout"
    connected
    controllers={[]}
    usbDevices={usbDevices}
    glyphs={{ top: '△', right: '○', bottom: '✕', left: '□', lb: 'L1', rb: 'R1', menu: 'Options', power: 'Share' }}
    mappings={[]}
    onClose={() => {}}
    Art={() => <div />}
    Battery={() => <div />}
  />,
)

describe('the peripherals list', () => {
  it('names a declared device that is not plugged in, and what to check', () => {
    draw([device()])
    expect(screen.getByText('Not detected')).toBeTruthy()
    // The pack's own words, not a generic "device not found" — the note is the
    // only part of the row the owner can act on.
    expect(screen.getByText('Check the switch is on Wii U.')).toBeTruthy()
  })

  it('marks a device that is on the bus as detected', () => {
    draw([device({ status: 'present', detected_as: 'GC Adapter' })])
    expect(screen.getByText('Detected')).toBeTruthy()
  })

  it('does not repeat the note for a device that is here', () => {
    /* There is nothing to check when it works. A row that carried its
       troubleshooting line at all times would read as a warning on a box with
       nothing wrong with it. */
    draw([device({ status: 'present', detected_as: 'GC Adapter' })])
    expect(screen.queryByText('Check the switch is on Wii U.')).toBeNull()
  })

  it('draws nothing at all when no system declares a peripheral', () => {
    /* The common case. An empty "PERIPHERALS" heading is a question the owner
       did not ask, on the screen they reached because something was wrong. */
    draw([])
    expect(screen.queryByText('PERIPHERALS')).toBeNull()
  })

  it('still lists a device whose class this release does not know', () => {
    /* A pack from a newer catalogue, or one the operator wrote. The device and
       its note are the point of the row; an unrecognised class word must not
       cost the owner the line. */
    draw([device({ class: 'dancemat' })])
    expect(screen.getByText('Check the switch is on Wii U.')).toBeTruthy()
    expect(screen.getByText(/Peripheral/)).toBeTruthy()
  })

  it('says which system wants the device', () => {
    /* "An adapter is missing" is not actionable on a box with thirteen
       systems; "Dolphin wants it" is.

       The system label here is deliberately nothing like the device label:
       asserting on a string both of them contain would pass without the row
       ever naming the system. */
    draw([device({ system_label: 'Nintendo Wii' })])
    expect(screen.getByText(/Nintendo Wii/)).toBeTruthy()
  })
})
