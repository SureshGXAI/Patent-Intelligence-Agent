"""Claim parsing and analysis.

A pragmatic, dependency-free parser that turns a raw claims block into
structured `Claim` objects. It is heuristic (patent language is messy) but
covers the common cases: numbering, dependency ("claim N"), Markush groups,
and a rough category guess. For hard cases, hand the structured output to the
optional LLM layer for a plain-language scope summary.
"""
from __future__ import annotations

import re

from ..models import Claim

_CLAIM_SPLIT = re.compile(r"(?:^|\n)\s*(\d{1,3})\s*[\.\)]\s+")
_DEP_PATTERNS = [
    re.compile(r"\bclaim\s+(\d{1,3})\b", re.I),
    re.compile(r"\bclaims?\s+(\d{1,3})\s*(?:or|to|-|–|through)\s*(\d{1,3})\b", re.I),
    re.compile(r"\baccording to\s+claim\s+(\d{1,3})\b", re.I),
]
_MARKUSH = re.compile(
    r"selected from the group consisting of|wherein .* is selected from", re.I
)

_CATEGORY_HINTS = {
    "method": re.compile(r"\b(a|the)?\s*method (of|for|comprising)|process (of|for)", re.I),
    "use": re.compile(r"\buse of\b|for use in|for treating|for the treatment", re.I),
    "composition": re.compile(
        r"\b(compound|composition|pharmaceutical composition|salt|formulation|"
        r"crystalline form|polymorph)\b",
        re.I,
    ),
    "apparatus": re.compile(r"\b(apparatus|device|system|kit)\b", re.I),
}


def _dependencies(text: str) -> list[int]:
    deps: set[int] = set()
    for pat in _DEP_PATTERNS:
        for m in pat.finditer(text):
            nums = [int(g) for g in m.groups() if g]
            if len(nums) == 2 and nums[0] <= nums[1]:
                deps.update(range(nums[0], nums[1] + 1))
            else:
                deps.update(nums)
    return sorted(deps)


def _category(text: str) -> str:
    for cat, pat in _CATEGORY_HINTS.items():
        if pat.search(text):
            return cat
    return "unknown"


def parse_claims(raw: str) -> list[Claim]:
    """Parse a raw claims block into structured Claim objects."""
    if not raw or not raw.strip():
        return []

    # Split on leading claim numbers while keeping the number.
    parts = _CLAIM_SPLIT.split(raw)
    # parts looks like ['', '1', 'text1', '2', 'text2', ...]
    claims: list[Claim] = []
    it = iter(parts)
    _ = next(it, None)  # drop preamble before claim 1
    for num, text in zip(it, it):
        try:
            number = int(num)
        except ValueError:
            continue
        text = text.strip()
        deps = _dependencies(text)
        claims.append(
            Claim(
                number=number,
                text=text,
                independent=len(deps) == 0,
                depends_on=deps,
                is_markush=bool(_MARKUSH.search(text)),
                category=_category(text),
            )
        )
    return claims


def summarize(claims: list[Claim]) -> dict:
    """Quick structural summary useful for triage dashboards."""
    independent = [c.number for c in claims if c.independent]
    markush = [c.number for c in claims if c.is_markush]
    by_cat: dict[str, list[int]] = {}
    for c in claims:
        by_cat.setdefault(c.category, []).append(c.number)
    return {
        "total": len(claims),
        "independent": independent,
        "dependent_count": len(claims) - len(independent),
        "markush_claims": markush,
        "by_category": by_cat,
    }
