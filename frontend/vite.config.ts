/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // The test runner shares this config so a test resolves imports exactly the
  // way the bundle does. A second resolver is a second set of answers, and the
  // one that disagrees is always the one not being watched.
  test: {
    // jsdom, not happy-dom: the store and the gamepad bus talk to `window`
    // and to CustomEvent, and this is the environment the box's Electron
    // renderer is closest to.
    environment: 'jsdom',
    // A real origin, because jsdom only exposes localStorage on a document
    // that has one — on about:blank it is undefined. The UI reads it without a
    // guard on the navigation path (lib/sounds.ts on every gp:* event, and the
    // theme crash counter), so a test environment without it does not fail
    // where the code touches storage: it fails somewhere else entirely, with
    // the pad appearing to do nothing.
    environmentOptions: { jsdom: { url: 'http://localhost/' } },
    setupFiles: ['./src/test/setup.ts'],
    // No `globals: true`: every test imports describe/it/expect from vitest
    // explicitly. Ambient globals would need a `types` entry in tsconfig.json,
    // and `npm run build` runs tsc over src/ — including these files — so the
    // cheapest way to keep the build honest is to import what is used.
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
  server: {
    // The bundled themes live in ../config/themes, outside this package. The
    // acceptance test imports one of them — the default UI rebuilt as an
    // ordinary theme — and runs it against the real SDK, which is only worth
    // doing if it is the shipped files being loaded and not a copy.
    //
    // Dev-server only. On the box the backend serves /themes itself, and this
    // config is not involved.
    fs: { allow: ['..'] },
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8765',
      '/ws':  { target: 'ws://localhost:8765', ws: true },
      '/covers': 'http://localhost:8765',
      '/assets': 'http://localhost:8765',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
