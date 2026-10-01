import {systemMark, systemName} from './catalog.js'
import {fold} from './collection.js'
import {isFavourite} from './favourites.js'

/** The query as words: lower case, accents gone, so "pokemon" finds "Pokémon". */
export const wordsOf = (query) => fold(query).split(/\s+/).filter(Boolean)

/** Games in the filter ('all', 'fav' or a system id) whose title or console
 * holds every word. */
export const searchGames = (games, words, filter) => games.filter((g) => {
  if (filter === 'fav' ? !isFavourite(g.systemId, g.gameKey) : filter !== 'all' && g.systemId !== filter) return false
  if (!words.length) return true
  const hay = fold(`${g.title} ${systemName(g.system)} ${systemMark(g.system)}`)
  return words.every((w) => hay.includes(w))
})
