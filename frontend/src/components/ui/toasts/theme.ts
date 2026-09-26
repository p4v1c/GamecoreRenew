import contract from '../../../../../electron/hud-tokens.json'

/** Read at notification time: theme switches must not leave stale IPC tokens. */
export function readHudTheme(): Record<string, string> {
  const css = getComputedStyle(document.documentElement)
  const result: Record<string, string> = {}
  for (const [key, kind] of Object.entries(contract.tokens)) {
    const value = css.getPropertyValue(`--gc-hud-${key}`).trim()
    if (value.length <= 160 && new RegExp(contract.patterns[kind as keyof typeof contract.patterns]).test(value)) {
      result[key] = value
    }
  }
  // A light panel without severity overrides must still have readable text.
  const rgb = result.panel?.slice(1, 7).match(/../g)?.map(v => {
    const n = parseInt(v, 16) / 255
    return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4
  })
  if (rgb && 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] > 0.45) {
    return { ...contract.lightDefaults, ...result }
  }
  return result
}

export function batteryNotice(level: number, player: number | null) {
  const stage = contract.battery.find(s => level <= s.threshold) || contract.battery[3]
  const who = player ? `Controller ${player}` : 'Controller'
  return { icon: 'gamepad', title: `${who} battery at ${Math.round(level)}%`,
    body: stage.message, accent: stage.color, tone: `battery-${stage.threshold}` }
}
