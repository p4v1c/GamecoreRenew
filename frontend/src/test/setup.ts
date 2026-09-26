/**
 * Vitest setupFiles: the browser APIs jsdom leaves out.
 *
 * Web Storage: recent Node defines its own `localStorage` global, undefined
 * without `--localstorage-file`, shadowing jsdom's. The UI reads storage on
 * every `gp:*` event (lib/sounds.ts) and for the theme crash counter
 * (themeSafety.ts), so without this "the pad does nothing". An in-memory
 * Storage, fresh per file, behaves like the real thing.
 */
function memoryStorage(): Storage {
  let data: Record<string, string> = {}
  return {
    get length() { return Object.keys(data).length },
    key: (i: number) => Object.keys(data)[i] ?? null,
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => { data[k] = String(v) },
    removeItem: (k: string) => { delete data[k] },
    clear: () => { data = {} },
  } as Storage
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  if (!globalThis[name]) {
    Object.defineProperty(globalThis, name, {
      value: memoryStorage(), configurable: true, writable: true,
    })
  }
}

/**
 * **The Gamepad API.** jsdom implements none of it, and `useGamepad` starts a
 * requestAnimationFrame loop that calls `navigator.getGamepads()` on its very
 * first frame. "No pad connected" is the honest default and is also the state
 * a box is in until one is paired; a test that wants a pad overrides this.
 */
if (typeof navigator !== 'undefined' && !navigator.getGamepads) {
  Object.defineProperty(navigator, 'getGamepads', {
    value: () => [], configurable: true, writable: true,
  })
}
