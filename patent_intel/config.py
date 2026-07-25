"""Runtime configuration. Everything is overridable via environment variables
so the same code runs offline (mock) and against live APIs in production.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: list[str]) -> list[str]:
    v = os.getenv(name)
    return default if not v else [x.strip() for x in v.split(",") if x.strip()]


@dataclass
class Settings:
    # If True, no network calls are made; bundled sample data is used instead.
    mock: bool = _bool("PIA_MOCK", True)

    # --- Chemical source (PubChem PUG-REST is free, no key) ---
    pubchem_base: str = os.getenv(
        "PIA_PUBCHEM_BASE", "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    )

    # --- Patent databases to query (order = priority) ---
    # Enabled sources; each has its own credentials below.
    patent_sources: list[str] = field(
        default_factory=lambda: _list(
            "PIA_PATENT_SOURCES", ["surechembl", "uspto", "epo_ops", "tipo", "kipris", "lens"]
        )
    )

    # SureChEMBL — chemistry-aware structure search (open data)
    surechembl_base: str = os.getenv("PIA_SURECHEMBL_BASE", "https://www.surechembl.org")

    # USPTO — PatentsView Search API (key-gated) / Open Data Portal
    uspto_base: str = os.getenv("PIA_USPTO_BASE", "https://search.patentsview.org/api/v1")
    uspto_key: str = os.getenv("PIA_USPTO_KEY", "")

    # EPO Open Patent Services — OAuth2 client credentials
    epo_ops_base: str = os.getenv("PIA_EPO_OPS_BASE", "https://ops.epo.org/3.2")
    epo_ops_key: str = os.getenv("PIA_EPO_OPS_KEY", "")
    epo_ops_secret: str = os.getenv("PIA_EPO_OPS_SECRET", "")

    # TIPO (Taiwan) — Global Patent Search System (GPSS) API
    tipo_base: str = os.getenv("PIA_TIPO_BASE", "https://tiponet.tipo.gov.tw/gpss1/gpsskmc/gpssbkm")
    tipo_key: str = os.getenv("PIA_TIPO_KEY", "")

    # KIPRIS (Korea) — KIPRIS Plus API (service key, XML responses)
    kipris_base: str = os.getenv(
        "PIA_KIPRIS_BASE", "http://plus.kipris.or.kr/kipo-api/kipi"
    )
    kipris_key: str = os.getenv("PIA_KIPRIS_KEY", "")

    # Lens.org — Patent Search API (bearer token, JSON)
    lens_base: str = os.getenv("PIA_LENS_BASE", "https://api.lens.org")
    lens_key: str = os.getenv("PIA_LENS_KEY", "")

    # --- Optional LLM enrichment via Ollama (local, no key) ---
    use_llm: bool = _bool("PIA_USE_LLM", False)
    ollama_base: str = os.getenv("PIA_OLLAMA_BASE", "http://localhost:11434")
    ollama_model: str = os.getenv("PIA_OLLAMA_MODEL", "llama3.1")

    # --- Scoring thresholds (tunable, transparent) ---
    sim_threshold: float = float(os.getenv("PIA_SIM_THRESHOLD", "0.75"))
    anticipation_tanimoto: float = float(os.getenv("PIA_ANTICIPATION_T", "0.99"))
    obviousness_tanimoto: float = float(os.getenv("PIA_OBVIOUSNESS_T", "0.85"))
    http_timeout: float = float(os.getenv("PIA_HTTP_TIMEOUT", "30"))

    def credentials_for(self, source: str) -> dict:
        return {
            "uspto": {"key": self.uspto_key, "base": self.uspto_base},
            "epo_ops": {"key": self.epo_ops_key, "secret": self.epo_ops_secret,
                        "base": self.epo_ops_base},
            "tipo": {"key": self.tipo_key, "base": self.tipo_base},
            "kipris": {"key": self.kipris_key, "base": self.kipris_base},
            "lens": {"key": self.lens_key, "base": self.lens_base},
        }.get(source, {})


settings = Settings()
