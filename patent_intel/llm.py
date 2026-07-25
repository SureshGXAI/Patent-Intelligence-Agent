"""Optional LLM enrichment via a local Ollama server (no API key).

Deterministic core works without this. When enabled (PIA_USE_LLM=true and an
Ollama server reachable at PIA_OLLAMA_BASE), it adds plain-language claim-scope
summaries and a novelty/obviousness narrative grounded in evidence the
deterministic layer already computed -- it explains, it does not invent facts.

Start Ollama locally:  `ollama serve`  then  `ollama pull llama3.1`
"""
from __future__ import annotations

import json
from typing import Optional

import requests

from .config import settings
from .models import Claim, NoveltyResult


def available() -> bool:
    if not settings.use_llm:
        return False
    try:
        r = requests.get(f"{settings.ollama_base}/api/tags",
                         timeout=min(settings.http_timeout, 5))
        return r.status_code == 200
    except Exception:
        return False


def _chat(system: str, user: str, num_predict: int = 700) -> Optional[str]:
    if not settings.use_llm:
        return None
    try:
        r = requests.post(
            f"{settings.ollama_base}/api/chat",
            json={
                "model": settings.ollama_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"temperature": 0.2, "num_predict": num_predict},
            },
            timeout=settings.http_timeout,
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip() or None
    except Exception:
        return None


def explain_claim_scope(claims: list[Claim]) -> Optional[str]:
    if not claims:
        return None
    payload = [
        {"number": c.number, "independent": c.independent,
         "category": c.category, "markush": c.is_markush, "text": c.text}
        for c in claims
    ]
    system = (
        "You are a patent analyst. Summarise the SCOPE of the independent claims "
        "in plain English for a non-lawyer triaging freedom-to-operate. Be "
        "concrete about what is and isn't covered. Do not give legal advice."
    )
    return _chat(system, "Claims:\n" + json.dumps(payload, indent=2))


def narrate_novelty(result: NoveltyResult) -> Optional[str]:
    system = (
        "You are a patent analyst. Given a target compound and its closest "
        "prior-art analogues with similarity scores, explain the novelty/"
        "obviousness picture for triage. Reference only the evidence given; do "
        "not invent references. State that this is not a legal determination."
    )
    payload = {
        "target": result.target.to_dict(),
        "verdict": result.verdict,
        "novelty_score": result.novelty_score,
        "closest_art": [c.to_dict() for c in result.closest_art],
    }
    return _chat(system, json.dumps(payload, indent=2))
