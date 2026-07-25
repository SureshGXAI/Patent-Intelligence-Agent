"""Core data models for the Patent Intelligence Agent.

These are deliberately plain dataclasses so they serialize cleanly to JSON
and stay decoupled from any specific data source or LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass
class Compound:
    """A chemical entity resolved to a structure."""
    query: str                      # what the user asked for (name or SMILES)
    smiles: Optional[str] = None    # canonical SMILES once resolved
    cid: Optional[int] = None       # PubChem CID if known
    name: Optional[str] = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    number: int
    text: str
    independent: bool = True
    depends_on: list[int] = field(default_factory=list)
    is_markush: bool = False        # "selected from the group consisting of ..."
    category: str = "unknown"       # composition | method | use | apparatus | unknown

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Patent:
    id: str                         # e.g. US7521456B2
    title: str = ""
    assignee: str = ""
    priority_date: Optional[str] = None   # ISO date
    grant_date: Optional[str] = None
    expiry_date: Optional[str] = None
    pta_days: int = 0                # US patent term adjustment (35 USC 154(b))
    spc_expiry: Optional[str] = None  # supplementary protection certificate / term extension
    jurisdiction: str = ""          # US | EP | TW | KR | WO | ...
    legal_status: str = "unknown"   # active | expired | pending | withdrawn
    abstract: str = ""
    claims: list[Claim] = field(default_factory=list)
    linked_compounds: list[str] = field(default_factory=list)  # SMILES or names
    url: str = ""
    source: str = ""                # which database returned it (uspto, lens, ...)
    also_found_in: list[str] = field(default_factory=list)     # other DBs w/ same pub#
    family_id: Optional[str] = None  # simple patent-family key
    accessed: Optional[str] = None   # ISO date the record was retrieved
    citation_id: Optional[int] = None  # assigned by CitationManager

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompoundHit:
    """A prior-art / neighbouring compound with a similarity score."""
    smiles: str
    similarity: float               # Tanimoto 0..1 vs the query
    cid: Optional[int] = None
    name: Optional[str] = None
    disclosed_in: list[str] = field(default_factory=list)  # patent ids
    source: str = "pubchem"
    citation_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimScopeResult:
    """Whether a target structure falls within a claim's Markush genus."""
    patent_id: str
    claim_number: int
    covered: bool
    verdict: str                    # covered | scaffold-absent | substituent-outside | scaffold-only-review
    scaffold_smarts: str = ""
    matched_scaffold: bool = False
    substituents: list[dict] = field(default_factory=list)  # {class, smiles, allowed}
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FTOResult:
    """Freedom-to-operate TRIAGE output. Not legal advice."""
    target: Compound
    risk: RiskLevel
    blocking_candidates: list[dict[str, Any]] = field(default_factory=list)
    claim_scope: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    disclaimer: str = (
        "Decision-support triage only. This is NOT a freedom-to-operate opinion "
        "and NOT legal advice. Flagged patents/claims require review by a "
        "qualified patent attorney in each jurisdiction of interest."
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["target"] = self.target.to_dict()
        d["risk"] = self.risk.value
        return d


@dataclass
class NoveltyResult:
    """Novelty / non-obviousness ESTIMATE. Not a legal determination."""
    target: Compound
    novelty_score: float            # 0 (anticipated) .. 1 (no close art found)
    verdict: str                    # anticipated | obviousness-risk | likely-novel
    closest_art: list[CompoundHit] = field(default_factory=list)
    prior_art: list[dict[str, Any]] = field(default_factory=list)  # full-text refs
    rationale: str = ""
    disclaimer: str = (
        "Heuristic estimate for triage. Structural similarity is a proxy, not a "
        "legal test. Anticipation (novelty) and obviousness are determined by "
        "claim construction and examiner/attorney judgement."
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["target"] = self.target.to_dict()
        d["closest_art"] = [c.to_dict() for c in self.closest_art]
        return d


@dataclass
class IntelReport:
    """Consolidated output of a full agent run."""
    compound: Compound
    patents: list[Patent] = field(default_factory=list)
    similar_compounds: list[CompoundHit] = field(default_factory=list)
    novelty: Optional[NoveltyResult] = None
    fto: Optional[FTOResult] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compound": self.compound.to_dict(),
            "patents": [p.to_dict() for p in self.patents],
            "similar_compounds": [c.to_dict() for c in self.similar_compounds],
            "novelty": self.novelty.to_dict() if self.novelty else None,
            "fto": self.fto.to_dict() if self.fto else None,
            "notes": self.notes,
        }
