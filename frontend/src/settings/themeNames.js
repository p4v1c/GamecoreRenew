/**
 * A profile's theme by name ("Orbit theme"), for the profile cards and
 * "Who's using this controller?". The ids come from profiles.json; the names
 * from the theme index, read once per screen.
 */
export const useThemeNames = (sdk) => {
  const { useState, useEffect } = sdk.ui
  const [names, setNames] = useState({})
  useEffect(() => {
    let live = true
    const list = sdk.themes && sdk.themes.list
    if (!list) return undefined
    list().then((i) => {
      if (!live) return
      const out = {}
      for (const t of (i && i.themes) || []) out[t.id] = t.name
      setNames(out)
    }).catch(() => {})
    return () => { live = false }
  }, [])
  return (id) => (id == null ? 'Default' : names[id] || '')
}

/** "Orbit theme", or '' for a profile that has worn none yet or a theme gone since. */
export const wornTheme = (profile, themeName) => {
  if (!profile || !('theme' in profile)) return ''
  const name = themeName(profile.theme)
  return name ? `${name} theme` : ''
}
