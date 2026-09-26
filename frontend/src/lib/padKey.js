/**
 * Button prompts drawn as controller buttons, PlayStation style.
 *
 * GameCore is driven with a pad, and the hints used to print keyboard-looking
 * keys — "↑↓" and "←→" in bordered boxes — that read as arrow keys on a
 * keyboard nobody has plugged in. Every hint in the host and in the shipped
 * themes goes through this one component instead, keyed by the same short
 * labels they already used ("↑↓", "← →", "✕", "L1 R1"…), so a theme changes one
 * element and keeps its hint lists.
 *
 * Inline SVG and inline styles only: it has to look the same on Orbit's dark
 * glass, Shelf's paper and Summer's beach, so outlines follow `currentColor`
 * and only the four face symbols carry their own colour. The defaults are
 * pale, for dark screens; a light theme sets `--gc-pad-cross`, `-circle`,
 * `-square` and `-triangle` to darker ones (≥ 3:1 on its background).
 */
import { createElement } from 'react'

const FACE = {
  '✕': ['var(--gc-pad-cross, #7aa7ff)', '<path d="M8 8l8 8M16 8l-8 8" stroke-width="2.2" stroke-linecap="round"/>'],
  '○': ['var(--gc-pad-circle, #ff6f76)', '<circle cx="12" cy="12" r="4.6" fill="none" stroke-width="2.2"/>'],
  '□': ['var(--gc-pad-square, #f58fd6)', '<rect x="7.6" y="7.6" width="8.8" height="8.8" rx="0.8" fill="none" stroke-width="2.2"/>'],
  '△': ['var(--gc-pad-triangle, #4fd1a5)', '<path d="M12 7.2l5 8.6H7z" fill="none" stroke-width="2.1" stroke-linejoin="round"/>'],
}

// Which arms of the d-pad are lit.
const DPAD = {
  '↑↓': 'ud', '↑ ↓': 'ud', '←→': 'lr', '← →': 'lr',
  '← → ↑ ↓': 'udlr', '↑↓←→': 'udlr', '↑ ↓ ← →': 'udlr', '↑↓ ←→': 'udlr',
  '↑': 'u', '↓': 'd', '←': 'l', '→': 'r',
}
const ARMS = {
  u: 'M9.5 2.5h5v6.2L12 11.2 9.5 8.7z', d: 'M9.5 21.5h5v-6.2L12 12.8l-2.5 2.5z',
  l: 'M2.5 9.5v5h6.2L11.2 12 8.7 9.5z', r: 'M21.5 9.5v5h-6.2L12.8 12l2.5-2.5z',
}

const svg = (body, label) =>
  `<svg viewBox="0 0 24 24" width="1.35em" height="1.35em" role="img" aria-label="${label}" ` +
  `style="display:inline-block;vertical-align:-0.32em;overflow:visible">${body}</svg>`

function dpad(lit) {
  return svg(Object.entries(ARMS).map(([arm, d]) => lit.includes(arm)
    ? `<path d="${d}" fill="currentColor"/>`
    : `<path d="${d}" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="1.2"/>`).join(''),
  'D-pad')
}

function face(symbol) {
  const [colour, shape] = FACE[symbol]
  return svg(`<circle cx="12" cy="12" r="10.4" fill="none" stroke="currentColor" stroke-opacity=".8" stroke-width="1.3"/>` +
    `<g style="stroke:${colour}">${shape}</g>`, symbol)
}

// Buttons that are drawn as a labelled pill, the way PlayStation prompts show
// L1/R1 and Options. Xbox names are accepted so a theme can map to them.
const PILL = /^([LR][123]|Options|Share|Create|PS|Menu|View|LB|RB|LT|RT|[ABXY])$/

const pill = (text, key) => createElement('span', {
  key,
  style: {
    display: 'inline-block', minWidth: '1.9em', padding: '0 .38em', textAlign: 'center',
    border: '1.5px solid currentColor', borderRadius: '.55em .55em .3em .3em',
    fontSize: 'max(.8em, 14px)', fontWeight: 700, lineHeight: '1.45em', letterSpacing: '.02em',
    verticalAlign: '.08em',
  },
}, text)

const raw = (html, key) => createElement('span', { key, style: { display: 'inline-flex' },
  dangerouslySetInnerHTML: { __html: html } })

/** The glyph for one hint key, or null when it is not a pad label we know. */
export function padGlyph(k) {
  const key = String(k).trim()
  if (FACE[key]) return face(key)
  if (DPAD[key]) return dpad(DPAD[key])
  if (key === 'D-Pad') return dpad('udlr')
  return null
}

/**
 * `<PadKey k="↑↓" />` — one hint key as controller button(s). Compound labels
 * ("L1 R1", "L1 / R1", "D-Pad / L-stick", "PS ×2") are drawn piece by piece:
 * a glyph, a pill, or the word itself.
 */
export function PadKey({ k }) {
  const key = String(k ?? '').trim()
  const wrap = { className: 'gc-pad', 'data-k': key,
    style: { display: 'inline-flex', alignItems: 'center', gap: '.22em', marginRight: '.35em' } }
  const whole = padGlyph(key)
  if (whole) return createElement('span', wrap, raw(whole, 0))
  const parts = key.split(/\s*(\/)\s*|\s+/).filter(Boolean)
  return createElement('span', wrap, ...parts.map((part, i) => {
    const glyph = padGlyph(part)
    if (glyph) return raw(glyph, i)
    if (PILL.test(part)) return pill(part, i)
    return createElement('span', { key: i }, part)
  }))
}

const isKeyToken = (t) => /^[↑↓←→✕○□△]+$/.test(t) || /^[LR][123](\/[LR][123])?$/.test(t)
  || /^(D-Pad|Options|PS|×2)$/.test(t)

/**
 * `<PadHints text="↑↓ Navigate · ✕ Select · ○ Back" />` — the hint strings the
 * screens already had, with each leading key drawn as a controller button.
 * Segments are split on " · "; the leading run of key tokens is the button,
 * the rest is its label. Anything that is not a key stays text.
 */
export function PadHints({ text, className, style }) {
  const segments = String(text ?? '').split(/\s+·\s+/).filter((s) => s.trim())
  return createElement('span', { className, style: { display: 'inline-flex', flexWrap: 'wrap',
    alignItems: 'center', columnGap: '1.1em', rowGap: '.3em', ...style } },
  ...segments.map((seg, i) => {
    const words = seg.trim().split(/\s+/)
    let n = 0
    while (n < words.length && isKeyToken(words[n])) n++
    const key = words.slice(0, n).join(' ')
    const label = words.slice(n).join(' ')
    const k = key === 'D-Pad' ? '← → ↑ ↓' : key.replace(/\//g, ' ')
    return createElement('span', { key: i, style: { display: 'inline-flex', alignItems: 'center' } },
      key ? createElement(PadKey, { k }) : null, label)
  }))
}
