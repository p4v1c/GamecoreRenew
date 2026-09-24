import type { ReactElement } from 'react'
/** Controller button prompts, PlayStation style — see padKey.js. */
export function padGlyph(k: string): string | null
export function PadKey(props: { k: string }): ReactElement
export function PadHints(props: { text: string; className?: string; style?: Record<string, unknown> }): ReactElement
