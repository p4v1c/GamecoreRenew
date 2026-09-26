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
  ): (props: { onClose: () => void }) => import('react').ReactNode
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

declare module '*/settings/rows' {
  export function createRows(sdk: unknown): unknown
}
