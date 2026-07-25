"""Similar-compound search: find structural neighbours and, where possible,
the patents that disclose them (a SureChEMBL-style compound->patent linkage).
"""
from __future__ import annotations

from ..config import settings
from ..models import CompoundHit
from ..sources import pubchem, patents as patent_src
from ..chem.structure import canonical_smiles
from ..data.mock_data import MOCK_COMPOUNDS


def _disclosing_patents(smiles: str) -> list[str]:
    """Which known patents disclose this structure (mock linkage)."""
    if not settings.mock:
        return []  # live: query SureChEMBL / patent-compound index here
    # reverse map canonical smiles -> compound name -> patents
    name = None
    for nm, smi in MOCK_COMPOUNDS.items():
        if canonical_smiles(smi) == smiles:
            name = nm
            break
    if not name:
        return []
    hits = []
    from ..data.mock_data import MOCK_PATENTS
    for pid, rec in MOCK_PATENTS.items():
        if name in [c.lower() for c in rec.get("linked_compounds", [])]:
            hits.append(pid)
    return hits


def find(smiles: str, threshold: float | None = None) -> list[CompoundHit]:
    threshold = settings.sim_threshold if threshold is None else threshold
    neighbours = pubchem.similarity_search(smiles, threshold=threshold)
    name_by_smiles = {
        canonical_smiles(v): k for k, v in MOCK_COMPOUNDS.items()
    } if settings.mock else {}
    hits: list[CompoundHit] = []
    for cand_smiles, sim, cid in neighbours:
        hits.append(
            CompoundHit(
                smiles=cand_smiles,
                similarity=round(sim, 4),
                cid=cid,
                name=name_by_smiles.get(cand_smiles),
                disclosed_in=_disclosing_patents(cand_smiles),
            )
        )
    return hits
