/**
 * Reading a ROM filename the way a collector reads a box.
 *
 * The shelf shows two things the default library does not: the letter a game
 * files under, and the region its box was printed for. Both come out of the
 * filename — `Chrono Trigger (USA).sfc` is a North American NTSC cartridge, and
 * it lives under C. Neither is worth a round trip, so neither makes one.
 *
 * The host has its own `formatGameName`, which strips *trailing* region words.
 * This one also strips the parenthesised and bracketed tags that dumps carry
 * mid-string, because a spine 30 pixels wide has room for the title and nothing
 * else.
 */

/** Trailing extension, then every (…) and […] group, then the leftovers. */
export const title = (raw) => {
  const s = String(raw || '')
  const out = s
    .replace(/\.[a-z0-9]{1,5}$/i, '')
    .replace(/[\(\[][^\)\]]*[\)\]]/g, ' ')
    .replace(/[_]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s*[-–—]\s*$/, '')
    .trim()
  // Never return nothing: a file called "(USA).sfc" still needs a label.
  return out || s
}

/**
 * The index letter. Articles are not stripped — "The Legend of Zelda" files
 * under L in every No-Intro set and under T on a real shelf, and the host sorts
 * on the raw title, so following the host is the only answer that keeps the
 * rail in step with the list.
 */
export const initial = (name) => {
  const c = title(name).trim().charAt(0).toUpperCase()
  return c >= 'A' && c <= 'Z' ? c : '#'
}

export const LETTERS = ['#', ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))]

/**
 * Region and TV standard, from the tags a dump carries.
 *
 * Order matters: `(Japan, USA)` is a dual release that ran on NTSC sets in
 * both, so Japan is checked first only to name the *box*, and the standard is
 * NTSC either way. Anything unrecognised gets no badge rather than a guess —
 * a wrong region on a collector's screen is worse than a missing one.
 */
const REGIONS = [
  [/\b(usa|u\.s\.a|america|north america|\(u\)|ntsc-u)\b/i, 'North America', 'NTSC'],
  [/\b(japan|jpn|\(j\)|ntsc-j)\b/i, 'Japan', 'NTSC'],
  [/\b(europe|eur|\(e\)|pal)\b/i, 'Europe', 'PAL'],
  [/\b(world|international|global)\b/i, 'World', 'NTSC'],
  [/\b(australia|aus)\b/i, 'Australia', 'PAL'],
  [/\b(korea|kor)\b/i, 'Korea', 'NTSC'],
  [/\b(brazil|bra)\b/i, 'Brazil', 'PAL-M'],
  [/\b(china|chn|taiwan|asia)\b/i, 'Asia', 'NTSC'],
  [/\b(france|germany|spain|italy|sweden|netherlands)\b/i, 'Europe', 'PAL'],
]

export const stamp = (filename) => {
  const tags = String(filename || '').match(/[\(\[][^\)\]]*[\)\]]/g)?.join(' ') || ''
  for (const [re, region, std] of REGIONS) {
    if (re.test(tags)) return { region, std }
  }
  return { region: null, std: null }
}

/** "Nov 1991" from an ISO date, "1991" from a bare year, "—" from nothing. */
export const released = (meta) => {
  const iso = meta?.released || ''
  const m = /^(\d{4})-(\d{2})/.exec(iso)
  if (m) {
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return `${MONTHS[Number(m[2]) - 1] || ''} ${m[1]}`.trim()
  }
  if (/^\d{4}$/.test(iso)) return iso
  return meta?.year || '—'
}

/** Playtime, in the shortest form that is still exact enough to be useful. */
export const played = (secs) => {
  if (!secs) return '—'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m`
}

export const day = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
}
