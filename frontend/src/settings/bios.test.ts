/** The BIOS page's rules: installed consoles only, the broken ones first, and
 * a verdict short enough for one row. */
import { describe, expect, it } from 'vitest'
import { biosRows, biosSummary, fileVerdict, systemVerdict } from '../settings/bios'

const sys = (id: string, status: string, installed = true, files: object[] = []) =>
  ({ id, label: id, status, installed, files })

describe('the BIOS page', () => {
  it('keeps installed consoles only, the ones needing a file first', () => {
    const rows = biosRows([sys('wii u', 'ok'), sys('ps2', 'absent'), sys('xbox', 'absent', false), sys('ps3', 'mismatch')])
    expect(rows.map((r: { id: string }) => r.id)).toEqual(['ps2', 'ps3', 'wii u'])
    expect(biosSummary([sys('a', 'ok'), sys('b', 'absent'), sys('c', 'absent', false)])).toBe('1/2 ready')
    expect(biosRows({ detail: 'nope' } as never)).toEqual([])
  })

  it('says how many required files are missing, and ignores optional ones', () => {
    const missing = (required: boolean) => ({ required, status: 'absent' })
    expect(systemVerdict(sys('a', 'absent', true, [missing(true)]))).toBe('File missing')
    expect(systemVerdict(sys('a', 'absent', true, [missing(true), missing(true), missing(false)]))).toBe('2 files missing')
    expect(systemVerdict(sys('a', 'mismatch'))).toBe('Wrong file')
    expect(systemVerdict(sys('a', 'ok', true, [missing(false)]))).toBe('Ready')
  })

  it('tells a missing file from an optional one and a checked one', () => {
    expect(fileVerdict({ status: 'absent', required: true })).toEqual({ tone: 'bad', text: 'Missing' })
    expect(fileVerdict({ status: 'absent', required: false })).toEqual({ tone: 'quiet', text: 'Optional' })
    expect(fileVerdict({ status: 'ok', verified: true }).text).toBe('Present, MD5 checked')
    expect(fileVerdict({ status: 'mismatch' }).tone).toBe('bad')
  })
})
