import {isApp, onFavouritesChange, titleFromKey} from '../../lib/catalog.js'

export function createHomeHooks(sdk, tabs, systemsRef) {
  const {useState, useEffect, useRef} = sdk.ui

  /** An installed collection, with recently played games first and a bounded rail. */
  function useRecent(systems) {
    const [rows, setRows] = useState([])
    useEffect(() => {
      let live = true
      Promise.all([
        sdk.api.playtime.all().catch(() => []),
        Promise.all(systems.filter(s => !isApp(s)).map(async system => {
          const games = await sdk.api.games.list(system.id).catch(() => [])
          return Array.isArray(games) ? games.map(game => ({...game, system})) : []
        })),
      ]).then(([entries, libraries]) => {
        if (!live) return
        const history = new Map(entries.map(e => [`${e.system_id}:${e.game_key}`, e]))
        const installed = libraries.flat().filter(g => g.filename)
        setRows(installed.map(game => {
          const key = `${game.system.id}:${game.filename}`
          const played = history.get(key)
          return {key, gameKey: game.filename, systemId: game.system.id, system: game.system,
            title: game.display_name || titleFromKey(sdk, game.filename), ext: game.ext,
            seconds: played?.total_secs || 0, lastPlayed: played?.last_played || null}
        }).sort((a, b) => String(b.lastPlayed || '').localeCompare(String(a.lastPlayed || ''))
          || a.title.localeCompare(b.title)).slice(0, 6))
      }).catch(() => {})
      return () => {live = false}
    }, [systems])
    return rows
  }

  /** The metadata panel of the hero, for whichever game is selected. */
  function useGameMeta(item) {
    const [meta, setMeta] = useState(null)
    useEffect(() => {
      setMeta(null)
      if (!item) return
      let live = true
      sdk.api.metadata.get(item.systemId, item.gameKey)
        .then((m) => {if (live && m?.found) setMeta(m)})
        .catch(() => { /* no metadata is a shorter hero, not an error */ })
      return () => {live = false}
    }, [item?.key])
    return meta
  }

  function useFavourites() {
    const [, bump] = useState(0)
    useEffect(() => onFavouritesChange(() => bump((n) => n + 1)), [])
  }

  /** One binding set for whichever home tab is on screen.
   *
   * The host's own d-pad, L1/R1 and ✕ are dropped for this screen (`homeOmit`
   * in index.js), so these are not competing with anything — which is the whole
   * reason for dropping them. Registered once and reading the live tab, so a
   * tab change does not tear listeners down and rebuild them.
   */
  function useHomeKeys(move, open, owns) {
    const live = useRef({move, open, owns})
    live.current = {move, open, owns}

    // Bumped by every rail step the pad makes, and read by the effect below.
    //
    // The point is *when* that effect runs. `setIdx` and this counter are set
    // in the same dispatch, so React batches them into one commit and the
    // effect fires with the new tile already in the DOM. A `setTimeout(…, 0)`
    // cannot promise that: React 18 is free to leave a low-priority render for
    // a later task, and focusing on the next one lands on the tile we just
    // left — whose `onFocus` sets the selection straight back to where it was.
    // That is a stuck cursor on the box, not only a red test.
    const [moved, setMoved] = useState(0)
    const sectionOf = () => document.getElementById(
      `${live.current.owns === 'home' ? 'home' : live.current.owns}-view`)

    useEffect(() => {
      if (!moved) return
      sectionOf()?.querySelector('[data-active="true"]')?.focus({preventScroll: true})
    }, [moved])

    useEffect(() => {
      const mine = () => {
        const s = sdk.nav.get()
        return s.screen === 'home' && !s.modalDepth && !s.sessionGameKey
          && !s.powerPending && s.standby === 'off' && tabs.get() === live.current.owns
      }
      const section = sectionOf
      const actions = () => [...(section()?.querySelectorAll('.hero-actions button,.application-copy button,.console-story button') || [])]
      const focusRow = direction => {
        const el = direction > 0 ? actions()[0] : section()?.querySelector('[data-active="true"]')
        el?.focus({preventScroll: true})
      }
      const horizontal = direction => {
        const buttons = actions(), at = buttons.indexOf(document.activeElement)
        if (at >= 0) buttons[(at + direction + buttons.length) % buttons.length]?.focus()
        else {
          // Not on an action button, so the rail owns this press. Move it, and
          // ask for DOM focus to follow the selection once React has committed.
          live.current.move(direction)
          setMoved((n) => n + 1)
        }
      }
      const offs = [
        sdk.input.onGp('gp:dpad-left', () => {if (mine()) horizontal(-1)}),
        sdk.input.onGp('gp:dpad-right', () => {if (mine()) horizontal(1)}),
        sdk.input.onGp('gp:dpad-up', () => {if (mine()) focusRow(-1)}),
        sdk.input.onGp('gp:dpad-down', () => {if (mine()) focusRow(1)}),
        sdk.input.onGp('gp:confirm', () => {if (mine()) {
          const el = document.activeElement
          if (el?.matches('.hero-actions button,.application-copy button,.console-story button')) el.click()
          else live.current.open()
        }}),
        sdk.input.onGp('gp:back', () => {if (mine()) tabs.go('home', systemsRef.current)}),
        sdk.input.onGp('gp:l1', () => {if (mine()) tabs.step(-1, systemsRef.current)}),
        sdk.input.onGp('gp:r1', () => {if (mine()) tabs.step(1, systemsRef.current)}),
      ]
      return () => offs.forEach((off) => off())
    }, [])
  }

  return {useRecent, useGameMeta, useFavourites, useHomeKeys}
}
