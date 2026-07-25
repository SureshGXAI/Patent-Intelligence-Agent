"""Live per-jurisdiction legal-status feed (template).

FTO's enforceability gate consults this provider instead of trusting a static
field. In mock mode it echoes the bundled status; in live mode it templates
INPADOC legal-status (EPO OPS) and leaves hooks for USPTO PTAB/assignment and
national registers. Endpoints/parsing must be verified against current API docs.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

import requests

from .config import settings


class LegalStatusProvider:
    def status(self, patent) -> dict:
        """Return {status, expiry_date, effective_expiry, term, source, enforceable}."""
        if settings.mock:
            eff, term = self._effective_expiry(patent)
            return {
                "status": patent.legal_status,
                "expiry_date": patent.expiry_date,
                "effective_expiry": eff,
                "term": term,
                "source": "bundled",
                "enforceable": self._enforceable(patent.legal_status, eff),
            }
        return self._live(patent)

    # --- term calculation ---------------------------------------------------

    @staticmethod
    def _effective_expiry(patent):
        """Apply PTA and SPC/term-extension to the statutory expiry.

        Returns (effective_expiry_iso, term_note). SPC/term extension, if present,
        supersedes; otherwise base expiry is extended by any patent-term
        adjustment (PTA) days.
        """
        base = patent.expiry_date
        if getattr(patent, "spc_expiry", None):
            return patent.spc_expiry, f"SPC/term extension to {patent.spc_expiry}"
        pta = getattr(patent, "pta_days", 0) or 0
        if base and pta:
            try:
                d = _dt.date.fromisoformat(base) + _dt.timedelta(days=pta)
                return d.isoformat(), f"base {base} + {pta}d PTA"
            except ValueError:
                pass
        return base, "statutory term"

    # --- live templates -----------------------------------------------------

    def _live(self, patent) -> dict:
        juris = (patent.jurisdiction or "").upper()
        try:
            if juris in {"EP", "WO"} and settings.epo_ops_key:
                return self._epo_inpadoc(patent)
            # hooks: USPTO PTAB / assignment, KR/TW national registers
            return {"status": "unknown", "expiry_date": patent.expiry_date,
                    "source": "unresolved", "enforceable": None}
        except Exception as exc:
            return {"status": "error", "expiry_date": patent.expiry_date,
                    "source": f"error:{exc}", "enforceable": None}

    def _epo_inpadoc(self, patent) -> dict:
        """EPO OPS INPADOC legal-status service.

        GET {base}/rest-services/legal/publication/epodoc/{number}/ ; the response
        lists ops:legal events; the most recent 'lapse'/'expiry'/'revocation' code
        determines enforceability. Reuses the OPS OAuth token from EPOOPSSource.
        """
        from .sources.patent_dbs import EPOOPSSource  # reuse token cache
        from .sources import _http
        num = patent.id.replace(patent.jurisdiction, "", 1) if patent.jurisdiction else patent.id
        token = EPOOPSSource()._token()
        r = _http.get(
            f"{settings.epo_ops_base}/rest-services/legal/publication/epodoc/{num}/",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        events = self._extract_legal_events(r.json())
        dead_codes = {"lapsed", "revoked", "withdrawn", "expired", "refused"}
        status = "active"
        for ev in events:
            if any(code in ev.lower() for code in dead_codes):
                status = "expired"
                break
        return {"status": status, "expiry_date": patent.expiry_date,
                "effective_expiry": patent.expiry_date, "term": "INPADOC",
                "source": "epo_ops_inpadoc",
                "enforceable": self._enforceable(status, patent.expiry_date)}

    @staticmethod
    def _extract_legal_events(payload: dict) -> list[str]:
        try:
            data = payload["ops:world-patent-data"]["ops:legal"]
            if isinstance(data, dict):
                data = [data]
            out = []
            for ev in data:
                code = ev.get("ops:L510EP", ev.get("@code", ""))
                if isinstance(code, dict):
                    code = code.get("$", "")
                out.append(str(code))
            return out
        except (KeyError, TypeError):
            return []

    # --- shared logic -------------------------------------------------------

    @staticmethod
    def _enforceable(status: str, expiry: Optional[str]) -> Optional[bool]:
        s = (status or "").lower()
        if s in {"expired", "withdrawn", "lapsed", "revoked"}:
            return False
        if expiry:
            try:
                return _dt.date.fromisoformat(expiry) >= _dt.date.today()
            except ValueError:
                pass
        if s in {"active", "granted", "pending"}:
            return True
        return None


_provider: Optional[LegalStatusProvider] = None


def get_provider() -> LegalStatusProvider:
    global _provider
    if _provider is None:
        _provider = LegalStatusProvider()
    return _provider


def is_enforceable(patent) -> Optional[bool]:
    return get_provider().status(patent)["enforceable"]
