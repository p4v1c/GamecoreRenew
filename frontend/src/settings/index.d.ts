/**
 * Types for the two shared screens, which stay plain `.js` on purpose: they
 * are written in the theme SDK's idiom (`sdk.ui.html` templates, sdk passed
 * in), the same language theme authors write.
 *
 * Ambient modules match the import SPECIFIER, so every declaration contains
 * `settings/` and callers inside this directory import `../settings/x`.
 * (The wildcard pattern is spelled out in words: a literal star-slash would
 * close this comment.) `sdk` is `unknown` on purpose.
 */
declare module '*/settings/screen' {
  /** A theme's own inline pages, keyed like the rail. */
  interface OwnPages {
    inline?: Record<string, unknown>
  }

  interface ScreenParts {
    /** Drawn above the rail. Omitted by the built-in UI, which has its own. */
    TopBar?: unknown
    /** Extra class on the root, carrying this surface's palette. */
    skin?: string
    /** The theme's Home background component, drawn as the screen's ground. */
    Background?: unknown
    /** 'index': one page at a time behind a category list (Orbit). */
    layout?: 'rail' | 'index'
    /** L1/R1 change category when no dialog is open (Shelf). */
    pager?: boolean
    /** Where a network's or device's detail goes; absent is the legacy layout. */
    detail?: 'dialog' | 'inline'
  }

  export function createSettings(
    sdk: unknown,
    ownPages?: OwnPages,
    parts?: ScreenParts,
  ): (props: { onClose: () => void; initialCategory?: string }) => import('react').ReactNode
}

declare module '*/settings/power' {
  /**
   * The props are `PowerViewProps` from `modals/power/types`, but naming that
   * here would make this ambient declaration import from a component tree it
   * has no other business knowing about. The caller asserts the shape.
   */
  export function createPowerView(
    sdk: unknown,
    parts?: { skin?: string },
  ): (props: never) => import('react').ReactNode
}

declare module '*/settings/catalog' {
  export function createCatalogPage(
    sdk: unknown,
  ): (props: { active: boolean; onLeave: () => void }) => import('react').ReactNode
}

declare module '*/settings/themes' {
  export function createThemesPage(
    sdk: unknown,
    Rows: unknown,
  ): (props: { active: boolean; onLeave: () => void }) => import('react').ReactNode
}

declare module '*/settings/controllers' {
  export function createControllersPage(
    sdk: unknown,
    Rows: unknown,
  ): (props: { active: boolean; onLeave: () => void }) => import('react').ReactNode
}

declare module '*/settings/system' {
  export function createSystemPage(
    sdk: unknown,
    Rows: unknown,
  ): (props: { active: boolean; onLeave: () => void }) => import('react').ReactNode
}

declare module '*/settings/rows' {
  export function createRows(sdk: unknown): unknown
}

declare module '*/settings/bios' {
  /** The installed systems from `GET /bios`, the ones needing a file first. */
  export function biosRows<T extends { installed?: boolean; status: string; label: string }>(rows: T[]): T[]
  /** A system's verdict for its row: "Ready", "File missing", "2 files missing", "Wrong file". */
  export function systemVerdict(b: { status: string; files?: unknown[] }): string
  /** One file's state; `tone` is ok, bad, or quiet for an optional absent file. */
  export function fileVerdict(f: { status: string; required?: boolean; verified?: boolean }): { tone: 'ok' | 'bad' | 'quiet'; text: string }
  /** "4/6 ready", counting installed systems only. */
  export function biosSummary(rows: unknown): string
  export function createBiosPage(sdk: unknown): (props: { active: boolean; onLeave: () => void }) => import('react').ReactNode
}

declare module '*/settings/avatars' {
  /** [key stored in profiles.json, label, SVG path on a 24-unit grid]. */
  export const AVATARS: [string, string, string][]
  /** The letter drawn on a profile's colour when it has no picture. */
  export function initial(name: string): string
}

declare module '*/settings/profiles' {
  /** The letter drawn on a profile's colour when it has no picture. */
  export function initial(name: string): string
  /** Which systems keep a save per profile, as one sentence. */
  export function savesLine(separate: unknown, shared?: unknown): string
  export function createProfilesPage(
    sdk: unknown,
    Rows: unknown,
    Dialog: unknown,
  ): (props: { active: boolean; onLeave: () => void }) => import('react').ReactNode
}

declare module '*/settings/whoIsPlaying' {
  /** Props: `ViewProps` in components/WhoIsPlaying.tsx; the caller asserts the shape. */
  export function createWhoIsPlaying(
    sdk: unknown,
    parts?: { skin?: string },
  ): (props: never) => import('react').ReactNode
}

declare module '*/settings/dialog' {
  export function createDialogs(sdk: unknown): { Dialog: unknown; useDialogOpen: () => boolean }
}
