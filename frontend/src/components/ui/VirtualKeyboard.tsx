import { useState, useEffect, useRef } from 'react'
import { onGp } from '../../hooks/useGamepad'
import { PadHints } from '../../lib/padKey'

// Two layers: letters and symbols. '?123' / 'abc' switches (also R1).
const LETTERS: string[][] = [
  ['1','2','3','4','5','6','7','8','9','0'],
  ['q','w','e','r','t','y','u','i','o','p'],
  ['a','s','d','f','g','h','j','k','l'],
  ['z','x','c','v','b','n','m'],
  ['?123','SHIFT','SPACE','⌫','CLR','ENTER'],
]

const SYMBOLS: string[][] = [
  ['!','@','#','$','%','^','&','*','(',')'],
  ['-','_','=','+','[',']','{','}','±','~'],
  [';',':','\'','"',',','.','<','>','?','/'],
  ['\\','|','`','€','£','¥','§','°','¿','¡'],
  ['abc','SPACE','⌫','CLR','ENTER'],
]

interface Props {
  title?: string
  password?: boolean
  /** Pre-filled text — e.g. the current search query so reopening doesn't lose it. */
  initialValue?: string
  /** Empty-field hint. Defaults to a password hint only in password mode. */
  placeholder?: string
  onConfirm: (value: string) => void
  onCancel: () => void
  /**
   * A name for the surface this keyboard is sitting on, so a stylesheet can
   * set `--gc-kb-*` for THAT surface and no other.
   *
   * The tokens have to be scoped to something, and the settings screens had
   * their own wrapper to hang them on. The game search did not: it is rendered
   * by the host, inside the host's overlay, and a theme had no selector that
   * reached it — which is why every theme's search keyboard stayed the built-in
   * grey while its password keyboard was dressed.
   */
  className?: string
}

/**
 * On-screen keyboard, themable through `--gc-kb-*` (defaults = the original
 * dark look). Set them on the CONTAINER, not :root: one component serves
 * several surfaces (a paper dialog shipped white-on-white at 1.05:1); callers
 * name theirs via `className` (the game search is `.gc-search-kb`).
 *
 *   --gc-kb-field / --gc-kb-field-ink   the typed-value box and its text
 *   --gc-kb-key / --gc-kb-key-edge      key face, hairline (and Cancel's)
 *   --gc-kb-ink / -strong / -dim / -faint   lettering, focused key, Cancel, legend
 *
 * Focus ring and accent keys use `--gc-accent*`.
 */
export function VirtualKeyboard({ title, password = false, initialValue = '', placeholder, onConfirm, onCancel, className }: Props) {
  const [value, setValue] = useState(initialValue)
  const [layout, setLayout] = useState<'letters' | 'symbols'>('letters')
  const [row, setRow] = useState(1)
  const [col, setCol] = useState(0)
  const [shifted, setShifted] = useState(false)

  const rows = layout === 'letters' ? LETTERS : SYMBOLS

  // Stable ref so gamepad handlers never go stale
  const stateRef = useRef({ row, col, shifted, value, rows })
  useEffect(() => { stateRef.current = { row, col, shifted, value, rows } }, [row, col, shifted, value, rows])

  const onConfirmRef = useRef(onConfirm)
  const onCancelRef  = useRef(onCancel)
  useEffect(() => { onConfirmRef.current = onConfirm }, [onConfirm])
  useEffect(() => { onCancelRef.current  = onCancel  }, [onCancel])

  const toggleLayout = () => {
    setLayout(l => {
      const next = l === 'letters' ? 'symbols' : 'letters'
      const nextRows = next === 'letters' ? LETTERS : SYMBOLS
      // Keep the cursor on a real key after the grid changes shape
      const r = Math.min(stateRef.current.row, nextRows.length - 1)
      setRow(r)
      setCol(c => Math.min(c, nextRows[r].length - 1))
      return next
    })
  }

  const pressKey = (key: string) => {
    const { shifted, value } = stateRef.current
    switch (key) {
      case 'SHIFT': setShifted(s => !s); break
      case 'SPACE': setValue(v => v + ' '); break
      case '⌫':    setValue(v => v.slice(0, -1)); break
      // Backspace is per-character, and a d-pad makes that twelve presses to
      // empty a field nobody can read. On a masked field that is the
      // difference between correcting a password and appending to one.
      case 'CLR':   setValue(''); break
      case 'ENTER': onConfirmRef.current(value); break
      case '?123':
      case 'abc':   toggleLayout(); break
      default: {
        const ch = shifted ? key.toUpperCase() : key
        setValue(v => v + ch)
        if (shifted) setShifted(false)
      }
    }
  }

  // Register gamepad handlers once — use stateRef to avoid stale closures
  useEffect(() => {
    const offs = [
      onGp('gp:dpad-up', () => {
        const { row, rows } = stateRef.current
        const newRow = Math.max(0, row - 1)
        setRow(newRow)
        setCol(c => Math.min(c, rows[newRow].length - 1))
      }),
      onGp('gp:dpad-down', () => {
        const { row, rows } = stateRef.current
        const newRow = Math.min(rows.length - 1, row + 1)
        setRow(newRow)
        setCol(c => Math.min(c, rows[newRow].length - 1))
      }),
      onGp('gp:dpad-left', () => {
        const { row, col, rows } = stateRef.current
        setCol(col > 0 ? col - 1 : rows[row].length - 1)
      }),
      onGp('gp:dpad-right', () => {
        const { row, col, rows } = stateRef.current
        setCol(col < rows[row].length - 1 ? col + 1 : 0)
      }),
      onGp('gp:confirm', () => {
        const { row, col, rows } = stateRef.current
        pressKey(rows[row][col])
      }),
      onGp('gp:back', () => onCancelRef.current()),
      onGp('gp:l1',   () => setShifted(s => !s)),
      onGp('gp:r1',   () => toggleLayout()),
    ]
    return () => offs.forEach(o => o())
  }, []) // intentionally empty — stateRef keeps values fresh

  const displayValue = password ? '●'.repeat(value.length) : value

  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {title && (
        <div style={{ fontSize: 13, color: 'var(--gc-accent-soft, #f2a46a)', textAlign: 'center', marginBottom: 2 }}>
          {title}
        </div>
      )}

      {/* Typed value display — long values are clipped on the left so the
          end of the input (what you're typing) always stays visible */}
      <div style={{
        background: 'var(--gc-kb-field, rgba(0,0,0,0.45))',
        border: '1px solid color-mix(in srgb, var(--gc-accent, #b8501b) 50%, transparent)',
        borderRadius: 10, padding: '10px 16px', minHeight: 44,
        // NOT `--gc-kb-ink-strong`: that one is the lettering on the focused
        // key, which sits on an accent fill and stays light in every theme.
        // This sits on `--gc-kb-field`, which a paper theme makes pale — one
        // token for both put white text on a white field.
        fontSize: 20, letterSpacing: 4, color: 'var(--gc-kb-field-ink, #fff)',
        fontFamily: 'monospace',
        display: 'flex', alignItems: 'center',
        justifyContent: displayValue ? 'flex-end' : 'center',
        overflow: 'hidden', whiteSpace: 'nowrap',
      }}>
        {displayValue || <span style={{ opacity: 0.25, fontSize: 14, }}>{placeholder ?? (password ? 'enter password' : 'start typing…')}</span>}
      </div>

      {/* A masked field is the one place a stray character is invisible: the
          dots clip on the left, and nobody counts them from a sofa. A box
          shipped `<old password><new password>` to NetworkManager for exactly
          that reason. The number is small, but it is the only thing on screen
          that disagrees with "I typed eight characters". */}
      {password && value.length > 0 && (
        <div style={{ fontSize: 11, opacity: 0.45, textAlign: 'right', marginTop: -4 }}>
          {value.length} character{value.length === 1 ? '' : 's'}
        </div>
      )}

      {/* Key rows */}
      {rows.map((keys, ri) => (
        <div key={`${layout}-${ri}`} style={{ display: 'flex', justifyContent: 'center', gap: 4 }}>
          {keys.map((key, ci) => {
            const focused   = ri === row && ci === col
            const isShift   = key === 'SHIFT'
            const isSpace   = key === 'SPACE'
            const isDel     = key === '⌫'
            const isClr     = key === 'CLR'
            const isEnter   = key === 'ENTER'
            const isMode    = key === '?123' || key === 'abc'
            const isSpecial = isShift || isSpace || isDel || isClr || isEnter || isMode
            const label     = isShift ? (shifted ? '⇧●' : '⇧')
                            : isSpace ? 'SPACE'
                            : isEnter ? '↵ OK'
                            : (!isSpecial && layout === 'letters' && shifted) ? key.toUpperCase()
                            : key

            return (
              <button
                key={`${layout}-${ri}-${ci}`}
                onClick={() => pressKey(key)}
                style={{
                  minWidth:   isSpace ? 100 : isShift || isEnter ? 64 : isDel || isClr ? 52 : isMode ? 54 : 34,
                  height:     34,
                  borderRadius: 7,
                  border:     focused
                    // Was a hardcoded #b8501b while the fill beside it already
                    // read the accent, so the focus ring was the default
                    // purple on every theme that changed its colour.
                    ? '2px solid var(--gc-accent, #b8501b)'
                    : '1px solid var(--gc-kb-key-edge, rgba(255,255,255,0.09))',
                  background: focused
                    ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 38%, transparent)'
                    : (isShift && shifted) || isMode
                      ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 20%, transparent)'
                      : isEnter
                        ? 'color-mix(in srgb, var(--gc-accent, #b8501b) 15%, transparent)'
                        : 'var(--gc-kb-key, rgba(255,255,255,0.05))',
                  color:      focused
                    ? 'var(--gc-kb-ink-strong, #fff)'
                    : isEnter || isMode
                      ? 'var(--gc-accent-bright, #f8cfa9)'
                      : 'var(--gc-kb-ink, rgba(255,255,255,0.78))',
                  fontSize:   isSpecial ? 11 : 13,
                  fontWeight: isSpecial ? 600 : 400,
                  cursor:     'pointer',
                  transition: 'all 0.08s',
                  padding:    '0 4px',
                  flexShrink: 0,
                }}
              >
                {label}
              </button>
            )
          })}
        </div>
      ))}

      {/* Cancel button */}
      <button
        onClick={onCancelRef.current}
        style={{
          marginTop: 2, padding: '7px', borderRadius: 8, cursor: 'pointer',
          background: 'transparent',
          border: '1px solid var(--gc-kb-key-edge, rgba(255,255,255,0.08))',
          color: 'var(--gc-kb-ink-dim, rgba(255,255,255,0.3))', fontSize: 12,
        }}
      >
        Cancel
      </button>

      <div style={{ textAlign: 'center', fontSize: 10, color: 'var(--gc-kb-ink-faint, rgba(255,255,255,0.18))', }}>
        <PadHints text="D-Pad navigate · ✕ type · ○ cancel · L1 shift · R1 symbols · ↵ OK" />
      </div>
    </div>
  )
}
