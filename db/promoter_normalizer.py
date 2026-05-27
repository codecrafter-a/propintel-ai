"""Normalize promoter / builder names for deduplication.

GUJRERA promoter strings are inconsistent: "ABC Builders Pvt Ltd" vs
"ABC Builders Private Limited" vs "abc  builders". We normalize for matching
but preserve the raw input separately on the row.
"""

from __future__ import annotations

import re

# Suffixes commonly tacked onto Indian company names.
# Each pattern uses ``\b`` at both ends so e.g. ``\bco\b`` doesn't eat the
# "co" prefix of "corp".
_SUFFIX_PATTERNS = [
    r"\bprivate\s+limited\b",
    r"\bpvt\b\.?\s*\bltd\b\.?",
    r"\blimited\b",
    r"\bltd\b\.?",
    r"\bllp\b",
    r"\binc\b\.?",
    r"\bcorporation\b",
    r"\bcorp\b\.?",
    r"\bco\b\.?",
    r"\bbuilders\s+and\s+developers\b",
    r"\bdevelopers\b",
    r"\benterprises\b",
    r"\bgroup\b",
]
_SUFFIX_RE = re.compile("|".join(_SUFFIX_PATTERNS), re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[.,()'\"&/]+")


def normalize(name: str) -> str:
    """Return a canonical form suitable for unique-key matching.

    - lowercases
    - strips common corporate suffixes
    - collapses whitespace
    - removes light punctuation

    Empty input → empty string. Never raises.
    """
    if not name:
        return ""
    s = name.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _SUFFIX_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s
