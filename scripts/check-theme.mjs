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
import { readdirSync, statSync } from 'fs'
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
process.exit(bad ? 1 : 0)
