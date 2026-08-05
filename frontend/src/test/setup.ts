/**
 * Test environment setup — the browser APIs jsdom leaves out.
 *
 * Registered as vitest's `setupFiles`, so it runs once per test file before
 * any test.
 *
 * **Web Storage.** Recent Node versions ship their own experimental
 * `localStorage` global, and it resolves to undefined unless the process was
 * started with `--localstorage-file`. It shadows the working one jsdom builds,
 * so the test environment ends up with the name defined and the API absent —
 * which no browser ever does.
 *
 * That matters because the UI reads storage on paths that have nothing to do
 * with storage: `lib/sounds.ts` reads it on EVERY `gp:*` event to decide
 * whether to play a click, and `lib/themeSafety.ts` keeps the crash counter
 * that stops a broken theme from bricking the box there.
 *
 * Without this the failure is badly misleading: the throw happens inside
 * `emit()`, before the CustomEvent is dispatched, so the symptom is "the pad
 * does nothing" and the stack points at a sound file. It is worth knowing that
 * this is also the real-browser failure mode if storage is ever unavailable —
 * `themeSafety` guards every access, `sounds` does not.
 *
 * A plain in-memory Storage, not a mock: tests assert on what the UI stored,
 * so it has to behave like the real thing, and each file gets a fresh one.
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
