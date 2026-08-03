/**
 * Loads a theme module and resolves its surfaces.
 *
 * The module is a native ES module served from /themes/<id>/, imported at
 * runtime — there is no build step for themes, by design (see
 * docs/themes/README.md §2).
 */
import type { ComponentType } from 'react'
import { buildSdk, SDK_VERSION, type SdkHost } from './themeSdk'

/**
 * The two surfaces a theme owns: the boot animation, and the frontend body.
 *
 * Both are mandatory. A theme that covers one and leaves the other to the
 * default produces exactly the half-and-half UI that made the first version
 * feel broken — a beach dashboard behind the stock purple splash. Either a
 * theme dresses the whole thing or it does not load at all.
 *
 * It used to be nine interleaved surfaces. That is what made themes brittle:
 * the theme's tree and the host's fought over stacking, the modal stack and the
 * containers that default pages expect. One owner per tree removes the class.
 */
export type SurfaceName = 'splash' | 'shell'

export const SURFACES: SurfaceName[] = ['splash', 'shell']

export interface ThemeManifest {
  id: string
  name: string
  version: string
  api: number
  author: string
  description: string
  entry: string
  preview: string | null
  styles: string | null
  provides: string[]
  schedule?: { from?: string; to?: string } | null
  /** Dashboard grid the theme asks for. Absent = whatever the host uses. */
  home?: { cols?: number; rows?: number } | null
  compatible: boolean
  warnings: string[]
}

export interface ThemeIndex {
  sdk_version: number
  active: string | null
  themes: ThemeManifest[]
}

export type SurfaceMap = Partial<Record<SurfaceName, ComponentType<any>>>

export async function fetchThemeIndex(): Promise<ThemeIndex> {
  const r = await fetch('/api/themes')
  if (!r.ok) throw new Error(`theme index: ${r.status}`)
  return r.json()
}

export async function setActiveTheme(id: string | null): Promise<void> {
  const r = await fetch('/api/themes/active', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!r.ok) throw new Error(`select theme: ${r.status}`)
}

const STYLE_ID = 'gc-theme-style'

/**
 * A theme owns its own markup, so a stylesheet is useful again — unlike the
 * default UI, which styles itself inline and cannot be overridden.
 *
 * Busted on every load, exactly like the entry module. Keying the URL on the
 * manifest version alone meant an edited theme.css kept serving from cache
 * until its author remembered to bump `version` — so a theme looked unchanged
 * no matter what they wrote, and a shipped fix could stay invisible after an
 * update.
 */
function applyStyles(m: ThemeManifest | null): void {
  document.getElementById(STYLE_ID)?.remove()
  if (!m?.styles) return
  const link = document.createElement('link')
  link.id = STYLE_ID
  link.rel = 'stylesheet'
  link.href = `/themes/${encodeURIComponent(m.id)}/${m.styles}?v=${encodeURIComponent(m.version)}&t=${Date.now()}`
  document.head.appendChild(link)
}

/** Called when falling back to the default theme. */
export function clearThemeStyles(): void {
  applyStyles(null)
}

/**
 * Import a theme and return its surfaces.
 *
 * Completeness is a load-time gate, not a per-screen fallback: a missing or
 * malformed surface throws, the caller records it, and the default frontend
 * runs whole. Nothing is ever half-themed.
 */
export async function loadTheme(m: ThemeManifest, host: SdkHost): Promise<SurfaceMap> {
  if (m.api > SDK_VERSION) {
    throw new Error(`theme targets SDK v${m.api}, this build speaks v${SDK_VERSION}`)
  }

  // Cache-bust: Electron's HTTP cache has hidden UI changes before
  // (see docs/architecture/09-gotchas.md).
  const url = `/themes/${encodeURIComponent(m.id)}/${m.entry}?v=${encodeURIComponent(m.version)}&t=${Date.now()}`
  const mod = await import(/* @vite-ignore */ url)

  const factory = mod?.default
  if (typeof factory !== 'function') {
    throw new Error('theme entry must default-export a function')
  }

  applyStyles(m)

  const produced = factory(buildSdk(m.id, host))
  if (!produced || typeof produced !== 'object') {
    throw new Error('theme factory must return an object of surfaces')
  }

  const declared = new Set(m.provides)
  const out: SurfaceMap = {}
  const missing: string[] = []

  for (const name of SURFACES) {
    const comp = (produced as Record<string, unknown>)[name]
    // Declared *and* exported: the manifest is the promise, the export is the
    // thing. Either one alone means the theme is incomplete.
    if (!declared.has(name)) { missing.push(`${name} (not declared in theme.json)`); continue }
    if (typeof comp !== 'function') { missing.push(`${name} (not exported as a component)`); continue }
    out[name] = comp as ComponentType<any>
  }

  if (missing.length) {
    throw new Error(`theme is incomplete — a theme must provide every surface: ${missing.join(', ')}`)
  }

  return out
}
