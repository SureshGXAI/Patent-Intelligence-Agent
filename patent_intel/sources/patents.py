"""Single-patent lookup used for compound->patent linkage.

Multi-database *search* now lives in `sources/aggregator.py`. This module only
resolves a known publication number to a full Patent record (with claims), used
by the similarity and FTO capabilities when they follow a compound to the
patents that disclose it.
"""
from __future__ import annotations

from typing import Optional

from ..config import settings
from ..models import Patent
from ..data.mock_data import MOCK_PATENTS
from .base import build_patent


def get(patent_id: str) -> Optional[Patent]:
    if settings.mock:
        key = patent_id.upper()
        rec = MOCK_PATENTS.get(key) or MOCK_PATENTS.get(patent_id)
        return build_patent(rec, rec.get("source", "")) if rec else None
    raise NotImplementedError(
        "Live single-patent fetch: implement per-source lookup (e.g. EPO OPS "
        "published-data/publication/docdb/<number>/biblio)."
    )
