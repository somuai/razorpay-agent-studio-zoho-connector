"""Scan saved live output and print only redacted matches."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = {
    "long_digits": re.compile(r"\b\d{8,}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "named_secret": re.compile(
        r"(?i)(?:authorization\s*[:=]\s*|(?:access|refresh)_token\s*[:=]\s*|"
        r"client_secret\s*[:=]\s*|grant(?:\s*code)?\s*[:=]\s*)\S+"
    ),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}(?:\.[A-Za-z0-9_-]{8,})?\b"),
    "long_token_like": re.compile(r"\b[A-Za-z0-9_-]{40,}\b"),
}


def mask(line: str) -> str:
    line = PATTERNS["long_digits"].sub("XXXXXXXX", line)
    line = PATTERNS["email"].sub("[EMAIL]", line)
    line = PATTERNS["named_secret"].sub("[SECRET_FIELD]=[REDACTED]", line)
    line = PATTERNS["jwt"].sub("[TOKEN]", line)
    return PATTERNS["long_token_like"].sub("[TOKEN]", line)


def main() -> int:
    paths = [Path(value) for value in sys.argv[1:]]
    unsafe = False
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            print(f"UNSAFE {path}: output file could not be read")
            unsafe = True
            continue
        for number, line in enumerate(lines, start=1):
            labels = [name for name, pattern in PATTERNS.items() if pattern.search(line)]
            if labels:
                print(f"UNSAFE {path}:{number} [{','.join(labels)}] {mask(line)}")
                unsafe = True
    if not unsafe:
        print("SAFE: no long digit strings, email addresses, or token-like strings found")
    return 1 if unsafe else 0


if __name__ == "__main__":
    raise SystemExit(main())
