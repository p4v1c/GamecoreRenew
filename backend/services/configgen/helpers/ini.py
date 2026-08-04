"""INI section surgery.

Surgical on purpose: emulators tolerate their own formatting and little else,
so nothing here ever reformats a file it did not have to touch. Moved verbatim
from controller_profiles.py, which is why the regexes look the way they do.
"""
from __future__ import annotations

import re


def section(text: str, header: str) -> str | None:
    m = re.search(rf"^\[{re.escape(header)}\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def set_section(text: str, header: str, body: str) -> str:
    pat = rf"^\[{re.escape(header)}\]\n.*?(?=^\[|\Z)"
    if re.search(pat, text, re.S | re.M):
        return re.sub(pat, f"[{header}]\n{body}", text, count=1, flags=re.S | re.M)
    return text.rstrip() + f"\n\n[{header}]\n{body}"


def section_bounds(lines: list[str], header: str):
    start = None
    for i, l in enumerate(lines):
        if l.strip() == f"[{header}]":
            start = i
        elif start is not None and l.strip().startswith("["):
            return start, i
    return (start, len(lines)) if start is not None else (None, None)


def extract_section(header):
    def f(text: str) -> str:
        lines = text.splitlines(keepends=True)
        s, e = section_bounds(lines, header)
        return "".join(lines[s:e]) if s is not None else ""
    return f


def replace_section(header):
    def f(text: str, block: str) -> str:
        lines = text.splitlines(keepends=True)
        s, e = section_bounds(lines, header)
        if not block.endswith("\n"):
            block += "\n"
        if s is None:
            return text + ("" if text.endswith("\n") else "\n") + block
        return "".join(lines[:s]) + block + "".join(lines[e:])
    return f


def iter_sections(block: str) -> list[tuple[str, str]]:
    """[(header, whole section including its [header] line)] for a block of
    complete INI sections — the shape snapshots of multi-section formats take."""
    out: list[tuple[str, str]] = []
    header, body = None, []
    for line in block.splitlines(keepends=True):
        if line.strip().startswith("[") and line.strip().endswith("]"):
            if header is not None:
                out.append((header, "".join(body)))
            header, body = line.strip()[1:-1], [line]
        elif header is not None:
            body.append(line)
    if header is not None:
        out.append((header, "".join(body)))
    return out


def set_key(text: str, header: str, key: str, value: str) -> tuple[str, bool]:
    """Set `key = value` in an INI section, adding the line if it is missing.
    Returns (text, changed) and never reformats anything else."""
    body = section(text, header)
    if body is None:
        return text, False
    if re.search(rf"^{re.escape(key)} = {re.escape(value)}$", body, re.M):
        return text, False
    if re.search(rf"^{re.escape(key)} = ", body, re.M):
        new = re.sub(rf"^{re.escape(key)} = .*$", lambda _: f"{key} = {value}",
                     body, count=1, flags=re.M)
    else:
        lines = body.splitlines(keepends=True)
        at = max((n for n, l in enumerate(lines) if l.strip()), default=-1) + 1
        lines.insert(at, f"{key} = {value}\n")
        new = "".join(lines)
    return set_section(text, header, new), True
