"""Concrete patent-database adapters.

Live clients are working templates: the request shapes reflect each API's
documented contract, but endpoints/fields drift and most require registration,
so verify against current docs before shipping. All adapters degrade to the
bundled mock dataset when PIA_MOCK is set.
"""
from __future__ import annotations

from typing import Optional

import requests

from ..config import settings
from ..models import Patent
from .base import PatentSource, build_patent
from . import _http


def _mock_filter(records: list[Patent], compound_names, keywords) -> list[Patent]:
    wanted = {c.lower() for c in (compound_names or [])}
    kw = (keywords or "").lower()
    out = []
    for p in records:
        linked = {c.lower() for c in p.linked_compounds}
        ok = True
        if wanted:
            ok = ok and bool(wanted & linked)
        if kw:
            hay = f"{p.title} {p.abstract}".lower()
            ok = ok and kw in hay
        if ok:
            out.append(p)
    return out or records  # if nothing matched, return all this source knows


# --------------------------------------------------------------------------- #
# USPTO — PatentsView Search API                                              #
# --------------------------------------------------------------------------- #
class USPTOSource(PatentSource):
    name = "uspto"

    def _has_credentials(self) -> bool:
        return bool(settings.uspto_key)

    def search(self, smiles=None, keywords=None, compound_names=None, limit=25):
        if settings.mock:
            return _mock_filter(self._mock_records(), compound_names, keywords)
        q = {"_and": []}
        if keywords:
            q["_and"].append({"_text_any": {"patent_abstract": keywords}})
        body = {
            "q": q if q["_and"] else {"_gte": {"patent_date": "1990-01-01"}},
            "f": ["patent_id", "patent_title", "patent_abstract", "patent_date",
                  "assignees.assignee_organization"],
            "o": {"size": limit},
        }
        r = requests.post(f"{settings.uspto_base}/patent/", json=body,
                          headers={"X-Api-Key": settings.uspto_key},
                          timeout=settings.http_timeout)
        r.raise_for_status()
        out = []
        for rec in r.json().get("patents", []):
            org = (rec.get("assignees") or [{}])[0].get("assignee_organization", "")
            out.append(build_patent({
                "id": f"US{rec.get('patent_id','')}",
                "title": rec.get("patent_title", ""),
                "abstract": rec.get("patent_abstract", ""),
                "grant_date": rec.get("patent_date"),
                "assignee": org, "jurisdiction": "US",
            }, self.name))
        return out


# --------------------------------------------------------------------------- #
# EPO — Open Patent Services (OAuth2 client-credentials)                       #
# --------------------------------------------------------------------------- #
class EPOOPSSource(PatentSource):
    name = "epo_ops"
    _token_cache: dict = {}   # {"token": str, "expires_at": float}

    def _has_credentials(self) -> bool:
        return bool(settings.epo_ops_key and settings.epo_ops_secret)

    def _token(self) -> str:
        import time
        cache = EPOOPSSource._token_cache
        if cache.get("token") and cache.get("expires_at", 0) > time.time() + 30:
            return cache["token"]
        r = _http.post(
            f"{settings.epo_ops_base}/auth/accesstoken",
            data={"grant_type": "client_credentials"},
            auth=(settings.epo_ops_key, settings.epo_ops_secret),
            headers={"Accept": "application/json"},
        )
        payload = r.json()
        cache["token"] = payload["access_token"]
        cache["expires_at"] = time.time() + int(payload.get("expires_in", 1200))
        return cache["token"]

    def search(self, smiles=None, keywords=None, compound_names=None, limit=25):
        if settings.mock:
            return _mock_filter(self._mock_records(), compound_names, keywords)
        token = self._token()
        cql = f'ta="{keywords}"' if keywords else 'pd within "1990 2025"'
        r = _http.get(
            f"{settings.epo_ops_base}/rest-services/published-data/search/biblio",
            params={"q": cql, "Range": f"1-{limit}"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        return self._parse_ops(r.json())

    def _parse_ops(self, payload: dict) -> list[Patent]:
        """Parse OPS biblio-search JSON (ops:world-patent-data -> ... -> exchange-documents)."""
        out: list[Patent] = []
        try:
            wpd = payload["ops:world-patent-data"]
            result = wpd["ops:biblio-search"]["ops:search-result"]
            docs = result.get("ops:publication-reference", result.get("exchange-documents", []))
            if isinstance(docs, dict):
                docs = [docs]
            for d in docs:
                doc = d.get("exchange-document", d)
                docid = (doc.get("@doc-number")
                         or self._docnum(doc.get("document-id")))
                juris = doc.get("@country", "EP")
                title = self._first_title(doc)
                out.append(build_patent({
                    "id": f"{juris}{docid}" if docid else "",
                    "title": title, "jurisdiction": juris,
                }, self.name))
        except (KeyError, TypeError):
            return out
        return out

    @staticmethod
    def _docnum(document_id) -> str:
        if isinstance(document_id, list):
            document_id = document_id[0] if document_id else {}
        if isinstance(document_id, dict):
            dn = document_id.get("doc-number", "")
            return dn.get("$", "") if isinstance(dn, dict) else str(dn)
        return ""

    @staticmethod
    def _first_title(doc) -> str:
        titles = ((doc.get("bibliographic-data", {}) or {})
                  .get("invention-title", []))
        if isinstance(titles, dict):
            titles = [titles]
        for t in titles:
            if isinstance(t, dict) and t.get("$"):
                return t["$"]
        return ""


# --------------------------------------------------------------------------- #
# TIPO (Taiwan) — Global Patent Search System (GPSS) API                       #
# --------------------------------------------------------------------------- #
class TIPOSource(PatentSource):
    name = "tipo"

    def _has_credentials(self) -> bool:
        return bool(settings.tipo_key)

    def search(self, smiles=None, keywords=None, compound_names=None, limit=25):
        if settings.mock:
            return _mock_filter(self._mock_records(), compound_names, keywords)
        r = requests.get(
            f"{settings.tipo_base}/patentSearch",
            params={"apiKey": settings.tipo_key, "keyword": keywords or "",
                    "rows": limit},
            timeout=settings.http_timeout,
        )
        r.raise_for_status()
        out = []
        for rec in r.json().get("records", []):
            out.append(build_patent({
                "id": rec.get("publicationNumber", ""),
                "title": rec.get("title", ""),
                "abstract": rec.get("abstract", ""),
                "assignee": rec.get("applicant", ""),
                "jurisdiction": "TW",
                "grant_date": rec.get("publicationDate"),
            }, self.name))
        return out


# --------------------------------------------------------------------------- #
# KIPRIS (Korea) — KIPRIS Plus API (service key, XML)                          #
# --------------------------------------------------------------------------- #
class KIPRISSource(PatentSource):
    name = "kipris"

    def _has_credentials(self) -> bool:
        return bool(settings.kipris_key)

    def search(self, smiles=None, keywords=None, compound_names=None, limit=25):
        if settings.mock:
            return _mock_filter(self._mock_records(), compound_names, keywords)
        r = requests.get(
            f"{settings.kipris_base}/patUtiModInfoSearchSevice/getWordSearch",
            params={"word": keywords or "", "ServiceKey": settings.kipris_key,
                    "numOfRows": limit},
            timeout=settings.http_timeout,
        )
        r.raise_for_status()
        return self._parse_kipris_xml(r.text)  # KIPRIS returns XML

    def _parse_kipris_xml(self, xml_text: str) -> list[Patent]:
        import xml.etree.ElementTree as ET
        out = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return out
        for item in root.iter("item"):
            def g(tag):
                el = item.find(tag)
                return el.text if el is not None else ""
            out.append(build_patent({
                "id": g("registerNumber") or g("applicationNumber"),
                "title": g("inventionTitle"),
                "abstract": g("astrtCont"),
                "assignee": g("applicantName"),
                "jurisdiction": "KR",
                "grant_date": g("registerDate"),
            }, self.name))
        return out


# --------------------------------------------------------------------------- #
# Lens.org — Patent Search API (bearer token, JSON)                            #
# --------------------------------------------------------------------------- #
class LensSource(PatentSource):
    name = "lens"

    def _has_credentials(self) -> bool:
        return bool(settings.lens_key)

    def search(self, smiles=None, keywords=None, compound_names=None, limit=25):
        if settings.mock:
            return _mock_filter(self._mock_records(), compound_names, keywords)
        query = {"match": {"abstract": keywords}} if keywords else {"match_all": {}}
        body = {"query": query, "size": limit,
                "include": ["lens_id", "biblio", "doc_key"]}
        r = _http.post(
            f"{settings.lens_base}/patent/search",
            json=body,
            headers={"Authorization": f"Bearer {settings.lens_key}",
                     "Content-Type": "application/json"},
        )
        out = []
        for rec in r.json().get("data", []):
            biblio = rec.get("biblio", {})
            doc = (biblio.get("publication_reference", {}) or {})
            pub = f"{doc.get('jurisdiction','')}{doc.get('doc_number','')}"
            title = ""
            titles = biblio.get("invention_title", [])
            if titles:
                title = titles[0].get("text", "")
            out.append(build_patent({
                "id": pub or rec.get("lens_id", ""),
                "title": title,
                "jurisdiction": doc.get("jurisdiction", ""),
                "url": f"https://www.lens.org/lens/patent/{rec.get('lens_id','')}",
            }, self.name))
        return out


from .surechembl import SureChEMBLSource

REGISTRY: dict[str, type[PatentSource]] = {
    "surechembl": SureChEMBLSource,
    "uspto": USPTOSource,
    "epo_ops": EPOOPSSource,
    "tipo": TIPOSource,
    "kipris": KIPRISSource,
    "lens": LensSource,
}
