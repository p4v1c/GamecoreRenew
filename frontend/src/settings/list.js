/**
 * `asList` — an answer that should have been an array, made into one.
 *
 * Every page on this screen has at least one endpoint that returns a list, and
 * every one of them stored the answer and mapped over it. That was fine while
 * this screen belonged to a theme: a theme that crashed got swapped out for the
 * built-in UI, and the player still had a settings screen.
 *
 * It is not fine now. This IS the built-in UI's settings screen — safe mode's
 * fallback — and there is nothing behind it. A backend that answers `{"detail":
 * ...}` on a validation error, or `{}` from a proxy, or `null` from a service
 * that is still starting, would take the screen down with `x.map is not a
 * function` before it drew a single row. The player would have no way back to
 * the Themes page, which is very often why they opened it.
 *
 * So: not an array means no rows, which is what every one of these pages
 * already renders honestly ("No network is in range", "Nothing installed"). An
 * empty list is a true statement about an answer nobody can read; a crash is
 * not a statement at all.
 *
 * Deliberately NOT a value-invention helper. It maps unusable to empty, never
 * to a plausible-looking default — the same rule the rest of this screen keeps
 * about showing nothing rather than a dash.
 */
export const asList = (v) => (Array.isArray(v) ? v : [])

/**
 * A version as the player reads it: one `v`, whatever the box answered.
 *
 * The tag an installed box writes to VERSION already carries its `v`
 * (`v1.2.60`), and every screen that printed `v${version}` showed "vv1.2.60".
 * Normalised here rather than in the backend, because other callers compare
 * that string against release tags as it is.
 */
export const versionLabel = (v) => (v ? `v${String(v).replace(/^v/i, '')}` : '')
