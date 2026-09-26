"""A stylesheet as the browser applies it: `@import url("…");` lines inlined.

Theme sheets and settings.css are split under css/ and imported in cascade
order; tests that assert on "the whole sheet" read it through `read_css`.
"""
import re
from pathlib import Path

_IMPORT = re.compile(r'^@import\s+url\("([^"]+)"\);\n', re.M)


def read_css(path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return _IMPORT.sub(lambda m: read_css(path.parent / m.group(1)), text)
