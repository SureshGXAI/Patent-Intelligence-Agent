"""Audit logging and reproducibility for the attorney workflow.

Produces a tamper-evident trail for each run:
  * a JSONL event log (append-only) of every pipeline step and DB query;
  * a manifest with the input hash, a deterministic analysis fingerprint, the
    config snapshot, source/tool versions, the citation set, and the SHA-256 of
    the generated PDF artifact.

`AuditLog.verify()` recomputes the artifact hash (and, given the report, the
analysis fingerprint) so a reviewer can confirm a PDF matches its manifest.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

VERSION = "0.3.0"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_text(s: str) -> str:
    return _sha256_bytes(s.encode("utf-8"))


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class AuditLog:
    run_dir: Optional[str] = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: str = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat())
    events: list[dict] = field(default_factory=list)
    _config: dict = field(default_factory=dict)
    _input: dict = field(default_factory=dict)

    # --- recording ----------------------------------------------------------

    def event(self, kind: str, **data) -> None:
        self.events.append({
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "kind": kind, **data,
        })

    def snapshot_config(self, settings) -> None:
        self._config = {
            "mock": settings.mock,
            "patent_sources": list(settings.patent_sources),
            "thresholds": {
                "sim_threshold": settings.sim_threshold,
                "anticipation_tanimoto": settings.anticipation_tanimoto,
                "obviousness_tanimoto": settings.obviousness_tanimoto,
            },
            "use_llm": settings.use_llm,
            "ollama_model": settings.ollama_model if settings.use_llm else None,
            "version": VERSION,
        }
        self.event("config", **self._config)

    def record_input(self, raw_smiles: str, canonical: Optional[str]) -> None:
        self._input = {
            "raw_smiles": raw_smiles,
            "canonical_smiles": canonical,
            "input_sha256": _sha256_text(canonical or raw_smiles),
        }
        self.event("input", **self._input)

    # --- finalisation -------------------------------------------------------

    def finalize(self, report, citations, coverage: dict,
                 pdf_path: Optional[str] = None) -> dict:
        report_dict = report.to_dict()
        analysis_fingerprint = _sha256_text(_canonical_json(report_dict))
        pdf_sha256 = None
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as fh:
                pdf_sha256 = _sha256_bytes(fh.read())

        manifest = {
            "run_id": self.run_id,
            "version": VERSION,
            "started": self.started,
            "finished": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "input": self._input,
            "config": self._config,
            "coverage": coverage,
            "verdicts": {
                "novelty": report.novelty.verdict if report.novelty else None,
                "novelty_score": report.novelty.novelty_score if report.novelty else None,
                "fto_risk": report.fto.risk.value if report.fto else None,
            },
            "citations": citations.as_list(),
            "analysis_fingerprint_sha256": analysis_fingerprint,
            "pdf_artifact": {"path": os.path.basename(pdf_path) if pdf_path else None,
                             "sha256": pdf_sha256},
            "event_count": len(self.events),
        }

        if self.run_dir:
            os.makedirs(self.run_dir, exist_ok=True)
            jsonl = os.path.join(self.run_dir, f"{self.run_id}.jsonl")
            with open(jsonl, "w") as fh:
                for ev in self.events:
                    fh.write(json.dumps(ev, default=str) + "\n")
            with open(os.path.join(self.run_dir, f"{self.run_id}.manifest.json"),
                      "w") as fh:
                json.dump(manifest, fh, indent=2, default=str)
        return manifest

    # --- verification -------------------------------------------------------

    @staticmethod
    def verify(manifest: dict, pdf_path: Optional[str] = None,
               report=None) -> dict:
        checks = {}
        if pdf_path and manifest.get("pdf_artifact", {}).get("sha256"):
            with open(pdf_path, "rb") as fh:
                actual = _sha256_bytes(fh.read())
            checks["pdf_sha256_match"] = (
                actual == manifest["pdf_artifact"]["sha256"])
        if report is not None:
            fp = _sha256_text(_canonical_json(report.to_dict()))
            checks["analysis_fingerprint_match"] = (
                fp == manifest.get("analysis_fingerprint_sha256"))
        checks["ok"] = all(checks.values()) if checks else False
        return checks
