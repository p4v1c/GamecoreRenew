/**
 * Loads a theme module and resolves its surfaces.
 *
 * The module is a native ES module served from /themes/<id>/, imported at
 * runtime — there is no build step for themes, by design (see
 * docs/themes/README.md §2).
 */
import type { ComponentType } from 'react'
import { buildSdk, SDK_VERSION, type SdkHost } from './themeSdk'
import { setThemeSounds, type ThemeSound } from './sounds'
import { setThemeRumble, type RumblePattern } from './rumble'

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
  home?: { cols?: number; rows?: number; paged?: boolean } | null
  /** How long the theme's launch animation runs before the game is started.
   *  Absent = start it immediately, which is what every theme did before. */
  launch?: { ms?: number } | null
  /** UI sounds the theme replaces, `name -> path inside the theme folder`.
   *  The backend has already dropped the ones whose file is missing. */
  sounds?: Record<string, string> | null
  /** Which host settings pages the theme's own menu can open. Absent = it did
   *  not say, which is a different thing from "none" — see unreachablePages. */
  settings?: { pages?: string[] } | null
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
 * The theme's sound set, from its two sources, in precedence order.
 *
 * The manifest can only name files; the module can also hand back functions,
 * which is what a theme that synthesizes rather than ships audio needs — and
 * both shipped themes synthesize. The module wins on a clash, the same way
 * `{ ...DefaultSettingsPages, ...ownPages }` lets a theme keep the host's page
 * for everything it did not write.
 *
 * Exported for its own sake: this merge is the whole contract, and the import()
 * in loadTheme means it is otherwise only reachable on a box with themes on it.
 */
export function resolveThemeSounds(
  m: ThemeManifest,
  produced: Record<string, unknown> = {},
): Record<string, ThemeSound> {
  // Same busting as the entry module and the stylesheet: an author who edits
  // move.wav and reloads must hear move.wav, not whatever Electron cached.
  const bust = `?v=${encodeURIComponent(m.version)}&t=${Date.now()}`
  const url = (rel: string) =>
    `/themes/${encodeURIComponent(m.id)}/${rel.replace(/^\/+/, '')}${bust}`

  const out: Record<string, ThemeSound> = {}
  for (const [name, rel] of Object.entries(m.sounds ?? {})) {
    if (typeof rel === 'string') out[name] = url(rel)
  }

  const fromModule = produced.sounds
  if (fromModule && typeof fromModule === 'object') {
    for (const [name, v] of Object.entries(fromModule as Record<string, unknown>)) {
      if (typeof v === 'function') out[name] = v as ThemeSound
      else if (typeof v === 'string') out[name] = url(v)
      else console.warn(`[gamecore] theme sound "${name}" must be a path or a function — ignored`)
    }
  }
  return out
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

  // After the completeness gate, so a theme that is about to be refused does
  // not leave its bips installed over the default UI that replaces it.
  setThemeSounds(resolveThemeSounds(m, produced as Record<string, unknown>))
  setThemeRumble(resolveThemeRumble(produced as Record<string, unknown>))

  return out
}

/**
 * Settings pages the host has and the theme's menu cannot open.
 *
 * This has already shipped twice, which is the whole argument for checking it.
 * `catalog` was left out of `DefaultSettingsPages` and both bundled themes had
 * no way to install an emulator; `storage` was never added to that map at all,
 * so safe-eject for an external disk was unreachable from any theme that could
 * ever be written. Each time the page existed, the route existed, and nothing
 * on screen could open them — which is invisible until somebody needs the page,
 * and the pages people need are the ones they need when something is wrong.
 *
 * A theme that says nothing gets an empty answer rather than the full list. Not
 * declaring is what a theme reusing the host's settings modal does, and it
 * reaches everything; flagging those would make the warning noise, and a
 * warning that cries wolf is how the first two got through.
 */
export function unreachablePages(m: ThemeManifest | null, hostPages: string[]): string[] {
  const declared = m?.settings?.pages
  if (!declared) return []
  const reachable = new Set(declared)
  return hostPages.filter(p => !reachable.has(p))
}

/**
 * The theme's per-event haptics table.
 *
 * Manifest-side there is nothing to declare — unlike a sound, a pattern is
 * plain data with no file behind it, so the module is the only source and JSON
 * in `theme.json` would be a second way to say the same thing.
 *
 * Keyed on `gp:*` event names, so a theme can make ○ feel different from ✕
 * without the host inventing a vocabulary of feelings first.
 */
export function resolveThemeRumble(
  produced: Record<string, unknown> = {},
): Record<string, RumblePattern> {
  const raw = produced.rumble
  if (!raw || typeof raw !== 'object') return {}
  const out: Record<string, RumblePattern> = {}
  for (const [event, pattern] of Object.entries(raw as Record<string, unknown>)) {
    // The core owns gp:guide, and it owns it here too: a theme that could hang
    // a 3-second buzz off the double-press that kills a running game would be
    // deciding what quitting feels like from inside the presentation layer.
    if (event === 'gp:guide') {
      console.warn('[gamecore] theme tried to dress reserved event gp:guide — ignored')
      continue
    }
    if (pattern && (typeof pattern === 'object')) out[event] = pattern as RumblePattern
    else console.warn(`[gamecore] rumble pattern for "${event}" must be an object or array — ignored`)
  }
  return out
}
