import { useState, useEffect, useRef } from 'react'
import { onGp } from '../../hooks/useGamepad'

// Two layers: letters and symbols. '?123' / 'abc' switches (also R1).
const LETTERS: string[][] = [
  ['1','2','3','4','5','6','7','8','9','0'],
  ['q','w','e','r','t','y','u','i','o','p'],
  ['a','s','d','f','g','h','j','k','l'],
  ['z','x','c','v','b','n','m'],
  ['?123','SHIFT','SPACE','⌫','ENTER'],
]

const SYMBOLS: string[][] = [
  ['!','@','#','$','%','^','&','*','(',')'],
  ['-','_','=','+','[',']','{','}','±','~'],
  [';',':','\'','"',',','.','<','>','?','/'],
  ['\\','|','`','€','£','¥','§','°','¿','¡'],
  ['abc','SPACE','⌫','ENTER'],
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
}

export function VirtualKeyboard({ title, password = false, initialValue = '', placeholder, onConfirm, onCancel }: Props) {
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {title && (
        <div style={{ fontSize: 13, color: '#a78bfa', textAlign: 'center', letterSpacing: 1, marginBottom: 2 }}>
          {title}
        </div>
      )}

      {/* Typed value display — long values are clipped on the left so the
          end of the input (what you're typing) always stays visible */}
      <div style={{
        background: 'rgba(0,0,0,0.45)', border: '1px solid rgba(124,58,237,0.5)',
        borderRadius: 10, padding: '10px 16px', minHeight: 44,
        fontSize: 20, letterSpacing: 4, color: '#fff',
        fontFamily: 'monospace',
        display: 'flex', alignItems: 'center',
        justifyContent: displayValue ? 'flex-end' : 'center',
        overflow: 'hidden', whiteSpace: 'nowrap',
      }}>
        {displayValue || <span style={{ opacity: 0.25, fontSize: 14, letterSpacing: 1 }}>{placeholder ?? (password ? 'enter password' : 'start typing…')}</span>}
      </div>

      {/* Key rows */}
      {rows.map((keys, ri) => (
        <div key={`${layout}-${ri}`} style={{ display: 'flex', justifyContent: 'center', gap: 4 }}>
          {keys.map((key, ci) => {
            const focused   = ri === row && ci === col
            const isShift   = key === 'SHIFT'
            const isSpace   = key === 'SPACE'
            const isDel     = key === '⌫'
            const isEnter   = key === 'ENTER'
            const isMode    = key === '?123' || key === 'abc'
            const isSpecial = isShift || isSpace || isDel || isEnter || isMode
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
                  minWidth:   isSpace ? 100 : isShift || isEnter ? 64 : isDel ? 52 : isMode ? 54 : 34,
                  height:     34,
                  borderRadius: 7,
                  border:     focused
                    ? '2px solid #7c3aed'
                    : '1px solid rgba(255,255,255,0.09)',
                  background: focused
                    ? 'rgba(124,58,237,0.38)'
                    : (isShift && shifted) || isMode
                      ? 'rgba(124,58,237,0.2)'
                      : isEnter
                        ? 'rgba(124,58,237,0.15)'
                        : 'rgba(255,255,255,0.05)',
                  color:      focused ? '#fff' : isEnter || isMode ? '#c4b5fd' : 'rgba(255,255,255,0.78)',
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
          background: 'transparent', border: '1px solid rgba(255,255,255,0.08)',
          color: 'rgba(255,255,255,0.3)', fontSize: 12,
        }}
      >
        Cancel
      </button>

      <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        D-Pad navigate · ✕ type · ○ cancel · L1 shift · R1 symbols · ↵ OK
      </div>
    </div>
  )
}
