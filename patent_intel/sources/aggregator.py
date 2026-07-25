"""Multi-database aggregator.

Queries every enabled + available patent source, merges the results by
publication number (recording which databases each was found in), groups by
family, and registers citations for both the databases queried and each patent
returned.
"""
from __future__ import annotations

from typing import Optional

from ..config import settings
from ..models import Patent
from ..citations import CitationManager
from .patent_dbs import REGISTRY


class PatentAggregator:
    def __init__(self, citations: Optional[CitationManager] = None):
        self.citations = citations or CitationManager()
        self.sources = []
        self.skipped: dict[str, str] = {}
        for name in settings.patent_sources:
            cls = REGISTRY.get(name)
            if not cls:
                self.skipped[name] = "unknown source"
                continue
            src = cls()
            if src.available():
                self.sources.append(src)
            else:
                self.skipped[name] = "no credentials configured"

    def search(
        self,
        smiles: Optional[str] = None,
        keywords: Optional[str] = None,
        compound_names: Optional[list[str]] = None,
        limit: int = 25,
    ) -> list[Patent]:
        merged: dict[str, Patent] = {}
        query_desc = keywords or (compound_names[0] if compound_names else smiles or "*")

        for src in self.sources:
            try:
                results = src.search(smiles=smiles, keywords=keywords,
                                     compound_names=compound_names, limit=limit)
            except Exception as exc:                      # keep going if one DB fails
                self.skipped[src.name] = f"error: {exc}"
                self.citations.cite_database(src.name, str(query_desc), 0)
                continue

            self.citations.cite_database(src.name, str(query_desc), len(results))

            for pat in results:
                key = pat.id.upper().replace("-", "")
                if key in merged:
                    existing = merged[key]
                    if src.name not in existing.also_found_in and \
                       src.name != existing.source:
                        existing.also_found_in.append(src.name)
                else:
                    merged[key] = pat

        patents = list(merged.values())
        for pat in patents:                               # per-patent citation ids
            pat.citation_id = self.citations.cite_patent(pat)
        # stable order: in-force first, then by priority date
        patents.sort(key=lambda p: (p.legal_status != "active", p.priority_date or ""))
        return patents

    def families(self, patents: list[Patent]) -> dict[str, list[Patent]]:
        fams: dict[str, list[Patent]] = {}
        for p in patents:
            fams.setdefault(p.family_id or p.id, []).append(p)
        return fams

    def coverage(self) -> dict:
        return {
            "queried": [s.name for s in self.sources],
            "skipped": self.skipped,
        }
