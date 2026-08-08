/**
 * The mapping wizard — any controller playable in about a minute, no keyboard.
 *
 * One button at a time, full frame, driven entirely by the pad being mapped.
 * That last point is the constraint everything here follows from: the player is
 * holding a controller the box does not understand, so nothing on this screen
 * may depend on a binding. The Gamepad API events the rest of the UI runs on
 * (`gp:confirm`, `gp:back`) are exactly what a pad SDL cannot map does not
 * produce reliably — so this screen ignores them and listens only to the raw
 * capture stream from the backend.
 *
 * The four gestures, and why each exists:
 *
 *   press          record this input for the current step and advance
 *   HOLD           skip a button the pad does not have. A hold rather than a
 *                  second button, because there is no second button we can
 *                  trust yet — every pad can hold the one it just pressed
 *   double-press   go back one step. Same reason
 *   nothing        after a while, an on-screen reminder of the two above. A
 *                  wizard whose escape hatch is invisible is a soft lock in
 *                  front of a television
 *
 * The keyboard shortcuts alongside are for a developer at a desk, never the
 * path the box is designed around.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { api, type MappingStep, type MappingSession } from '../../../api'

/** How long a press must last to count as "this pad has no such button". */
const HOLD_MS = 900
/**
 * Press the SAME input again within this long and it means "undo that".
 *
 * The same-input part is what makes it work at all. A plain double-press
 * cannot coexist with the settle window below: the first press advances the
 * step and starts the window, and the second is then swallowed as bleed. Tying
 * undo to the input just recorded resolves it — that input is by definition
 * not bleed from an earlier step, because it IS the earlier step.
 */
const UNDO_MS = 700
/**
 * After recording, ignore a DIFFERENT input for a moment. A stick pushed for
 * `leftx` is still deflected when `lefty` comes up, and a button bounces —
 * without this one push silently fills three steps in a row.
 */
const SETTLE_MS = 350

type Phase = 'starting' | 'capturing' | 'review' | 'saving' | 'done' | 'error'

interface Props {
  onClose: () => void
  /** Told what was written, so the caller can refresh whatever listed it. */
  onSaved?: (lines: string[]) => void
}

export default function MappingWizard({ onClose, onSaved }: Props) {
  const [phase, setPhase] = useState<Phase>('starting')
  const [session, setSession] = useState<MappingSession | null>(null)
  const [error, setError] = useState('')
  const [stepIdx, setStepIdx] = useState(0)
  const [bindings, setBindings] = useState<Record<string, string>>({})
  const [lastSeen, setLastSeen] = useState('')
  const [holding, setHolding] = useState(false)
  const [idle, setIdle] = useState(false)
  const [result, setResult] = useState<{ lines: string[]; missing: string[] } | null>(null)
  const [copied, setCopied] = useState(false)

  const steps: MappingStep[] = session?.steps ?? []
  const step: MappingStep | undefined = steps[stepIdx]

  // Refs, because the socket handler is installed once and would otherwise
  // close over the first render's state — the bug that makes a wizard record
  // every button onto step 1.
  const stepIdxRef = useRef(0)
  const sessionRef = useRef<MappingSession | null>(null)
  const acceptAfter = useRef(0)
  const pressStart = useRef<{ at: number; binding: string; signed: string } | null>(null)
  /** What the last recorded step bound, so re-pressing it means undo. */
  const lastPress = useRef<{ binding: string; at: number }>({ binding: '', at: 0 })
  const holdTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const phaseRef = useRef<Phase>('starting')
  const bindingsRef = useRef<Record<string, string>>({})
  useEffect(() => { stepIdxRef.current = stepIdx }, [stepIdx])
  useEffect(() => { phaseRef.current = phase }, [phase])
  useEffect(() => { bindingsRef.current = bindings }, [bindings])

  const total = steps.length
  const isLast = stepIdx >= total - 1

  const record = useCallback((field: string, token: string) => {
    setBindings(b => ({ ...b, [field]: token }))
    setStepIdx(i => i + 1)
    acceptAfter.current = Date.now() + SETTLE_MS
  }, [])

  const skip = useCallback(() => {
    setStepIdx(i => i + 1)
    setHolding(false)
    acceptAfter.current = Date.now() + SETTLE_MS
  }, [])

  const save = useCallback(() => {
    setPhase('saving')
    api.controllers.mapping.commit(bindingsRef.current, sessionRef.current?.controller || '')
      .then(r => {
        if (!r.ok) { setError(r.error || 'could not save'); setPhase('error'); return }
        setResult({ lines: r.lines ?? [], missing: r.missing ?? [] })
        setPhase('done')
        onSaved?.(r.lines ?? [])
      })
      .catch(() => { setError('could not save'); setPhase('error') })
  }, [onSaved])

  const back = useCallback(() => {
    setPhase('capturing')
    setStepIdx(i => {
      const to = Math.max(0, i - 1)
      // Clear what that step held, so going back and skipping actually leaves
      // it unbound rather than keeping the value being corrected.
      setBindings(b => {
        const field = steps[to]?.field
        if (!field) return b
        const { [field]: _dropped, ...rest } = b
        return rest
      })
      return to
    })
    acceptAfter.current = Date.now() + SETTLE_MS
  }, [steps])

  // ── open the session and the event stream ─────────────────────────────────
  useEffect(() => {
    let socket: WebSocket | null = null
    let cancelled = false

    api.controllers.mapping.start()
      .then(s => {
        if (cancelled) return
        if (!s.ok) { setError(s.error || 'could not start'); setPhase('error'); return }
        setSession(s)
        sessionRef.current = s
        setPhase('capturing')

        // Taken from the reply rather than from state: this handler is
        // installed once and would otherwise close over the empty first render.
        const list = s.steps ?? []

        socket = api.controllers.mapping.socket()
        socket.onmessage = e => {
          let msg: { event: string; data: Record<string, unknown> }
          try { msg = JSON.parse(e.data) } catch { return }
          if (msg.event === 'error') {
            setError(String(msg.data.error || 'the capture stream failed'))
            setPhase('error')
            return
          }
          if (msg.event !== 'input') return

          const binding = String(msg.data.binding)
          const signed = String(msg.data.signed || binding)
          const pressed = msg.data.pressed !== false
          const current = list[stepIdxRef.current]
          const now = Date.now()

          if (pressed) setLastSeen(signed)

          // ── the review screen ─────────────────────────────────────────────
          // Confirmed with the input the player themselves told us was A. That
          // is not a flourish: it is the first end-to-end proof the capture is
          // right, made before anything is written, using the only binding the
          // box can be sure of at this point.
          if (phaseRef.current === 'review') {
            if (pressed) return
            const confirm = bindingsRef.current.a
            if (confirm && binding === confirm) { save(); return }
            const undoLast = lastPress.current.binding
            if (undoLast && binding === undoLast) back()
            return
          }
          if (!current) return

          // Undoing the step just recorded is the ONE thing the settle window
          // must let through — the input it names cannot be bleed from an
          // earlier step, because it is the step being undone.
          const undoing = lastPress.current.binding === binding
            && now - lastPress.current.at < UNDO_MS
          if (now < acceptAfter.current && !undoing) return

          // ── the press edge: start timing, and arm the hold ────────────────
          if (pressed) {
            if (pressStart.current) return          // a second input while one
                                                    // is held is not a gesture
            pressStart.current = { at: now, binding, signed }
            setHolding(true)
            if (holdTimer.current) clearTimeout(holdTimer.current)
            holdTimer.current = setTimeout(() => {
              // Still down after HOLD_MS: the pad has no such button.
              holdTimer.current = null
              pressStart.current = null
              setHolding(false)
              lastPress.current = { binding: '', at: 0 }
              skip()
            }, HOLD_MS)
            return
          }

          // ── the release edge: it was a short press ────────────────────────
          const start = pressStart.current
          pressStart.current = null
          setHolding(false)
          if (!start || start.binding !== binding) return
          if (holdTimer.current === null) return    // the hold already fired
          clearTimeout(holdTimer.current)
          holdTimer.current = null

          if (undoing) {
            lastPress.current = { binding: '', at: 0 }
            back()
            return
          }
          lastPress.current = { binding, at: now }

          // A trigger wants the sign; a stick axis is bound whole. Only the
          // step being asked for knows which, which is why the backend sends
          // both spellings and lets this decide.
          const token = current.kind === 'axis' && current.field.includes('trigger')
            ? start.signed : start.binding
          record(current.field, token)
        }
        socket.onerror = () => { setError('the capture stream failed'); setPhase('error') }
      })
      .catch(() => { if (!cancelled) { setError('could not reach the backend'); setPhase('error') } })

    return () => {
      cancelled = true
      if (holdTimer.current) clearTimeout(holdTimer.current)
      socket?.close()
      // Always: leaving the screen must not leave a session holding /dev/input.
      api.controllers.mapping.cancel().catch(() => {})
    }
    // Installed once on purpose — the handler reads live values through refs.
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── the reminder ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (phase !== 'capturing') return
    setIdle(false)
    const t = setTimeout(() => setIdle(true), 6000)
    return () => clearTimeout(t)
  }, [stepIdx, phase])

  // ── the last step leads to review, never straight to disk ─────────────────
  // Committing on the final press would make the last button the one binding
  // that can never be corrected: there is no screen left to undo it from, and
  // the file is already written.
  useEffect(() => {
    if (phase !== 'capturing' || !total || stepIdx < total) return
    setPhase('review')
  }, [stepIdx, total, phase])

  // ── keyboard, for a desk ──────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (phase === 'review') {
        if (e.key === 'Enter') save()
        if (e.key === 'Backspace' || e.key === 'ArrowLeft') back()
        return
      }
      if (phase !== 'capturing') return
      if (e.key === 's' || e.key === 'ArrowRight') skip()
      if (e.key === 'Backspace' || e.key === 'ArrowLeft') back()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [phase, onClose, skip, back, save])

  const contribute = () => {
    const text = (result?.lines ?? []).join('\n')
    navigator.clipboard?.writeText(text).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), 2500) },
      () => setCopied(false))
  }

  const done = Object.keys(bindings).length

  return (
    <div style={S.frame}>
      {phase === 'starting' && <Centered title="Looking for your controller…" />}

      {phase === 'error' && (
        <Centered title="The wizard could not start" detail={error}>
          <button style={S.button} onClick={onClose} autoFocus>Close</button>
        </Centered>
      )}

      {phase === 'saving' && <Centered title="Saving…" />}

      {phase === 'review' && (
        <Centered
          title="Check it over"
          detail={`${done} of ${total} recorded for ${session?.controller}. ` +
                  'Nothing has been written yet.'}
        >
          <div style={S.review}>
            {steps.map(s => (
              <div key={s.field} style={S.reviewRow}>
                <span style={S.reviewField}>{s.field}</span>
                <code style={S.reviewToken}>
                  {bindings[s.field] ?? <span style={S.absent}>not on this pad</span>}
                </code>
              </div>
            ))}
          </div>
          <div style={S.buttons}>
            <button style={S.button} onClick={back}>Back one step</button>
            <button style={{ ...S.button, ...S.primary }} onClick={save} autoFocus>
              Save
            </button>
          </div>
          {bindings.a && (
            <div style={S.contribute}>
              Or press the button you told us was <b>A / Cross</b> — if that
              works, the mapping is right.
            </div>
          )}
        </Centered>
      )}

      {phase === 'capturing' && step && (
        <>
          <div style={S.header}>
            <div style={S.pad}>{session?.controller}</div>
            <div style={S.counter}>{stepIdx + 1} / {total}</div>
          </div>

          <div style={S.bar}>
            <div style={{ ...S.barFill, width: `${(stepIdx / total) * 100}%` }} />
          </div>

          <div style={S.stage}>
            <Glyph field={step.field} holding={holding} />
            <div style={S.ask}>{step.label}</div>
            <div style={S.kind}>
              {step.kind === 'axis' ? 'Push it all the way' : 'Press it'}
            </div>
            {lastSeen && <div style={S.seen}>last input seen: <code>{lastSeen}</code></div>}
          </div>

          <div style={{ ...S.hints, opacity: idle ? 1 : 0.35 }}>
            <span><b>Hold</b> any button — this pad does not have it</span>
            <span><b>Press twice quickly</b> — go back</span>
          </div>
          <div style={S.footer}>
            {done} recorded · <button style={S.link} onClick={onClose}>Cancel</button>
          </div>
        </>
      )}

      {phase === 'done' && result && (
        <Centered
          title="Your controller is mapped"
          detail={
            result.missing.length
              ? `Saved, but these were skipped: ${result.missing.join(', ')}. ` +
                'Run the wizard again if one of them exists on your pad.'
              : 'Every button was recorded. It works in all thirteen systems, ' +
                'and it survives a restart and an update.'
          }
        >
          <div style={S.lineBox}>
            {result.lines.map(l => <code key={l} style={S.line}>{l}</code>)}
          </div>
          <div style={S.buttons}>
            <button style={S.button} onClick={contribute}>
              {copied ? 'Copied ✓' : 'Copy & contribute'}
            </button>
            <button style={{ ...S.button, ...S.primary }} onClick={onClose} autoFocus>
              Done
            </button>
          </div>
          <div style={S.contribute}>
            Paste it at <b>github.com/mdqinc/SDL_GameControllerDB</b> — every
            mapping sent upstream reaches everyone with the same controller.
          </div>
        </Centered>
      )}
    </div>
  )
}

/**
 * One illustrated button. Deliberately a drawing and not a word: the player may
 * not read English, and "the big centre button" is a paragraph where a picture
 * is instant.
 */
function Glyph({ field, holding }: { field: string; holding: boolean }) {
  const art: Record<string, { face: string; where: string }> = {
    a: { face: '✕', where: 'bottom' }, b: { face: '○', where: 'right' },
    x: { face: '□', where: 'left' }, y: { face: '△', where: 'top' },
    dpup: { face: '▲', where: 'dpad' }, dpdown: { face: '▼', where: 'dpad' },
    dpleft: { face: '◀', where: 'dpad' }, dpright: { face: '▶', where: 'dpad' },
    leftshoulder: { face: 'L1', where: 'shoulder' },
    rightshoulder: { face: 'R1', where: 'shoulder' },
    lefttrigger: { face: 'L2', where: 'trigger' },
    righttrigger: { face: 'R2', where: 'trigger' },
    back: { face: '⊟', where: 'centre' }, start: { face: '≡', where: 'centre' },
    guide: { face: '⌂', where: 'centre' },
    leftstick: { face: 'L3', where: 'stick' }, rightstick: { face: 'R3', where: 'stick' },
    leftx: { face: '↔', where: 'stick' }, lefty: { face: '↕', where: 'stick' },
    rightx: { face: '↔', where: 'stick' }, righty: { face: '↕', where: 'stick' },
  }
  const g = art[field] ?? { face: '?', where: '' }
  return (
    <div style={{
      ...S.glyph,
      transform: holding ? 'scale(0.92)' : 'scale(1)',
      borderColor: holding ? 'var(--gc-accent, #7c3aed)' : 'rgba(255,255,255,0.18)',
    }}>
      <span style={S.glyphFace}>{g.face}</span>
      <span style={S.glyphWhere}>{g.where}</span>
    </div>
  )
}

function Centered({ title, detail, children }: {
  title: string; detail?: string; children?: React.ReactNode
}) {
  return (
    <div style={S.centered}>
      <div style={S.title}>{title}</div>
      {detail && <div style={S.detail}>{detail}</div>}
      {children}
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  frame: {
    position: 'fixed', inset: 0, zIndex: 900, background: 'rgba(8,8,14,0.97)',
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: 40, fontFamily: 'inherit',
  },
  header: {
    position: 'absolute', top: 32, left: 40, right: 40, display: 'flex',
    justifyContent: 'space-between', alignItems: 'center',
  },
  pad: { fontSize: 13, color: 'rgba(255,255,255,0.55)', fontWeight: 700 },
  counter: { fontSize: 13, color: 'rgba(255,255,255,0.3)' },
  bar: {
    position: 'absolute', top: 62, left: 40, right: 40, height: 3,
    borderRadius: 2, background: 'rgba(255,255,255,0.07)', overflow: 'hidden',
  },
  barFill: {
    height: '100%', background: 'var(--gc-accent, #7c3aed)',
    transition: 'width 180ms ease',
  },
  stage: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 },
  glyph: {
    width: 148, height: 148, borderRadius: 28, display: 'flex',
    flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    gap: 6, border: '2px solid rgba(255,255,255,0.18)',
    background: 'rgba(255,255,255,0.04)', transition: 'all 120ms ease',
  },
  glyphFace: { fontSize: 56, color: '#fff', lineHeight: 1 },
  glyphWhere: {
    fontSize: 10, letterSpacing: 2, textTransform: 'uppercase',
    color: 'rgba(255,255,255,0.3)',
  },
  ask: { fontSize: 26, fontWeight: 700, color: '#fff', textAlign: 'center' },
  kind: { fontSize: 13, color: 'rgba(255,255,255,0.4)' },
  seen: { fontSize: 11, color: 'rgba(255,255,255,0.22)' },
  hints: {
    position: 'absolute', bottom: 72, display: 'flex', gap: 28,
    fontSize: 12, color: 'rgba(255,255,255,0.5)', transition: 'opacity 400ms ease',
  },
  footer: {
    position: 'absolute', bottom: 36, fontSize: 11,
    color: 'rgba(255,255,255,0.25)',
  },
  link: {
    background: 'none', border: 'none', color: 'rgba(255,255,255,0.45)',
    fontSize: 11, cursor: 'pointer', textDecoration: 'underline',
    font: 'inherit', padding: 0,
  },
  centered: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
    maxWidth: 680, textAlign: 'center',
  },
  title: { fontSize: 24, fontWeight: 700, color: '#fff' },
  detail: { fontSize: 14, color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 },
  lineBox: {
    display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 640,
    maxHeight: 140, overflowY: 'auto', width: '100%',
  },
  line: {
    fontSize: 10, color: 'rgba(255,255,255,0.4)', background: 'rgba(255,255,255,0.04)',
    padding: '6px 10px', borderRadius: 6, wordBreak: 'break-all', textAlign: 'left',
  },
  review: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 20px',
    width: '100%', maxHeight: 260, overflowY: 'auto', margin: '4px 0',
  },
  reviewRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    gap: 10, padding: '3px 8px', borderRadius: 6,
    background: 'rgba(255,255,255,0.03)',
  },
  reviewField: { fontSize: 11, color: 'rgba(255,255,255,0.45)' },
  reviewToken: { fontSize: 11, color: 'var(--gc-accent-bright, #c4b5fd)' },
  absent: { color: 'rgba(255,255,255,0.2)', fontStyle: 'italic' },
  buttons: { display: 'flex', gap: 12, marginTop: 6 },
  button: {
    padding: '10px 22px', borderRadius: 10, fontSize: 13, fontWeight: 700,
    color: '#fff', background: 'rgba(255,255,255,0.07)',
    border: '1px solid rgba(255,255,255,0.14)', cursor: 'pointer', font: 'inherit',
  },
  primary: {
    background: 'var(--gc-accent, #7c3aed)', borderColor: 'transparent',
  },
  contribute: {
    fontSize: 11, color: 'rgba(255,255,255,0.3)', maxWidth: 460, lineHeight: 1.6,
  },
}
