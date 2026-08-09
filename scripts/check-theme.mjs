#!/usr/bin/env node
// Load every module of a theme the way the browser will.
//
//     node scripts/check-theme.mjs config/themes/<id>
//
// `node --check` is not enough and this is the whole reason the script exists.
// It parses one file in isolation, and the failure that actually happens looks
// like valid JavaScript to it: a backtick inside an HTML comment inside an
// html`` template closes the template early. The file parses; the module
// explodes the moment it is loaded, and the theme is disabled at runtime with
// "Unexpected identifier". It has bitten twice.
//
// Importing is the test. A module that parses, imports. Anything thrown that
// is NOT a SyntaxError means the module was read fine and only its runtime
// needs an SDK we are not providing here — which is not what we are asking.
import { readdirSync, readFileSync, statSync } from 'fs'
import { join, resolve } from 'path'
import { pathToFileURL } from 'url'

const root = resolve(process.argv[2] || '.')
const files = []
;(function walk(d) {
  for (const e of readdirSync(d)) {
    const p = join(d, e)
    if (statSync(p).isDirectory()) walk(p)
    else if (p.endsWith('.js')) files.push(p)
  }
})(root)

let bad = 0
for (const f of files.sort()) {
  try {
    await import(pathToFileURL(f).href)
    console.log(`  ok  ${f.slice(root.length + 1)}`)
  } catch (e) {
    // A missing SDK is not a syntax error: the module was parsed, which is
    // all this asks.
    const msg = String(e && e.message)
    if (e instanceof SyntaxError) { bad++; console.log(`  FAIL ${f.slice(root.length + 1)} — ${msg}`) }
    else console.log(`  ok  ${f.slice(root.length + 1)}  (${e.constructor.name} at run time, not at parse)`)
  }
}
console.log(`\n  ${files.length} modules, ${bad} syntax error(s)`)

// ── Unreachable settings pages ───────────────────────────────────────────────
//
// A theme that builds its own settings menu resolves each entry through
// `sdk.defaults.DefaultSettingsPages`. Leaving one out costs nothing at load
// and is invisible on screen: the page exists, the route exists, and nothing
// can open it. That has shipped twice — `catalog`, so neither bundled theme
// could install an emulator, and `storage`, which was missing from the map
// itself so no theme could have offered safe-eject at all.
//
// The full list lives in the frontend, in TypeScript this script cannot import.
// Read as source rather than duplicated here: a copy would be the third time
// the same list drifted.
const PAGES_SRC = resolve(import.meta.dirname, '../frontend/src/components/defaults.tsx')

function hostPages() {
  const src = readFileSync(PAGES_SRC, 'utf8')
  const block = src.match(/export const DefaultSettingsPages = \{([\s\S]*?)\n\}/)
  if (!block) return null
  return [...block[1].matchAll(/^\s{2}([a-z][a-z0-9_-]*):/gm)].map(m => m[1])
}

let unreachable = 0
try {
  const manifest = JSON.parse(readFileSync(join(root, 'theme.json'), 'utf8'))
  const pages = hostPages()

  if (!pages?.length) {
    // Loud, because the alternative is a check that silently passes forever.
    console.log(`\n  WARN could not read DefaultSettingsPages from ${PAGES_SRC}`)
  } else if (Array.isArray(manifest.settings?.pages)) {
    const declared = new Set(manifest.settings.pages)
    const missing = pages.filter(p => !declared.has(p))
    const unknown = [...declared].filter(p => !pages.includes(p))
    for (const p of missing) console.log(`  UNREACHABLE  settings page "${p}" is in no menu entry`)
    for (const p of unknown) console.log(`  UNKNOWN      settings page "${p}" does not exist in this build`)
    unreachable = missing.length + unknown.length
    if (!unreachable) console.log(`  ok  settings menu reaches all ${pages.length} host pages`)
  } else {
    // Only themes that write their own menu need to declare. A theme reusing
    // the host's settings modal reaches everything, and demanding a
    // declaration from it would make this warning noise — which is how the
    // first two slipped through.
    const buildsOwnMenu = files.some(f =>
      readFileSync(f, 'utf8').includes('DefaultSettingsPages'))
    if (buildsOwnMenu) {
      console.log('\n  UNREACHABLE  this theme builds its own settings menu but theme.json'
                + '\n               has no settings.pages — declare which pages it reaches')
      unreachable = 1
    }
  }
} catch (e) {
  if (e.code !== 'ENOENT') console.log(`\n  WARN could not check settings pages — ${e.message}`)
}

process.exit(bad || unreachable ? 1 : 0)
