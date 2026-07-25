"""Common interface for patent database adapters.

Each database (USPTO, EPO OPS, TIPO, KIPRIS, Lens) implements `PatentSource`.
In mock mode adapters serve records from the bundled dataset tagged with their
source name; in live mode each hits its own API. The aggregator queries every
enabled+available source, then normalises, de-duplicates and groups by family.
"""
from __future__ import annotations

import datetime as _dt
from abc import ABC, abstractmethod
from typing import Optional

from ..config import settings
from ..models import Patent
from ..capabilities.claims import parse_claims
from ..data.mock_data import MOCK_PATENT_RECORDS

_TODAY = _dt.date.today().isoformat()


def build_patent(rec: dict, source: str) -> Patent:
    """Normalise a raw source record into a Patent object."""
    return Patent(
        id=rec.get("id", ""),
        title=rec.get("title", ""),
        assignee=rec.get("assignee", ""),
        priority_date=rec.get("priority_date"),
        grant_date=rec.get("grant_date"),
        expiry_date=rec.get("expiry_date"),
        pta_days=rec.get("pta_days", 0),
        spc_expiry=rec.get("spc_expiry"),
        jurisdiction=rec.get("jurisdiction", ""),
        legal_status=rec.get("legal_status", "unknown"),
        abstract=rec.get("abstract", ""),
        claims=parse_claims(rec.get("claims", "")),
        linked_compounds=rec.get("linked_compounds", []),
        url=rec.get("url", f"https://patents.google.com/patent/{rec.get('id','')}"),
        source=source,
        family_id=rec.get("family_id"),
        accessed=_TODAY,
    )


class PatentSource(ABC):
    name: str = "base"

    def available(self) -> bool:
        """True if this source can be queried (mock always; live needs creds)."""
        if settings.mock:
            return True
        return self._has_credentials()

    def _has_credentials(self) -> bool:
        return True

    def _mock_records(self) -> list[Patent]:
        return [
            build_patent(r, self.name)
            for r in MOCK_PATENT_RECORDS
            if r.get("source") == self.name
        ]

    @abstractmethod
    def search(
        self,
        smiles: Optional[str] = None,
        keywords: Optional[str] = None,
        compound_names: Optional[list[str]] = None,
        limit: int = 25,
    ) -> list[Patent]:
        ...
