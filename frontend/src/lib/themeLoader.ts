/**
 * Loads a theme module and resolves its surfaces.
 *
 * The module is a native ES module served from /themes/<id>/, imported at
 * runtime — there is no build step for themes, by design (see
 * docs/themes/README.md §2).
 */
import type { ComponentType } from 'react'
import { buildSdk, SDK_VERSION } from './themeSdk'

export type SurfaceName =
  | 'background' | 'decor' | 'home' | 'library' | 'topbar'
  | 'screensaver' | 'keyboard' | 'powerModal' | 'gamepadModal'

export const SURFACES: SurfaceName[] = [
  'background', 'decor', 'home', 'library', 'topbar',
  'screensaver', 'keyboard', 'powerModal', 'gamepadModal',
]

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

/** A theme owns its own markup, so a stylesheet is useful again — unlike the
 *  default UI, which styles itself inline and cannot be overridden. */
function applyStyles(m: ThemeManifest | null): void {
  document.getElementById(STYLE_ID)?.remove()
  if (!m?.styles) return
  const link = document.createElement('link')
  link.id = STYLE_ID
  link.rel = 'stylesheet'
  link.href = `/themes/${encodeURIComponent(m.id)}/${m.styles}?v=${encodeURIComponent(m.version)}`
  document.head.appendChild(link)
}

/** Called when falling back to the default theme. */
export function clearThemeStyles(): void {
  applyStyles(null)
}

/**
 * Import a theme and return only the surfaces it both declared and exported.
 * Throws on anything structural — the caller records the crash and falls back.
 */
export async function loadTheme(m: ThemeManifest): Promise<SurfaceMap> {
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

  const produced = factory(buildSdk(m.id))
  if (!produced || typeof produced !== 'object') {
    throw new Error('theme factory must return an object of surfaces')
  }

  const declared = new Set(m.provides)
  const out: SurfaceMap = {}
  for (const name of SURFACES) {
    const comp = (produced as Record<string, unknown>)[name]
    if (!comp) continue
    if (!declared.has(name)) {
      // Declared-and-exported is the gate: it stops a theme from silently
      // taking over a screen its author never listed.
      console.warn(`[gamecore] theme ${m.id} exports "${name}" without declaring it — ignored`)
      continue
    }
    if (typeof comp !== 'function') {
      console.warn(`[gamecore] theme ${m.id}: surface "${name}" is not a component — ignored`)
      continue
    }
    out[name] = comp as ComponentType<any>
  }

  for (const name of m.provides) {
    if (!out[name as SurfaceName]) {
      console.warn(`[gamecore] theme ${m.id} declares "${name}" but did not export it — using default`)
    }
  }

  return out
}
