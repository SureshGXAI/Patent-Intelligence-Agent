"""Claim-text -> structured-genus parser.

Turns Markush claim prose into the structured genus the claim-scope engine
consumes: per-variable substituent classes (R1, R2, ...) and their union. It
recognises "selected from the group consisting of ...", "R<n> is/represents
...", and "wherein ..." phrasing, and maps natural-language substituent terms
onto the engine's class vocabulary.

Honest limitation: a scaffold SMARTS cannot be derived from claim *text* alone
(it lives in the referenced formula/drawing). So parsed genera carry the
substituent scope but no scaffold; downstream that yields a "scaffold-only-
review" verdict rather than a false conclusion. Pair with a formula/structure
extractor to close the loop. This is a heuristic parser, not a claim-construction
engine.
"""
from __future__ import annotations

import re
from typing import Optional

# natural-language term -> engine class. Order matters (specific before generic).
_TERM_MAP = [
    (r"\bhydrogen\b|\bh\b", "hydrogen"),
    (r"\bhalo(gen)?\b|\bfluoro\b|\bchloro\b|\bbromo\b|\biodo\b|\bfluorine\b|\bchlorine\b", "halogen"),
    (r"\bhalo(gen)?alkyl\b|\btrifluoromethyl\b|\bperfluoro", "haloalkyl"),
    (r"\bc1\s*[-–]?\s*c?\d*\s*alkoxy\b|\balkoxy\b|\bmethoxy\b|\bethoxy\b", "alkoxy"),
    (r"\bhydroxy(l)?\b", "hydroxyl"),
    (r"\bamino\b|\bamine\b", "amino"),
    (r"\bcarboxy(l|lic)?\b", "carboxyl"),
    (r"\bester\b|\bcar{0,1}alkoxycarbonyl\b", "ester"),
    (r"\bamide\b|\bcarbamoyl\b|\bcarboxamide\b", "amide"),
    (r"\bnitro\b", "nitro"),
    (r"\bcyano\b|\bnitrile\b", "cyano"),
    (r"\bsulfonyl\b|\bsulpho", "sulfonyl"),
    (r"\bheteroaryl\b|\bpyridyl\b|\bpyrimidinyl\b|\bimidazolyl\b|\bthiazolyl\b|\bfuryl\b|\bthienyl\b", "heteroaryl"),
    (r"\baryl\b|\bphenyl\b|\bnaphthyl\b|\bbenzyl\b", "aryl"),
    (r"\bheterocyc(le|lyl|lic)\b|\bmorpholin|\bpiperazin|\bpiperidin|\bpyrrolidin", "heterocyclyl"),
    (r"\bcycloalkyl\b|\bcyclopropyl\b|\bcyclohexyl\b|\bcyclopentyl\b", "cycloalkyl"),
    (r"\blower\s+alkyl\b|\bc1\s*[-–]?\s*c?[1-6]\s*alkyl\b|\bmethyl\b|\bethyl\b|\bpropyl\b|\bbutyl\b", "lower_alkyl"),
    (r"\balkyl\b", "alkyl"),
    (r"\balkenyl\b|\balkynyl\b", "alkyl"),
]

_RGROUP_DEF = re.compile(
    r"\bR\s*(\d*)\b[^.;]*?(?:is|are|represents?|denotes?|selected from|=)\s*(.+?)(?=(?:;|\.|\bwherein\b|\bR\s*\d+\b|$))",
    re.I | re.S,
)
_GROUP_CONSISTING = re.compile(
    r"consisting of (.+?)(?:\.|;|wherein|$)", re.I | re.S)


def _terms_to_classes(text: str) -> list[str]:
    text = text.lower()
    found = []
    for pattern, cls in _TERM_MAP:
        if re.search(pattern, text) and cls not in found:
            found.append(cls)
    return found


def parse_rgroups(claim_text: str) -> dict[str, list[str]]:
    """Return {R1: [classes], ...} parsed from per-variable definitions."""
    rgroups: dict[str, list[str]] = {}
    for m in _RGROUP_DEF.finditer(claim_text):
        label = f"R{m.group(1)}" if m.group(1) else "R"
        classes = _terms_to_classes(m.group(2))
        if classes:
            rgroups.setdefault(label, [])
            for c in classes:
                if c not in rgroups[label]:
                    rgroups[label].append(c)
    return rgroups


def parse_genus_from_claim(claim_text: str) -> Optional[dict]:
    """Parse a Markush claim into a structured genus.

    Returns {rgroups, allowed_classes, scaffold_smarts:"", source:"parsed", note}
    or None if no Markush substituent scope is found.
    """
    rgroups = parse_rgroups(claim_text)
    union: list[str] = []
    if not rgroups:
        m = _GROUP_CONSISTING.search(claim_text)
        if not m:
            return None
        union = _terms_to_classes(m.group(1))
        if not union:
            return None
    else:
        for classes in rgroups.values():
            for c in classes:
                if c not in union:
                    union.append(c)

    return {
        "scaffold_smarts": "",         # not derivable from text alone
        "allowed_classes": union,      # position-agnostic union (engine fallback)
        "rgroups": rgroups,            # per-position, if a labeled core is supplied
        "source": "parsed",
        "note": "Substituent scope parsed from claim text; scaffold must come "
                "from the referenced formula/structure.",
    }
