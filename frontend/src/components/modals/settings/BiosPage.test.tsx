/**
 * The BIOS screen, on the three states it exists to tell apart.
 *
 * The screen replaces an emulator that refused to start with no message. If it
 * shows the same red for a missing file and for a file that is simply the
 * wrong dump, it has replaced one unhelpful answer with another — and if it
 * shows red for an optional regional firmware, it manufactures the tickets it
 * was built to remove.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { BiosPage } from './BiosPage'
import type { BiosSystem, BiosFile } from '../../../api'

const listed = vi.fn()

vi.mock('../../../api', () => ({ api: { bios: { list: () => listed() } } }))
vi.mock('../../../hooks/useGamepad', () => ({ onGp: () => () => {} }))

function file(over: Partial<BiosFile> = {}): BiosFile {
  return {
    file: 'boot.bin', path: '/home/box/sys/boot.bin', required: true,
    note: 'the boot rom', status: 'ok', verified: true,
    expected_md5: '0'.repeat(32), ...over,
  }
}

function system(over: Partial<BiosSystem> = {}): BiosSystem {
  return {
    id: 'testpack', label: 'Test System', platform: 'TEST', color: '#123456',
    dir: '/home/box/sys', status: 'ok', installed: true,
    files: [file()], ...over,
  }
}

beforeEach(() => { listed.mockReset() })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const draw = async (rows: BiosSystem[]) => {
  listed.mockResolvedValue(rows)
  render(<BiosPage onClose={() => {}} onBack={() => {}} />)
  await waitFor(() => expect(screen.getByText('Test System')).toBeTruthy())
}

describe('the BIOS screen', () => {
  it('names the file and the directory when one is missing', async () => {
    // The whole point. "Copy a BIOS" is the sentence that produced the support
    // thread; the destination read off the screen is what ends it.
    await draw([system({
      status: 'absent',
      files: [file({ status: 'absent', verified: false })],
    })])

    expect(screen.getByText('boot.bin')).toBeTruthy()
    expect(screen.getByText('/home/box/sys')).toBeTruthy()
    expect(screen.getByText('missing')).toBeTruthy()
  })

  it('does not call a wrong dump missing', async () => {
    await draw([system({
      status: 'mismatch',
      files: [file({ status: 'mismatch', actual_md5: 'f'.repeat(32) })],
    })])

    expect(screen.getByText('wrong md5')).toBeTruthy()
    expect(screen.queryByText('missing')).toBeNull()
    // The hash they actually have, so nobody has to be walked through md5sum
    // over SSH to find out which dump it is.
    expect(screen.getByText(/found f{32}/)).toBeTruthy()
  })

  it('says whether a present file was really checked', async () => {
    // `verified` exists because RPCS3 firmware and Switch keys carry no md5 on
    // purpose. Announcing "conforming" about a file nothing compared would be
    // the screen inventing a guarantee.
    await draw([system({ files: [file({ verified: false })] })])
    expect(screen.getByText('present')).toBeTruthy()
    expect(screen.queryByText('present · md5 checked')).toBeNull()
  })

  it('does not report a working box as broken over an optional file', async () => {
    // A regional firmware nobody has is not a fault. The line still appears —
    // that is how the owner learns it exists — but the system stays ready and
    // the summary counts nothing.
    await draw([system({
      status: 'ok',
      files: [file({ required: false, status: 'absent', verified: false })],
    })])

    expect(screen.getByText('ready')).toBeTruthy()
    expect(screen.getByText('optional · not present')).toBeTruthy()
    expect(screen.getByText(/Every system file this box needs is in place/)).toBeTruthy()
  })

  it('counts only the systems that are actually on the box', async () => {
    // A system the owner has not added yet is listed so they can see what it
    // will need — but counting it as broken would make a working box read as
    // five faults on first boot.
    await draw([
      system({ installed: false, status: 'absent',
               files: [file({ status: 'absent', verified: false })] }),
    ])

    expect(screen.getByText('not installed')).toBeTruthy()
    expect(screen.getByText(/Every system file this box needs is in place/)).toBeTruthy()
  })

  it('never puts a download link on screen', async () => {
    // The legal line of the project. It is far too easy to break with a
    // well-meaning "helpful" addition, so it is held by a test on both sides.
    await draw([system({
      status: 'absent', files: [file({ status: 'absent', verified: false })],
    })])

    expect(document.body.innerHTML).not.toMatch(/https?:\/\/|www\./i)
  })
})
