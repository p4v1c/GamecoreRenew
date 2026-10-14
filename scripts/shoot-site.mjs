#!/usr/bin/env node
// Re-shoot the website screenshots and every theme's preview.png from the
// themes as they are now, on made-up data, so they cannot drift from what the
// box draws.
//
//   node scripts/shoot-site.mjs                    # every theme
//   node scripts/shoot-site.mjs --themes shelf     # the themes whose look changed
//   node scripts/shoot-site.mjs --no-build         # reuse frontend/dist as it is
//
// Writes, per theme:
//   docs/img/themes/<theme>-home.webp, -controller.webp   1280x720, the website and README
//   config/themes/<theme>/preview.png                     640x360, the profile theme picker
// and docs/img/social.jpg (1200x630, Orbit's consoles) when Orbit is shot.
// A new preview.png is a change to the theme: bump its theme.json version.
//
// Needs python3 with backend/requirements.txt, and Playwright with Chromium
// (PLAYWRIGHT_MODULE=/path/to/node_modules/playwright if it is not resolvable).
// It starts the read-only dev server of the legibility skill on :8766, on a
// temporary data root, and stops it at the end. Nothing on the box is read:
// covers are drawn here and media refused, so no real box art reaches the website.
import { spawn, spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SKILL = join(ROOT, '.claude/skills/gamecore-legibility/scripts')
const BASE = 'http://127.0.0.1:8766'
const ALL = ['default', 'orbit', 'shelf', 'summer', 'jelly']
// A fixed afternoon: Summer draws the real hour, and "played 2 h ago" must not
// depend on when the script runs.
const SHOT_TIME = new Date('2026-07-14T16:20:00+02:00')
const TIMEZONE = 'Europe/Paris'

// Invented titles: no ROM names, no trademarks, no box art.
const GAMES = {
  azahar: ['Lantern Keep.3ds', 'Moss Rally.3ds', 'Paper Comets.3ds'],
  switch: ['Harbor Lights.xci', 'Tin Pilots.xci'],
  cemu: ['Orchard Quest.wux'],
  pcsx2: ['Night Ferry.iso', 'Cobalt Run.iso'],
  duckstation: ['Glass Garden.chd'],
  snes9x: ['Signal Hill.sfc', 'Pocket Tides.sfc'],
  gba: ['Ember Valley.gba'],
  melonds: ['Kite Season.nds'],
  megadrive: ['Velvet Circuit.md'],
  gopher64: ['Copper Canyon.z64'],
  dreamcast: ['Starling Bay.chd'],
}
// [system, game, hours played, hours since last played]
const PLAYED = [
  ['azahar', 'Lantern Keep.3ds', 3.4, 2], ['switch', 'Harbor Lights.xci', 11, 20],
  ['snes9x', 'Signal Hill.sfc', 2, 46], ['pcsx2', 'Cobalt Run.iso', 6, 94],
  ['gba', 'Ember Valley.gba', 1.2, 140],
]
// What each theme needs pressed to show its home the way the website does.
const HOME_KEYS = { orbit: ['r1'] }

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : undefined
}
const THEMES = (arg('themes') || ALL.join(',')).split(',').filter(Boolean)
const BUILD = !process.argv.includes('--no-build')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function loadPlaywright() {
  const require = createRequire(import.meta.url)
  for (const id of [process.env.PLAYWRIGHT_MODULE, 'playwright', '/opt/node22/lib/node_modules/playwright']) {
    if (!id) continue
    try { return require(id) } catch { /* next */ }
  }
  throw new Error('Playwright not found: npm i -g playwright, or set PLAYWRIGHT_MODULE')
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts })
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(' ')} failed (${r.status})`)
}

/** A data root with every system, a few invented games and some playtime. */
function makeFixture() {
  const data = mkdtempSync(join(tmpdir(), 'gc-site-'))
  mkdirSync(join(data, 'config'))
  cpSync(join(ROOT, 'install/generated/systems.json.dist'), join(data, 'config/systems.json'))
  cpSync(join(ROOT, 'install/generated/apps.json.dist'), join(data, 'config/apps.json'))
  cpSync(join(ROOT, 'config/themes'), join(data, 'config/themes'), { recursive: true })
  for (const [system, names] of Object.entries(GAMES)) {
    mkdirSync(join(data, 'emu', system), { recursive: true })
    for (const n of names) writeFileSync(join(data, 'emu', system, n), '')
  }
  const rows = PLAYED.map(([s, g, h, ago]) =>
    [g, s, Math.round(h * 3600), Math.ceil(h), new Date(SHOT_TIME - ago * 3600e3).toISOString()])
  // The backend's own schema, then the rows, as the box would have them.
  const seed = `
import asyncio, json, sys
from backend import db
async def main():
    await db.init_db()
    c = await db.get_db()
    await c.executemany("INSERT INTO playtime VALUES (?, ?, ?, ?, ?)", json.loads(sys.argv[1]))
    await c.commit()
    await c.close()
asyncio.run(main())`
  run('python3', ['-c', seed, JSON.stringify(rows)], { cwd: ROOT, env: env(data) })
  return data
}

function env(data) {
  return { ...process.env, GAMECORE_PATH: ROOT, GAMECORE_DATA: data, PYTHONPATH: ROOT,
    SCREENSCRAPER_DEV_ID: '', SCREENSCRAPER_USER: '', THEGAMESDB_API_KEY: '' }
}

async function startServer(data) {
  if (await fetch(`${BASE}/api/systems`).then(() => true, () => false)) {
    throw new Error(':8766 is already in use (another devserve?). Stop it first: its data is not this fixture.')
  }
  const server = spawn('python3', [join(SKILL, 'devserve.py')], { cwd: ROOT, env: env(data), stdio: 'ignore' })
  for (let i = 0; i < 60; i++) {
    await sleep(500)
    if (await fetch(`${BASE}/api/systems`).then((r) => r.ok, () => false)) return server
  }
  server.kill()
  throw new Error('devserve did not start (python3 -c "import fastapi, uvicorn, aiosqlite"?)')
}

async function setTheme(id) {
  const res = await fetch(`${BASE}/api/themes/active`, { method: 'POST',
    headers: { 'content-type': 'application/json', origin: BASE },
    body: JSON.stringify({ id: id === 'default' ? null : id }) })
  if (!res.ok) throw new Error(`theme switch to ${id} failed: ${res.status}`)
}

/** A plain printed jacket for an invented game: its title on a flat colour. */
function cover(url) {
  const name = decodeURIComponent(url.split('/').pop().split('?')[0]).replace(/\.[^.]+$/, '')
  const hues = [12, 205, 150, 36, 280, 340, 95, 190]
  const hue = hues[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % hues.length]
  const lines = name.toUpperCase().split(' ')
  const text = lines.map((w, i) => `<text x="28" y="${300 + i * 58}">${w}</text>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="560" viewBox="0 0 400 560">
<rect width="400" height="560" fill="hsl(${hue} 45% 34%)"/>
<circle cx="300" cy="150" r="96" fill="hsl(${hue} 55% 62%)"/>
<rect x="0" y="500" width="400" height="60" fill="hsl(${hue} 40% 22%)"/>
<g font-family="Arial, Helvetica, sans-serif" font-weight="900" font-size="52" fill="#fff">${text}</g></svg>`
}

/** Wait until the visible text stops changing: boot animation, theme load, entry motion. */
async function settle(page) {
  let last = ''
  for (let i = 0; i < 20; i++) {
    await sleep(i ? 1000 : 2500)
    const now = await page.evaluate(() => document.body?.innerText || '')
    if (now && now === last) break
    last = now
  }
  // Images still on their way (a console render) and the last motion.
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
  await page.evaluate(() => Promise.all([...document.images].map((i) => i.decode().catch(() => {}))))
  await sleep(1200)
}

async function shootTheme(browser, id) {
  await setTheme(id)
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, timezoneId: TIMEZONE, locale: 'en-GB' })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => console.warn(`  ${id}: page error: ${e.message}`))
  // The clock starts at SHOT_TIME and keeps running: a frozen Date stops the
  // themes' own entry motion (Summer's panels never arrive).
  await page.addInitScript(`(() => {
    const off = ${+SHOT_TIME} - Date.now(), RealDate = Date
    class ShotDate extends RealDate {
      constructor(...a) { a.length ? super(...a) : super(RealDate.now() + off) }
      static now() { return RealDate.now() + off }
    }
    window.Date = ShotDate
  })()`)
  await page.route('**/api/covers/**', (r) => r.fulfill({ status: 200, contentType: 'image/svg+xml', body: cover(r.request().url()) }))
  await page.route(/\/api\/media\/[^/]+\/[^/]+\/media\//, (r) => r.fulfill({ status: 404, body: '' }))
  await page.addInitScript(readFileSync(join(SKILL, 'fake-pads.js'), 'utf8'))
  await page.goto(`${BASE}/?pads=xbox,ds4`)
  await settle(page)
  const gp = (key) => page.evaluate((k) => window.dispatchEvent(new CustomEvent(`gp:${k}`)), key)
  for (const key of HOME_KEYS[id] || []) { await gp(key); await sleep(700) }
  await settle(page)
  const home = await page.screenshot()
  await gp('x')
  await settle(page)
  // A held ✕ lights up on the live diagram, which is what the screen is for.
  await page.evaluate(() => window.__hold(0))
  await sleep(500)
  const controller = await page.screenshot()
  await ctx.close()
  return { home, controller }
}

/** Re-encode a PNG through Chromium's own encoders: no image library needed. */
async function encode(browser, png, { width, height, type, quality, crop }) {
  const page = await browser.newPage()
  const b64 = await page.evaluate(async ({ src, width, height, type, quality, crop }) => {
    const img = new Image()
    img.src = src
    await img.decode()
    const c = document.createElement('canvas')
    c.width = width; c.height = height
    const g = c.getContext('2d')
    g.imageSmoothingQuality = 'high'
    const [sx, sy, sw, sh] = crop || [0, 0, img.width, img.height]
    g.drawImage(img, sx, sy, sw, sh, 0, 0, width, height)
    return c.toDataURL(type, quality).split(',')[1]
  }, { src: `data:image/png;base64,${png.toString('base64')}`, width, height, type, quality, crop })
  await page.close()
  return Buffer.from(b64, 'base64')
}

async function main() {
  const unknown = THEMES.filter((t) => !ALL.includes(t))
  if (unknown.length) throw new Error(`unknown theme(s): ${unknown.join(', ')} (one of ${ALL.join(', ')})`)
  if (BUILD) run('npx', ['vite', 'build', '--logLevel', 'warn'], { cwd: join(ROOT, 'frontend') })
  if (!existsSync(join(ROOT, 'frontend/dist/index.html'))) throw new Error('no frontend/dist: run without --no-build')
  const data = makeFixture()
  const server = await startServer(data)
  const { chromium } = loadPlaywright()
  const browser = await chromium.launch()
  const written = []
  const write = (rel, buf) => { writeFileSync(join(ROOT, rel), buf); written.push(rel) }
  try {
    for (const id of THEMES) {
      console.log(`shooting ${id}`)
      const { home, controller } = await shootTheme(browser, id)
      const webp = { width: 1280, height: 720, type: 'image/webp', quality: 0.82 }
      write(`docs/img/themes/${id}-home.webp`, await encode(browser, home, webp))
      write(`docs/img/themes/${id}-controller.webp`, await encode(browser, controller, webp))
      if (id !== 'default') {
        write(`config/themes/${id}/preview.png`,
          await encode(browser, home, { width: 640, height: 360, type: 'image/png' }))
      }
      // 1200x630 is 1.905:1; the 16:9 frame loses 72 px at the bottom (the hint bar).
      if (id === 'orbit') {
        write('docs/img/social.jpg', await encode(browser, home,
          { width: 1200, height: 630, type: 'image/jpeg', quality: 0.86, crop: [0, 0, 1920, 1008] }))
      }
    }
  } finally {
    await browser.close()
    server.kill()
    rmSync(data, { recursive: true, force: true })
  }
  console.log(`\nwrote:\n  ${written.join('\n  ')}`)
  const previews = THEMES.filter((t) => t !== 'default')
  if (previews.length) {
    console.log(`\nBump the theme.json version of: ${previews.join(', ')} (a new preview.png is a theme change),`)
    console.log('or `git checkout config/themes/<id>/preview.png` for a theme whose look did not change.')
  }
}

main().catch((e) => { console.error(`shoot-site: ${e.message}`); process.exit(1) })
