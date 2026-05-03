import { useState, useEffect, useRef } from 'react'
import { onGp } from '../../hooks/useGamepad'

const ROWS: string[][] = [
  ['1','2','3','4','5','6','7','8','9','0'],
  ['q','w','e','r','t','y','u','i','o','p'],
  ['a','s','d','f','g','h','j','k','l'],
  ['z','x','c','v','b','n','m'],
  ['SHIFT','SPACE','⌫','ENTER'],
]

interface Props {
  title?: string
  password?: boolean
  onConfirm: (value: string) => void
  onCancel: () => void
}

export function VirtualKeyboard({ title, password = false, onConfirm, onCancel }: Props) {
  const [value, setValue] = useState('')
  const [row, setRow] = useState(1)
  const [col, setCol] = useState(0)
  const [shifted, setShifted] = useState(false)

  // Stable ref so gamepad handlers never go stale
  const stateRef = useRef({ row, col, shifted, value })
  useEffect(() => { stateRef.current = { row, col, shifted, value } }, [row, col, shifted, value])

  const onConfirmRef = useRef(onConfirm)
  const onCancelRef  = useRef(onCancel)
  useEffect(() => { onConfirmRef.current = onConfirm }, [onConfirm])
  useEffect(() => { onCancelRef.current  = onCancel  }, [onCancel])

  const pressKey = (key: string) => {
    const { shifted, value } = stateRef.current
    switch (key) {
      case 'SHIFT': setShifted(s => !s); break
      case 'SPACE': setValue(v => v + ' '); break
      case '⌫':    setValue(v => v.slice(0, -1)); break
      case 'ENTER': onConfirmRef.current(value); break
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
        const { row, col } = stateRef.current
        const newRow = Math.max(0, row - 1)
        setRow(newRow)
        setCol(c => Math.min(c, ROWS[newRow].length - 1))
      }),
      onGp('gp:dpad-down', () => {
        const { row, col } = stateRef.current
        const newRow = Math.min(ROWS.length - 1, row + 1)
        setRow(newRow)
        setCol(c => Math.min(c, ROWS[newRow].length - 1))
      }),
      onGp('gp:dpad-left', () => {
        const { row, col } = stateRef.current
        setCol(col > 0 ? col - 1 : ROWS[row].length - 1)
      }),
      onGp('gp:dpad-right', () => {
        const { row, col } = stateRef.current
        setCol(col < ROWS[row].length - 1 ? col + 1 : 0)
      }),
      onGp('gp:confirm', () => {
        const { row, col } = stateRef.current
        pressKey(ROWS[row][col])
      }),
      onGp('gp:back', () => onCancelRef.current()),
      onGp('gp:l1',   () => setShifted(s => !s)),
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

      {/* Typed value display */}
      <div style={{
        background: 'rgba(0,0,0,0.45)', border: '1px solid rgba(124,58,237,0.5)',
        borderRadius: 10, padding: '10px 16px', minHeight: 44,
        fontSize: 20, letterSpacing: 4, color: '#fff', textAlign: 'center',
        fontFamily: 'monospace',
      }}>
        {displayValue || <span style={{ opacity: 0.25, fontSize: 14, letterSpacing: 1 }}>enter password</span>}
      </div>

      {/* Key rows */}
      {ROWS.map((keys, ri) => (
        <div key={ri} style={{ display: 'flex', justifyContent: 'center', gap: 4 }}>
          {keys.map((key, ci) => {
            const focused   = ri === row && ci === col
            const isShift   = key === 'SHIFT'
            const isSpace   = key === 'SPACE'
            const isDel     = key === '⌫'
            const isEnter   = key === 'ENTER'
            const isSpecial = isShift || isSpace || isDel || isEnter
            const label     = isShift ? (shifted ? '⇧●' : '⇧')
                            : isSpace ? 'SPACE'
                            : isEnter ? '↵ OK'
                            : (!isSpecial && shifted) ? key.toUpperCase()
                            : key

            return (
              <button
                key={`${ri}-${ci}`}
                onClick={() => pressKey(key)}
                style={{
                  minWidth:   isSpace ? 100 : isShift || isEnter ? 64 : isDel ? 52 : 34,
                  height:     34,
                  borderRadius: 7,
                  border:     focused
                    ? '2px solid #7c3aed'
                    : '1px solid rgba(255,255,255,0.09)',
                  background: focused
                    ? 'rgba(124,58,237,0.38)'
                    : (isShift && shifted)
                      ? 'rgba(124,58,237,0.2)'
                      : isEnter
                        ? 'rgba(124,58,237,0.15)'
                        : 'rgba(255,255,255,0.05)',
                  color:      focused ? '#fff' : isEnter ? '#c4b5fd' : 'rgba(255,255,255,0.78)',
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
        D-Pad navigate · ✕ type · ⌫ delete · ○ cancel · L1 shift · ↵ OK
      </div>
    </div>
  )
}
