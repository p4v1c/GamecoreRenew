import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { api, type BiosSystem, type BiosFile } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'

/**
 * Settings → BIOS: what this box still needs, and exactly where to put it.
 *
 * This is the number one support ticket and it used to have no screen at all.
 * A missing or corrupt system file produces nothing a player can act on — the
 * emulator refuses to start, or starts on a black screen — so every case cost
 * three round trips before anyone knew which file was being talked about.
 *
 * Three things this screen has to get right:
 *
 *  · **Absent and wrong-md5 are not the same row.** They are different fixes.
 *    "Copy this file" is the wrong answer to a file that is already there.
 *
 *  · **The path, not just the name.** "Copy a BIOS" is the sentence that
 *    produced the support thread. The destination is printed in full,
 *    resolved on THIS box, so it can be read off the screen into an scp.
 *
 *  · **Optional is not a fault.** Regional firmwares and per-title keys are
 *    absent on working installations. They are listed in amber and never
 *    change the system's own verdict — red on a box that works is how a
 *    screen built to remove tickets starts generating them.
 *
 * No link to a BIOS, a firmware or a key appears here, ever. That is the legal
 * line of the project, and `backend/tests/test_bios.py` holds it.
 */

const ACCENT = 'var(--gc-accent, #7c3aed)'
const GOOD = '#4ade80'
const BAD = '#f87171'
const WARN = '#fbbf24'

/** Colour and words for one file's line — required decides the severity. */
function fileTone(f: BiosFile): { colour: string; text: string } {
  if (f.status === 'ok') {
    return { colour: GOOD, text: f.verified ? 'present · md5 checked' : 'present' }
  }
  if (f.status === 'mismatch') {
    return { colour: f.required ? BAD : WARN, text: 'wrong md5' }
  }
  return { colour: f.required ? BAD : WARN, text: f.required ? 'missing' : 'optional · not present' }
}

function systemTone(s: BiosSystem): { colour: string; text: string } {
  if (!s.installed) return { colour: 'rgba(255,255,255,0.3)', text: 'not installed' }
  if (s.status === 'absent') return { colour: BAD, text: 'file missing' }
  if (s.status === 'mismatch') return { colour: BAD, text: 'file does not match' }
  return { colour: GOOD, text: 'ready' }
}

export function BiosPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [rows, setRows] = useState<BiosSystem[]>([])
  const [error, setError] = useState(false)
  const [focus, setFocus] = useState(0)
  const refs = useRef<(HTMLDivElement | null)[]>([])
  const count = useRef(0)
  useEffect(() => { count.current = rows.length }, [rows])

  useEffect(() => {
    api.bios.list().then(setRows).catch(() => setError(true))
  }, [])

  useSubPageGamepad(onBack, onClose)

  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => setFocus(i => Math.max(0, i - 1))),
      onGp('gp:dpad-down', () => setFocus(i => Math.min(Math.max(0, count.current - 1), i + 1))),
    ]
    return () => offs.forEach(o => o())
  }, [])

  // The list is longer than a television screen, and a highlight the scroll
  // container knows nothing about is a cursor steered off-screen.
  useEffect(() => {
    refs.current[focus]?.scrollIntoView({ block: 'nearest' })
  }, [focus])

  const broken = rows.filter(s => s.installed && s.status !== 'ok')

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="BIOS & SYSTEM FILES" onBack={onBack} />

      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginBottom: 14, lineHeight: 1.5 }}>
        {error
          ? 'Could not read the BIOS status.'
          : broken.length === 0
            ? 'Every system file this box needs is in place. Copy files over SSH or from Desktop Mode; nothing is downloaded here.'
            : `${broken.length} system${broken.length > 1 ? 's need' : ' needs'} a file. Copy it to the path shown and start the game again.`}
      </div>

      {rows.map((s, i) => {
        const tone = systemTone(s)
        return (
          <div
            key={s.id}
            ref={el => { refs.current[i] = el }}
            style={{
              padding: '14px 18px', borderRadius: 12, marginBottom: 10,
              opacity: s.installed ? 1 : 0.45,
              background: focus === i ? `color-mix(in srgb, ${ACCENT} 15%, transparent)` : 'rgba(255,255,255,0.04)',
              border: focus === i ? `1px solid color-mix(in srgb, ${ACCENT} 40%, transparent)` : '1px solid rgba(255,255,255,0.07)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ width: 9, height: 9, borderRadius: '50%', background: tone.colour, flexShrink: 0 }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#fff', flex: 1 }}>{s.label}</div>
              <div style={{ fontSize: 12, color: tone.colour, fontWeight: 600 }}>{tone.text}</div>
            </div>

            <div style={{
              fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 6,
              fontFamily: 'monospace', wordBreak: 'break-all',
            }}>
              {s.dir}
            </div>

            {s.files.map(f => {
              const ft = fileTone(f)
              return (
                <div key={f.file || '(any)'} style={{ marginTop: 8, paddingLeft: 21 }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                    <span style={{
                      fontSize: 13, fontFamily: 'monospace', color: '#fff', wordBreak: 'break-all',
                    }}>
                      {/* An emulator that scans its directory pins no name, and
                          the screen must not invent one — the pack's note is
                          what says which images that emulator accepts. */}
                      {f.file || 'any image in this directory'}
                    </span>
                    <span style={{ fontSize: 11, color: ft.colour, fontWeight: 600, whiteSpace: 'nowrap' }}>
                      {ft.text}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2, lineHeight: 1.4 }}>
                    {f.note}
                  </div>
                  {f.status === 'mismatch' && (
                    // The hash they have, so support does not have to ask them
                    // to run md5sum over SSH to learn which dump this is.
                    <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginTop: 3, fontFamily: 'monospace' }}>
                      expected {f.expected_md5} · found {f.actual_md5}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}

      {!error && rows.length === 0 && (
        <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.35)', textAlign: 'center', padding: 20 }}>
          No system on this box needs a BIOS file.
        </div>
      )}

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ↑↓ Scroll · ○ Back
      </div>
    </Overlay>
  )
}
