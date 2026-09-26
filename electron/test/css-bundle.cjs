// A stylesheet with its `@import url("…");` lines inlined — see
// backend/tests/css_bundle.py. Theme sheets are split under css/.
const fs = require('node:fs')
const path = require('node:path')

module.exports = function readCss(file) {
  return fs.readFileSync(file, 'utf8').replace(/^@import\s+url\("([^"]+)"\);\n/gm,
    (_, rel) => readCss(path.join(path.dirname(file), rel)))
}
