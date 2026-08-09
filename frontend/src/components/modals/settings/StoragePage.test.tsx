/**
 * The storage screen, on what it has to tell apart.
 *
 * Eject is the reason it exists: pulling a disk with unwritten data is how a
 * save is lost, and "has it finished writing" is not a question anyone can
 * answer by looking at it. The rest of the screen is there so the owner knows
 * which path to point a system at, and which disks are safe to keep saves on.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { StoragePage } from './StoragePage'
import type { StorageVolume } from '../../../api'

const listed = vi.fn()
const unmounted = vi.fn()

vi.mock('../../../api', () => ({
  api: {
    storage: {
      list: () => listed(),
      unmount: (device: string) => unmounted(device),
    },
  },
}))
vi.mock('../../../hooks/useGamepad', () => ({ onGp: () => () => {} }))
vi.mock('./useSubPageGamepad', () => ({ useSubPageGamepad: () => {} }))

function volume(over: Partial<StorageVolume> = {}): StorageVolume {
  return {
    name: 'sdb1', device: '/dev/sdb1', label: 'ROMS', uuid: 'A4E2',
    fstype: 'ext4', size: '1T', mountpoint: '/run/media/gc/ROMS',
    mounted: true, slug: 'roms', stable_path: '/userdata/volumes/roms',
    keeps_permissions: true, saves_warning: '', ...over,
  }
}

beforeEach(() => { listed.mockReset(); unmounted.mockReset() })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const draw = async (volumes: StorageVolume[]) => {
  listed.mockResolvedValue({ ok: true, volumes })
  render(<StoragePage onClose={() => {}} onBack={() => {}} />)
  if (volumes.length) {
    await waitFor(() => expect(screen.getByText(volumes[0].label)).toBeTruthy())
  }
}

describe('the storage screen', () => {
  it('shows the stable path, never the mount point', async () => {
    /* udisks names the second mount of the same disk "ROMS 1". A library
       recorded against the real mount point scans nothing the day someone
       replugs it — so the path offered here has to be the durable one. */
    await draw([volume()])
    expect(screen.getByText('/userdata/volumes/roms')).toBeTruthy()
    expect(screen.queryByText('/run/media/gc/ROMS')).toBeNull()
  })

  it('offers Eject for a mounted disk', async () => {
    await draw([volume()])
    expect(screen.getByText('Eject safely')).toBeTruthy()
  })

  it('does not offer Eject for a disk that is not mounted', async () => {
    await draw([volume({ mounted: false })])
    expect(screen.queryByText('Eject safely')).toBeNull()
  })

  it('ejects the disk the row belongs to, by device path', async () => {
    /* A row number is not a handle: a disk arriving while the screen is open
       renumbers the list, and Eject would then detach the wrong disk. */
    unmounted.mockResolvedValue({ ok: true, detail: '' })
    await draw([volume({ device: '/dev/sda1', label: 'A' }),
                volume({ device: '/dev/sdb1', label: 'B' })])
    fireEvent.click(screen.getAllByText('Eject safely')[1])
    await waitFor(() => expect(unmounted).toHaveBeenCalledWith('/dev/sdb1'))
  })

  it('repeats udisks own words when a disk is busy', async () => {
    /* "target is busy" is actionable — a game is still reading it. A generic
       "could not eject" is the dead end this screen exists to remove. */
    unmounted.mockRejectedValue(new Error('Error unmounting: target is busy'))
    await draw([volume()])
    fireEvent.click(screen.getByText('Eject safely'))
    await waitFor(() => expect(screen.getByText(/target is busy/)).toBeTruthy())
  })

  it('warns about saves on a disk with no POSIX permissions', async () => {
    await draw([volume({
      fstype: 'exfat', keeps_permissions: false,
      saves_warning: 'This disk has no POSIX permissions. Keep saves on the internal disk.',
    })])
    expect(screen.getByText(/no POSIX permissions/)).toBeTruthy()
  })

  it('says nothing about saves on an ordinary filesystem', async () => {
    /* A warning on a disk with nothing wrong with it is how the owner learns
       to ignore warnings. */
    await draw([volume()])
    expect(screen.queryByText(/POSIX/)).toBeNull()
  })

  it('tells the owner what to do when no disk is attached', async () => {
    await draw([])
    await waitFor(() => expect(screen.getByText(/No external disk is attached/)).toBeTruthy())
  })
})
