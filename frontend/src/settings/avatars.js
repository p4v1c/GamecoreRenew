/**
 * The profile pictures a profile can pick: animal faces, drawn flat with a dark
 * outline so each one stands out on any of the profile colours, at 34 px in a
 * top bar as at 160 px on "Who's using this controller?".
 *
 * Each drawing is SVG markup on a 64-unit grid, inside a group that sets the
 * outline. Static strings from this file only, so setting them as innerHTML
 * never carries anything a player typed.
 *
 * The keys are what profiles.json stores; backend/services/profiles.py keeps
 * the same list to refuse anything else (a test holds the two together).
 */
const INK = '#2a211c'
const eyes = (y, dx = 8, r = 2.5) =>
  `<circle cx="${32 - dx}" cy="${y}" r="${r}" fill="${INK}" stroke="none"/><circle cx="${32 + dx}" cy="${y}" r="${r}" fill="${INK}" stroke="none"/>`
const blush = (y, dx = 12, fill = '#f4a3b4') =>
  `<circle cx="${32 - dx}" cy="${y}" r="2.8" fill="${fill}" stroke="none"/><circle cx="${32 + dx}" cy="${y}" r="2.8" fill="${fill}" stroke="none"/>`
const smile = (y) => `<path d="M32 ${y}q-2.4 3-5 1M32 ${y}q2.4 3 5 1" fill="none"/>`

export const AVATARS = [
  ['cat', 'Cat',
    '<path d="M14 28 13 9l14 9z" fill="#f2a541"/><path d="M50 28 51 9 37 18z" fill="#f2a541"/>'
    + '<path d="m16.5 14 .7 7 4.6-3.2z" fill="#f7c2b0" stroke="none"/><path d="m47.5 14-.7 7-4.6-3.2z" fill="#f7c2b0" stroke="none"/>'
    + '<ellipse cx="32" cy="35" rx="20" ry="17" fill="#f2a541"/>'
    + '<path d="M32 19v5M26.5 20.5l1.2 3.8M37.5 20.5l-1.2 3.8" fill="none"/>'
    + '<ellipse cx="32" cy="42" rx="9" ry="6.5" fill="#fff4e6"/>'
    + `${eyes(33)}<path d="M30 38.5h4l-2 2.4z" fill="#e0607e"/>${smile(40.9)}`
    + '<path d="M19 40l-8-1M19 43l-7 2M45 40l8-1M45 43l7 2" fill="none" stroke-width="1.6"/>'],
  ['dog', 'Dog',
    '<ellipse cx="32" cy="34" rx="17" ry="18" fill="#e9c48f"/>'
    + '<path d="M36.5 24.5q6.5-2.5 7.5 6-4 4.5-8 0z" fill="#8b5a3c" stroke="none"/>'
    + '<path d="M18 19C8 21 7 38 12 45c5 2 8-6 8-15z" fill="#8b5a3c"/><path d="M46 19c10 2 11 19 6 26-5 2-8-6-8-15z" fill="#8b5a3c"/>'
    + `<ellipse cx="32" cy="43" rx="10" ry="8" fill="#fff4e6"/>${eyes(31)}`
    + `<ellipse cx="32" cy="39" rx="3.8" ry="2.7" fill="${INK}"/><path d="M32 41.5v3M28 45.5q4 3 8 0" fill="none"/>`],
  ['fox', 'Fox',
    '<path d="M13 30 11 8l17 12z" fill="#e8742c"/><path d="M51 30 53 8 36 20z" fill="#e8742c"/>'
    + `<path d="m14.5 22-.8-9.5 7.6 5.8z" fill="${INK}" stroke="none"/><path d="m49.5 22 .8-9.5-7.6 5.8z" fill="${INK}" stroke="none"/>`
    + '<path d="M9 29c2-10 13-13 23-13s21 3 23 13c-2 10-12 20-23 26C21 49 11 39 9 29z" fill="#e8742c"/>'
    + '<path d="M10 30c8 1 17 7 22 25C21 49 12 40 10 30zM54 30c-8 1-17 7-22 25 11-6 20-15 22-25z" fill="#fff4e6"/>'
    + `${eyes(30)}<circle cx="32" cy="50.5" r="2.8" fill="${INK}"/>`],
  ['bear', 'Bear',
    '<circle cx="16" cy="18" r="7.5" fill="#9a6b45"/><circle cx="48" cy="18" r="7.5" fill="#9a6b45"/>'
    + '<circle cx="16" cy="18" r="3.4" fill="#d9a877" stroke="none"/><circle cx="48" cy="18" r="3.4" fill="#d9a877" stroke="none"/>'
    + '<circle cx="32" cy="35" r="19" fill="#9a6b45"/><ellipse cx="32" cy="42" rx="9.5" ry="7.5" fill="#e6c19a"/>'
    + `${eyes(31)}<ellipse cx="32" cy="38.5" rx="3.8" ry="2.7" fill="${INK}"/>`
    + '<path d="M32 41v2.6M28.5 45q3.5 2.6 7 0" fill="none"/>'],
  ['panda', 'Panda',
    `<circle cx="16" cy="19" r="7.5" fill="${INK}"/><circle cx="48" cy="19" r="7.5" fill="${INK}"/>`
    + '<circle cx="32" cy="35" r="19" fill="#ffffff"/>'
    + `<ellipse cx="24" cy="33" rx="5" ry="6.8" transform="rotate(28 24 33)" fill="${INK}" stroke="none"/>`
    + `<ellipse cx="40" cy="33" rx="5" ry="6.8" transform="rotate(-28 40 33)" fill="${INK}" stroke="none"/>`
    + '<circle cx="24.6" cy="32" r="1.9" fill="#fff" stroke="none"/><circle cx="39.4" cy="32" r="1.9" fill="#fff" stroke="none"/>'
    + `<ellipse cx="32" cy="40.5" rx="3.4" ry="2.4" fill="${INK}"/><path d="M32 43v2M29 46q3 2 6 0" fill="none"/>`],
  ['rabbit', 'Rabbit',
    '<ellipse cx="24" cy="18" rx="5.6" ry="13" fill="#ece7e3"/><ellipse cx="40" cy="18" rx="5.6" ry="13" fill="#ece7e3"/>'
    + '<ellipse cx="24" cy="18" rx="2.4" ry="9" fill="#f4a3b4" stroke="none"/><ellipse cx="40" cy="18" rx="2.4" ry="9" fill="#f4a3b4" stroke="none"/>'
    + '<ellipse cx="32" cy="41" rx="17" ry="14.5" fill="#ece7e3"/>'
    + `${eyes(39, 7)}${blush(45, 11)}<path d="M30 43.5h4l-2 2.2z" fill="#e0607e"/>${smile(45.7)}`],
  ['owl', 'Owl',
    '<path d="M14 21 17 9l9 8q6-2 12 0l9-8 3 12q5 16-4 28-14 9-28 0-9-12-4-28z" fill="#8d6e52"/>'
    + '<circle cx="24" cy="29" r="8.5" fill="#f3e3c7"/><circle cx="40" cy="29" r="8.5" fill="#f3e3c7"/>'
    + `<circle cx="24" cy="29" r="3.8" fill="${INK}"/><circle cx="40" cy="29" r="3.8" fill="${INK}"/>`
    + '<circle cx="25.3" cy="27.7" r="1.2" fill="#fff" stroke="none"/><circle cx="41.3" cy="27.7" r="1.2" fill="#fff" stroke="none"/>'
    + '<path d="M29 36h6l-3 5.5z" fill="#f2a541"/>'
    + '<path d="M24 46q2 2 4 0 2 2 4 0 2 2 4 0 2 2 4 0" fill="none" stroke-width="1.8"/>'],
  ['frog', 'Frog',
    '<ellipse cx="32" cy="39" rx="21" ry="15" fill="#6dbb5a"/>'
    + '<circle cx="21" cy="23" r="8" fill="#6dbb5a"/><circle cx="43" cy="23" r="8" fill="#6dbb5a"/>'
    + '<circle cx="21" cy="23" r="4.8" fill="#fff"/><circle cx="43" cy="23" r="4.8" fill="#fff"/>'
    + `<circle cx="21.5" cy="23.6" r="2.4" fill="${INK}" stroke="none"/><circle cx="42.5" cy="23.6" r="2.4" fill="${INK}" stroke="none"/>`
    + `${blush(42, 15)}<circle cx="29" cy="35" r="1" fill="${INK}" stroke="none"/><circle cx="35" cy="35" r="1" fill="${INK}" stroke="none"/>`
    + '<path d="M21 41q11 9 22 0" fill="none"/>'],
  ['penguin', 'Penguin',
    '<ellipse cx="32" cy="34" rx="19" ry="20" fill="#2f3a4a"/>'
    + '<path d="M32 26c-6-8-16-4-15 7s9 17 15 17 14-6 15-17-9-15-15-7z" fill="#ffffff"/>'
    + `${eyes(33, 7)}${blush(40, 10.5)}<path d="M27.5 38.5q4.5-2 9 0-4.5 6-9 0z" fill="#f2a541"/>`],
  ['lion', 'Lion',
    '<path d="M54 34a6 6 0 0 1-2.9 11A6 6 0 0 1 43 53.1 6 6 0 0 1 32 56a6 6 0 0 1-11-2.9A6 6 0 0 1 12.9 45 6 6 0 0 1 10 34a6 6 0 0 1 2.9-11A6 6 0 0 1 21 14.9 6 6 0 0 1 32 12a6 6 0 0 1 11 2.9A6 6 0 0 1 51.1 23 6 6 0 0 1 54 34z" fill="#c9772f"/>'
    + '<circle cx="20.5" cy="22" r="5" fill="#f2c46d"/><circle cx="43.5" cy="22" r="5" fill="#f2c46d"/>'
    + '<circle cx="32" cy="35" r="15" fill="#f2c46d"/><ellipse cx="32" cy="41.5" rx="7.5" ry="5.5" fill="#fff4e6"/>'
    + `${eyes(33, 6.5, 2.3)}<path d="M29.5 38.2h5l-2.5 2.7z" fill="#7a4524"/>${smile(40.9)}`],
  ['koala', 'Koala',
    '<circle cx="14.5" cy="25" r="10" fill="#9aa3ad"/><circle cx="49.5" cy="25" r="10" fill="#9aa3ad"/>'
    + '<circle cx="14.5" cy="25" r="5.5" fill="#f1e4ea" stroke="none"/><circle cx="49.5" cy="25" r="5.5" fill="#f1e4ea" stroke="none"/>'
    + '<circle cx="32" cy="36" r="17" fill="#9aa3ad"/>'
    + `${eyes(32, 7.5, 2.3)}<ellipse cx="32" cy="40" rx="4.6" ry="6.2" fill="${INK}"/>`],
]

const DRAWINGS = Object.fromEntries(AVATARS.map(([key, , body]) => [key, body]))

/** The whole drawing as an `<svg>` string, or '' for a key with no drawing
 *  (none, or a picture from an older version). */
export const avatarSvg = (key) => {
  const body = key && DRAWINGS[key]
  return body
    ? `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><g stroke="${INK}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${body}</g></svg>`
    : ''
}

/** The letter drawn on a profile's colour when it has no picture. */
export const initial = (name) => (Array.from(String(name || '').trim())[0] || '?').toUpperCase()

/** What goes inside the round: the picture, else the initial. */
export const avatarFace = (html, profile) => {
  const svg = avatarSvg(profile && profile.avatar)
  if (!svg) return initial(profile && profile.name)
  return html`<span class="gcs-animal" dangerouslySetInnerHTML=${{ __html: svg }} />`
}
