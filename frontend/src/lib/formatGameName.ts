const REGION_RE = /\s+(?:World|Europe?|EUR?|USA?|NTSC|PAL|Japan|JPN?|Australia|AUS?|Korea|KOR?|China|CHN?|France|Germany|Spain|Italy|Global|International|En|Rev\s*\d+|v\d+\.\d+)\s*$/i

// Sequences of 2+ camelCase language pairs: En, Fr, De, Es, It, Ja, Ko… optionally ending in Z
const LANG_SEQ_RE = /\s+(?:[A-Z][a-z]){2,}Z?\s*$/

export function formatGameName(raw: string): string {
  let name = raw.replace(/_/g, ' ').trim()

  // Strip trailing language codes first (they appear after the region)
  name = name.replace(LANG_SEQ_RE, '').trim()

  // Strip trailing region name
  name = name.replace(REGION_RE, '').trim()

  // Strip again in case of leftover (e.g. "Name Region1 Region2")
  name = name.replace(LANG_SEQ_RE, '').trim()
  name = name.replace(REGION_RE, '').trim()

  return name
}
