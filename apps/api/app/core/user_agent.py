"""
Minimal, dependency-free User-Agent parsing for the "your active
sessions" display (browser/platform only — never used for any security
decision, since User-Agent is trivially spoofable). A real parsing
library (e.g. `user-agents`) is a reasonable future swap; this covers the
common cases without adding a dependency for what is purely cosmetic
data.
"""

import re

_BROWSER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Edge", re.compile(r"Edg/")),
    ("Chrome", re.compile(r"Chrome/")),
    ("Firefox", re.compile(r"Firefox/")),
    ("Safari", re.compile(r"Version/.*Safari/")),
    ("Opera", re.compile(r"OPR/")),
]

_PLATFORM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("Android", re.compile(r"Android")),
    ("Windows", re.compile(r"Windows")),
    ("macOS", re.compile(r"Macintosh|Mac OS X")),
    ("Linux", re.compile(r"Linux")),
]


def parse_browser(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    for name, pattern in _BROWSER_PATTERNS:
        if pattern.search(user_agent):
            return name
    return "Other"


def parse_platform(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    for name, pattern in _PLATFORM_PATTERNS:
        if pattern.search(user_agent):
            return name
    return "Other"
