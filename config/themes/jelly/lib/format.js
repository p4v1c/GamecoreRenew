/** Playtime and "last played" in the host's words (`sdk.format.time` /
 * `date`), so Jelly never disagrees with the rest of the box. */
export const duration = (sdk, secs) => (secs > 0 ? sdk.format.time(secs) : 'Never played')

export const lastPlayed = (sdk, iso) => (iso ? sdk.format.date(iso) : 'Never played')
