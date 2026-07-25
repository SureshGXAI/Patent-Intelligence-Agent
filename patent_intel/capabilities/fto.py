"""Freedom-to-operate (FTO) triage.

Primary test is now claim-scope membership (Markush genus), not linked-compound
proximity: for each potentially enforceable patent, does any claim's genus cover
the target structure? Proximity is retained only as a fallback when a patent has
no structured Markush claim available.

This surfaces and ranks patents/claims for attorney review. It never concludes
infringement -- claim construction remains a legal judgement.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from ..config import settings
from ..models import Compound, FTOResult, RiskLevel, Patent, ClaimScopeResult
from ..chem.structure import tanimoto, canonical_smiles
from ..data.mock_data import MOCK_COMPOUNDS
from ..legal_status import is_enforceable, get_provider
from . import markush


def _is_live(patent: Patent) -> Optional[bool]:
    """Consult the legal-status feed: True enforceable, False dead, None unknown."""
    return is_enforceable(patent)


def _proximity(target_smiles: str, patent: Patent) -> float:
    best = 0.0
    for name in patent.linked_compounds:
        smi = MOCK_COMPOUNDS.get(name.lower()) if settings.mock else None
        smi = canonical_smiles(smi) if smi else (None if settings.mock else name)
        if not smi:
            continue
        t = tanimoto(target_smiles, smi)
        if t is not None:
            best = max(best, t)
    return best


def assess(compound: Compound, candidate_patents: list[Patent]) -> FTOResult:
    if not compound.smiles:
        return FTOResult(target=compound, risk=RiskLevel.UNKNOWN,
                         rationale="Target structure could not be resolved.")

    flagged: list[dict] = []
    scope_results: list[dict] = []
    any_covered = False
    any_review = False

    for pat in candidate_patents:
        legal = get_provider().status(pat)
        live = legal["enforceable"]
        if live is False:
            continue  # dead patent: no FTO concern

        claims = markush.claims_for_patent(pat)
        covered_here = False
        best_verdict = None
        covering_claim = None
        method = "claim-scope"

        for claim in claims:
            res: ClaimScopeResult = markush.claim_covers(compound.smiles, claim)
            scope_results.append(res.to_dict())
            if res.verdict == "covered":
                covered_here = True
                covering_claim = res.claim_number
                best_verdict = "covered"
                break
            if res.verdict == "scaffold-only-review" and best_verdict is None:
                best_verdict = "scaffold-only-review"
                covering_claim = res.claim_number

        proximity = None
        if not claims:                       # fallback: no structured genus
            method = "proximity-fallback"
            proximity = _proximity(compound.smiles, pat)
            if proximity >= settings.obviousness_tanimoto:
                best_verdict = "proximity"

        # decide whether this patent is a blocking candidate
        include = covered_here or best_verdict in {"scaffold-only-review", "proximity"}
        if not include:
            continue

        review_claims = [c.number for c in pat.claims
                         if c.independent and c.category in
                         {"composition", "use", "unknown"}]
        if covered_here:
            any_covered = True
        elif best_verdict in {"scaffold-only-review"}:
            any_review = True

        flagged.append({
            "patent": pat.id, "assignee": pat.assignee,
            "jurisdiction": pat.jurisdiction, "legal_status": pat.legal_status,
            "expiry_date": pat.expiry_date,
            "effective_expiry": legal.get("effective_expiry"),
            "term": legal.get("term"),
            "enforceable": live,
            "method": method,
            "claim_scope_verdict": best_verdict or "no-signal",
            "covering_claim": covering_claim,
            "structural_proximity": round(proximity, 4) if proximity is not None else None,
            "claims_to_review": review_claims,
            "url": pat.url,
        })

    # rank: covered first, then review/proximity; by proximity desc within
    order = {"covered": 0, "scaffold-only-review": 1, "proximity": 2, "no-signal": 3}
    flagged.sort(key=lambda f: (order.get(f["claim_scope_verdict"], 9),
                                -(f["structural_proximity"] or 0)))

    if any_covered:
        risk = RiskLevel.HIGH
        rationale = (f"Target reads on the claimed genus of "
                     f"{sum(1 for f in flagged if f['claim_scope_verdict']=='covered')} "
                     f"in-force patent claim(s) (scaffold + substituent-class match). "
                     f"Prioritise attorney review.")
    elif flagged and any_review:
        risk = RiskLevel.MEDIUM
        rationale = ("Target matches the claimed scaffold of in-force patent(s) but "
                     "substituent scope was not fully modelled; attorney review needed.")
    elif flagged:
        risk = RiskLevel.MEDIUM
        rationale = ("No modelled claim genus covers the target, but structurally "
                     "close in-force patents exist (proximity fallback).")
    else:
        risk = RiskLevel.LOW
        rationale = ("No enforceable patent has a claim genus covering the target, "
                     "and no structurally close in-force patents were found.")

    return FTOResult(target=compound, risk=risk, blocking_candidates=flagged,
                     claim_scope=scope_results, rationale=rationale)
