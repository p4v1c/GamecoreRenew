import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Builds shot/ only. Never part of `npm run build`.
export default defineConfig({
  plugins: [react()],
  root: 'shot',
  base: './',
  build: { outDir: '../.shot-dist', emptyOutDir: true },
})
