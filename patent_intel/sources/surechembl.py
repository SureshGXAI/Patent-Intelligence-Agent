"""SureChEMBL — chemistry-aware patent search (template).

Unlike the name/keyword adapters, this source takes a STRUCTURE (SMILES) and
returns patents that disclose that structure or close analogues -- the
structure-indexed search the roadmap calls for. In mock mode it maps the query
structure to disclosing patents via RDKit similarity against the bundled
compounds; in live mode it templates a SureChEMBL structure-search call.
"""
from __future__ import annotations

from typing import Optional

import requests

from ..config import settings
from ..models import Patent
from ..chem.structure import tanimoto, canonical_smiles
from ..data.mock_data import MOCK_COMPOUNDS, MOCK_PATENT_RECORDS
from .base import PatentSource, build_patent


class SureChEMBLSource(PatentSource):
    name = "surechembl"

    def _has_credentials(self) -> bool:
        # SureChEMBL data is open; a base URL is all that's needed in live mode.
        return True

    def search(self, smiles=None, keywords=None, compound_names=None, limit=25):
        if settings.mock:
            return self._mock_structure_search(smiles, limit)
        return self._live_structure_search(smiles, limit)

    # --- mock: structure -> disclosing patents ------------------------------

    def _mock_structure_search(self, smiles: Optional[str], limit: int) -> list[Patent]:
        if not smiles:
            return []
        threshold = 0.40
        # compounds structurally related to the query
        related = set()
        for name, smi in MOCK_COMPOUNDS.items():
            t = tanimoto(smiles, canonical_smiles(smi) or smi)
            if t is not None and t >= threshold:
                related.add(name)
        # patents disclosing any related compound
        out: list[Patent] = []
        for rec in MOCK_PATENT_RECORDS:
            linked = {c.lower() for c in rec.get("linked_compounds", [])}
            if related & linked:
                out.append(build_patent(rec, self.name))
        return out[:limit]

    # --- live template ------------------------------------------------------

    def _live_structure_search(self, smiles: Optional[str], limit: int) -> list[Patent]:
        if not smiles:
            return []
        # Template: SureChEMBL structure search (verify endpoint/params in docs).
        # e.g. GET {base}/api/structure?smiles=...&type=similarity&threshold=...
        base = getattr(settings, "surechembl_base",
                       "https://www.surechembl.org")
        try:
            from . import _http
            r = _http.get(
                f"{base}/api/structure",
                params={"smiles": smiles, "type": "similarity", "limit": limit},
            )
            out = []
            for rec in r.json().get("patents", []):
                out.append(build_patent({
                    "id": rec.get("patent_id", ""),
                    "title": rec.get("title", ""),
                    "jurisdiction": rec.get("jurisdiction", ""),
                    "linked_compounds": rec.get("compounds", []),
                }, self.name))
            return out
        except Exception:
            return []
