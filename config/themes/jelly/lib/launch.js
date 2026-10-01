/** Resume a game frozen in the background, else launch it through the host.
 * The one path every Jelly "Play" button takes. */
export function playOrResume(sdk, game, background) {
  const held = heldSession(background, game)
  if (held) return sdk.session.resume(held.session)
  return sdk.defaults.launchGame({systemId: game.systemId, path: game.path, gameKey: game.gameKey})
}

/** The background session of this game, or null. */
export const heldSession = (background, game) => background.find((s) =>
  s.gameKey === game.gameKey && s.systemId === game.systemId) || null

/** An error the player can read: the host's sentence, else a plain one. */
export const launchError = (e) => e?.message || 'Le jeu n’a pas démarré. Réessaie, ou regarde Réglages, BIOS.'
