/** The host's library rows in the shape every Jelly card takes. `index` is the
 * row's place in the host's list, which is what `onSelect` expects. */
export const libraryRows = (sdk, {games, playtime, systemId, system}) => games.map((g, i) => {
  const sid = g.system_id || systemId
  const p = playtime?.[systemId === '__all__' ? `${sid}:${g.filename}` : g.filename]
  return {kind: 'game', key: `${sid}:${g.filename}`, systemId: sid, system, gameKey: g.filename,
    path: g.path, title: g.display_name || sdk.format.gameName(g.filename), ext: g.ext,
    seconds: p?.total_secs || 0, lastPlayed: p?.last_played || null, index: i}
})
