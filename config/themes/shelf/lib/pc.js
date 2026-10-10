/**
 * Which systems are PC games, drawn in the PC case (views/pc-case.js) rather
 * than a console's box and cartridge.
 *
 * Keyed by pack id like everything else in this theme. `lutris` is the pack
 * that will bring the PC library in; `pc` is held for a plain folder of games.
 */
const PC_SYSTEMS = new Set(['lutris', 'pc'])

export const isPc = (systemId) => PC_SYSTEMS.has(String(systemId || '').toLowerCase())
