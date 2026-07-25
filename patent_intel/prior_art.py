"""Full-text prior-art search for novelty (template).

Structural similarity alone misses prior art that discloses a compound in text
(examples, tables, prophetic compounds) without a machine-readable structure.
This module templates a full-text search across patent + scholarly corpora and
returns document references that a reviewer should read for anticipation.

Mock mode returns illustrative references so the pipeline and citations are
exercised offline; live mode templates Lens scholarly/patent full-text and EPO
published-data search.
"""
from __future__ import annotations

from typing import Optional

import requests

from .config import settings


def search_prior_art(compound, keywords: Optional[str] = None,
                     limit: int = 5) -> list[dict]:
    """Return prior-art document references: {type, id, title, source, url}."""
    if settings.mock:
        return _mock(compound)
    refs = []
    if settings.lens_key:
        refs += _lens_fulltext(compound, keywords, limit)
    # hooks: EPO published-data full-text, PATENTSCOPE, PubMed/Europe PMC
    return refs[:limit]


def _mock(compound) -> list[dict]:
    name = compound.name or "the target compound"
    return [
        {"type": "journal", "id": "doi:10.1000/mock.kinase",
         "title": f"Structure-activity relationships of {name}-class kinase "
                  f"inhibitors", "source": "Lens scholarly (mock)",
         "url": "https://www.lens.org/lens/scholar"},
        {"type": "patent", "id": "WO2004005281A1",
         "title": "Pyrimidineamine derivatives as kinase inhibitors",
         "source": "Lens patent full-text (mock)",
         "url": "https://patents.google.com/patent/WO2004005281A1"},
    ]


def _lens_fulltext(compound, keywords, limit) -> list[dict]:
    # Template: Lens scholarly/patent full-text search (verify schema in docs).
    try:
        body = {"query": {"match": {"full_text": keywords or (compound.name or "")}},
                "size": limit}
        r = requests.post(
            f"{settings.lens_base}/patent/search",
            json=body,
            headers={"Authorization": f"Bearer {settings.lens_key}",
                     "Content-Type": "application/json"},
            timeout=settings.http_timeout,
        )
        r.raise_for_status()
        out = []
        for rec in r.json().get("data", []):
            out.append({"type": "patent", "id": rec.get("lens_id", ""),
                        "title": "", "source": "Lens full-text",
                        "url": f"https://www.lens.org/lens/patent/{rec.get('lens_id','')}"})
        return out
    except Exception:
        return []
