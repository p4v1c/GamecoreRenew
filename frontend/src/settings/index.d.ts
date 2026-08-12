/**
 * Types for the two shared screens.
 *
 * They stay plain `.js` rather than becoming `.tsx`, and that is a decision
 * rather than an omission: they are written in the theme SDK's idiom — tagged
 * templates through `sdk.ui.html`, an sdk passed in rather than modules
 * imported — which is the idiom a theme author writes in and reads. Converting
 * them would make the host's copy and the thing themes are documented to write
 * two different languages, for no gain the box can see.
 *
 * A wildcard ambient module matches on the SPECIFIER, not on the file it
 * resolves to, so every declaration below has to contain `settings/` and a
 * caller inside this directory must write `../settings/x` rather than `./x`.
 * Ugly, and the alternative — a star-slash wildcard on the bare module name —
 * would claim every module called `catalog` anywhere in the tree.
 *
 * (Written out in words rather than shown: a star followed by a slash ENDS a
 * block comment, and writing the pattern literally here turned the rest of
 * this file into code. Second time in this repository.)
 *
 * So the boundary is typed instead of the bodies. `sdk` is `unknown` on
 * purpose: `ThemeSdk` is a bag of `Record<string, unknown>` fields, and
 * pretending these files consume a precise shape of it would be a claim the
 * compiler cannot check anyway.
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
