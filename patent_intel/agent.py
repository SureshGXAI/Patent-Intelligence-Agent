"""Orchestrator: SMILES in -> cited PDF out, with full audit trail.

Pipeline: validate/resolve SMILES -> query all enabled patent databases
(aggregate + dedupe) -> similar compounds -> novelty -> claim-scope FTO ->
citations -> PDF, with every step recorded to an AuditLog.
"""
from __future__ import annotations

from typing import Optional

from .config import settings
from .models import Compound, IntelReport
from .citations import CitationManager
from .audit import AuditLog
from .sources import pubchem, patents as patent_src
from .sources.aggregator import PatentAggregator
from .capabilities import similar_compounds, novelty as novelty_cap, fto as fto_cap
from . import llm
from . import prior_art
from .report_pdf import build_report_pdf


class PatentIntelAgent:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [agent] {msg}")

    def resolve_compound(self, smiles: str) -> Compound:
        canon, cid, name = pubchem.resolve(smiles)
        return Compound(query=smiles, smiles=canon, cid=cid, name=name,
                        source="pubchem" if not settings.mock else "mock")

    def analyze(self, smiles: str, audit: Optional[AuditLog] = None):
        """Run the pipeline. Returns (report, citations, coverage, families,
        llm_notes, audit)."""
        audit = audit or AuditLog()
        audit.snapshot_config(settings)

        citations = CitationManager()
        citations.cite_tool("rdkit", "Morgan fingerprints (r=2, 2048 bits); "
                                     "Tanimoto similarity; substructure / scaffold "
                                     "matching for claim-scope")

        compound = self.resolve_compound(smiles)
        audit.record_input(smiles, compound.smiles)
        report = IntelReport(compound=compound)

        if not compound.smiles:
            report.notes.append("Input did not parse as a valid SMILES; "
                                "analyses skipped.")
            audit.event("abort", reason="invalid_smiles")
            return report, citations, {"queried": [], "skipped": {}}, {}, {}, audit

        citations.cite_compound(compound.smiles,
                                "structure resolution / canonicalisation")
        name_hint = compound.name or None

        self._log("querying patent databases")
        agg = PatentAggregator(citations)
        report.patents = agg.search(
            smiles=compound.smiles,
            compound_names=[name_hint] if name_hint else None,
        )
        coverage = agg.coverage()
        families = agg.families(report.patents)
        audit.event("patent_search", queried=coverage["queried"],
                    skipped=coverage["skipped"],
                    retrieved=[p.id for p in report.patents])

        self._log("finding similar compounds")
        report.similar_compounds = similar_compounds.find(compound.smiles)
        audit.event("similar_compounds",
                    hits=[{"name": h.name, "similarity": h.similarity}
                          for h in report.similar_compounds])

        self._log("estimating novelty")
        report.novelty = novelty_cap.estimate(compound)
        self._log("searching full-text prior art")
        report.novelty.prior_art = prior_art.search_prior_art(
            compound, keywords=name_hint)
        audit.event("novelty", verdict=report.novelty.verdict,
                    score=report.novelty.novelty_score,
                    prior_art=[r["id"] for r in report.novelty.prior_art])

        self._log("assessing freedom-to-operate (claim-scope)")
        candidates = {p.id: p for p in report.patents}
        for hit in report.similar_compounds:
            for pid in hit.disclosed_in:
                if pid not in candidates:
                    p = patent_src.get(pid)
                    if p:
                        p.citation_id = citations.cite_patent(p)
                        candidates[pid] = p
        report.fto = fto_cap.assess(compound, list(candidates.values()))
        audit.event("fto", risk=report.fto.risk.value,
                    blocking=[b["patent"] for b in report.fto.blocking_candidates],
                    claim_scope_evaluated=len(report.fto.claim_scope))

        llm_notes = {}
        if llm.available():
            self._log("enriching with Ollama")
            narrative = llm.narrate_novelty(report.novelty)
            if narrative:
                llm_notes["novelty"] = narrative
                audit.event("llm_enrichment", model=settings.ollama_model)

        report.notes.append("Triage output. FTO and novelty require attorney review.")
        return report, citations, coverage, families, llm_notes, audit

    def generate_pdf(self, smiles: str, out_path: str,
                     audit_dir: Optional[str] = None) -> str:
        audit = AuditLog(run_dir=audit_dir)
        report, citations, coverage, families, llm_notes, audit = \
            self.analyze(smiles, audit=audit)
        self._log(f"writing PDF -> {out_path}")
        build_report_pdf(report, citations, out_path, coverage=coverage,
                         families=families, llm_notes=llm_notes,
                         run_id=audit.run_id)
        manifest = audit.finalize(report, citations, coverage, pdf_path=out_path)
        if audit_dir:
            self._log(f"audit manifest -> {audit_dir}/{audit.run_id}.manifest.json")
        return out_path
