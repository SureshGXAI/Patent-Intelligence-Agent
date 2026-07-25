"""Offline demo: SMILES in -> cited PDF out, with claim-scope FTO and audit trail.

    python -m patent_intel.demo
"""
from __future__ import annotations

import os

from .agent import PatentIntelAgent
from .data.mock_data import MOCK_COMPOUNDS


def main() -> None:
    agent = PatentIntelAgent(verbose=True)
    outdir = os.environ.get("PIA_OUTDIR", ".")
    auditdir = os.path.join(outdir, "audit")
    os.makedirs(outdir, exist_ok=True)

    for name in ["nilotinib", "imatinib"]:
        smiles = MOCK_COMPOUNDS[name]
        print(f"\n=== {name}  ({smiles[:38]}...) ===")
        report, citations, coverage, families, _, audit = agent.analyze(smiles)
        print("  databases queried :", ", ".join(coverage["queried"]))
        print("  patents (deduped)  :", [p.id for p in report.patents])
        merged = [p.id for p in report.patents if p.also_found_in]
        print("  cross-DB merges    :", merged or "none")
        print("  novelty            :", report.novelty.verdict,
              f"(score {report.novelty.novelty_score})")
        print("  prior-art refs     :", [r["id"] for r in report.novelty.prior_art])
        print("  FTO risk           :", report.fto.risk.value.upper())
        for b in report.fto.blocking_candidates:
            print(f"     - {b['patent']}: {b['claim_scope_verdict']} "
                  f"(claim {b['covering_claim']}, {b['method']})")
        print("  citations          :", len(citations.references()))

        out = os.path.join(outdir, f"patent_report_{name}.pdf")
        agent.generate_pdf(smiles, out, audit_dir=auditdir)
        print("  PDF                :", out, f"({os.path.getsize(out)} bytes)")
        print("  audit run_id       :", audit.run_id)

    print(f"\nAudit manifests + JSONL logs in: {auditdir}")


if __name__ == "__main__":
    main()
