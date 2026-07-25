"""Citation tracking.

Every fact that lands in the report is traceable to a source. The manager
assigns stable [n] numbers in order of first use and renders a full reference
list for the PDF. Sources covered:

  * patent records (per database, with publication number + URL)
  * database queries (documents coverage even when a DB returns nothing)
  * chemical data (PubChem resolution / similarity)
  * tooling (RDKit, thresholds) for methodological transparency
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional

# Human-readable database provenance used in references.
DB_META = {
    "uspto": ("USPTO", "United States Patent and Trademark Office (PatentsView / Open Data)",
              "https://www.patentsview.org"),
    "epo_ops": ("EPO OPS", "European Patent Office — Open Patent Services",
                "https://www.epo.org/searching-for-patents/data/web-services/ops.html"),
    "tipo": ("TIPO", "Taiwan Intellectual Property Office — Global Patent Search System",
             "https://gpss.tipo.gov.tw"),
    "kipris": ("KIPRIS", "Korea Intellectual Property Rights Information Service (KIPRIS Plus)",
               "http://plus.kipris.or.kr"),
    "lens": ("Lens.org", "The Lens — Patent Search API", "https://www.lens.org"),
    "surechembl": ("SureChEMBL", "SureChEMBL — chemistry-aware patent search (EMBL-EBI)",
                   "https://www.surechembl.org"),
    "pubchem": ("PubChem", "NCBI PubChem (PUG-REST)", "https://pubchem.ncbi.nlm.nih.gov"),
    "rdkit": ("RDKit", "RDKit: Open-source cheminformatics", "https://www.rdkit.org"),
}


@dataclass
class Citation:
    number: int
    kind: str            # patent | database | compound | tool
    title: str
    source: str          # DB label, e.g. "USPTO"
    identifier: str = ""  # pub number / CID / query string
    url: str = ""
    accessed: str = ""
    note: str = ""

    def format(self) -> str:
        parts = [p for p in [self.title, self.source, self.identifier] if p]
        ref = ". ".join(parts)
        if self.url:
            ref += f". {self.url}"
        if self.accessed:
            ref += f" (accessed {self.accessed})"
        if self.note:
            ref += f". {self.note}"
        return ref


class CitationManager:
    def __init__(self, accessed: Optional[str] = None):
        self._by_key: dict[str, Citation] = {}
        self._order: list[Citation] = []
        self.accessed = accessed or _dt.date.today().isoformat()

    def _add(self, key: str, **kw) -> int:
        if key in self._by_key:
            return self._by_key[key].number
        c = Citation(number=len(self._order) + 1, accessed=self.accessed, **kw)
        self._by_key[key] = c
        self._order.append(c)
        return c.number

    # --- typed helpers ------------------------------------------------------

    def cite_patent(self, patent) -> int:
        src_label = DB_META.get(patent.source, (patent.source or "Patent DB",))[0]
        return self._add(
            key=f"patent:{patent.id}",
            kind="patent",
            title=patent.title or patent.id,
            source=src_label,
            identifier=patent.id,
            url=patent.url,
            note=(f"Also retrieved via {', '.join(patent.also_found_in)}"
                  if patent.also_found_in else ""),
        )

    def cite_database(self, source: str, query: str, n_results: int) -> int:
        label, full, url = DB_META.get(source, (source, source, ""))
        return self._add(
            key=f"db:{source}",
            kind="database",
            title=f"{full} — patent search",
            source=label,
            identifier=f"query: {query}; {n_results} record(s)",
            url=url,
        )

    def cite_compound(self, identifier: str, note: str = "") -> int:
        label, full, url = DB_META["pubchem"]
        return self._add(
            key=f"pubchem:{identifier}",
            kind="compound",
            title=full,
            source=label,
            identifier=identifier,
            url=url,
            note=note,
        )

    def cite_document(self, ref: dict) -> int:
        """Cite a prior-art document reference: {type,id,title,source,url}."""
        return self._add(
            key=f"doc:{ref.get('id') or ref.get('title')}",
            kind="prior-art",
            title=ref.get("title", "") or ref.get("id", ""),
            source=ref.get("source", ""),
            identifier=ref.get("id", ""),
            url=ref.get("url", ""),
        )

    def cite_tool(self, name: str, note: str = "") -> int:
        label, full, url = DB_META.get(name, (name, name, ""))
        return self._add(
            key=f"tool:{name}",
            kind="tool",
            title=full,
            source=label,
            url=url,
            note=note,
        )

    # --- output -------------------------------------------------------------

    def references(self) -> list[Citation]:
        return list(self._order)

    def as_list(self) -> list[dict]:
        return [
            {"number": c.number, "kind": c.kind, "text": c.format()}
            for c in self._order
        ]
