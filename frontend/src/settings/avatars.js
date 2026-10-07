/**
 * The profile pictures a profile can pick, drawn white on the profile's colour.
 * Line drawings on a 24-unit grid, the same stroke as the settings icons, so a
 * picture reads at 36 px in a top bar and at 160 px on "Who's playing?".
 *
 * The keys are what profiles.json stores; backend/services/profiles.py keeps
 * the same list to refuse anything else (a test holds the two together).
 */
export const AVATARS = [
  ['controller', 'Controller', 'M7 9h10a4 4 0 0 1 3.9 4.9l-.6 2.6a2 2 0 0 1-3.4.9L15 15H9l-1.9 2.4a2 2 0 0 1-3.4-.9l-.6-2.6A4 4 0 0 1 7 9zM8 11.5v3M6.5 13h3M15.5 12.5h.01M17.5 14h.01'],
  ['star', 'Star', 'M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8-4.2-4.1 5.9-.9z'],
  ['heart', 'Heart', 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z'],
  ['bolt', 'Bolt', 'M13 3 5 14h6l-1 7 8-11h-6z'],
  ['leaf', 'Leaf', 'M5 19c0-8 5-13 14-14-1 9-6 14-14 14zM5 19l7-7'],
  ['moon', 'Moon', 'M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z'],
  ['rocket', 'Rocket', 'M12 3c3 2 5 5.5 5 9.5L15 16H9l-2-3.5C7 8.5 9 5 12 3zM12 9.5h.01M9 16l-2 4 3-1M15 16l2 4-3-1'],
  ['cat', 'Cat', 'M5 20v-9L4 5l4.5 3h7L20 5l-1 6v9zM9.5 13h.01M14.5 13h.01M11 16.5h2'],
]

const PATHS = Object.fromEntries(AVATARS.map(([key, , d]) => [key, d]))

/** The letter drawn on a profile's colour when it has no picture. */
export const initial = (name) => (Array.from(String(name || '').trim())[0] || '?').toUpperCase()

/** What goes inside the round: the picture, else the initial. */
export const avatarFace = (html, profile) => {
  const d = profile && PATHS[profile.avatar]
  if (!d) return initial(profile && profile.name)
  return html`<svg viewBox="0 0 24 24" width="62%" height="62%" aria-hidden="true" fill="none"
    stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d=${d} /></svg>`
}
