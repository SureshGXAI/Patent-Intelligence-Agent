"""Command-line interface.

    python -m patent_intel.cli "CC(=O)Oc1ccccc1C(=O)O" -o report.pdf
    python -m patent_intel.cli "<SMILES>" -o report.pdf --json --audit-dir audit/
    python -m patent_intel.cli --sources surechembl,uspto,lens "<SMILES>" -o out.pdf

Runs offline (mock) by default. Set PIA_MOCK=false plus API keys for live
databases; PIA_USE_LLM=true with a local Ollama server for narrative enrichment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .agent import PatentIntelAgent
from .audit import AuditLog
from .config import settings
from .report_pdf import build_report_pdf


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="patent-intel", description=__doc__)
    ap.add_argument("smiles", help="compound SMILES (the analysis input)")
    ap.add_argument("-o", "--out", default="patent_report.pdf")
    ap.add_argument("--json", action="store_true", help="print report JSON to stdout")
    ap.add_argument("--sources", default=None, help="comma-separated DBs to query")
    ap.add_argument("--audit-dir", default=None,
                    help="write audit manifest + JSONL log here")
    args = ap.parse_args(argv)

    if args.sources:
        settings.patent_sources = [s.strip() for s in args.sources.split(",")]

    mode = "MOCK" if settings.mock else "LIVE"
    print(f"[patent-intel :: {mode}] databases: {', '.join(settings.patent_sources)}",
          file=sys.stderr)

    agent = PatentIntelAgent(verbose=True)
    audit = AuditLog(run_dir=args.audit_dir)
    report, citations, coverage, families, llm_notes, audit = \
        agent.analyze(args.smiles, audit=audit)

    if not report.compound.smiles:
        print("ERROR: input is not a valid SMILES.", file=sys.stderr)
        return 2

    build_report_pdf(report, citations, args.out, coverage=coverage,
                     families=families, llm_notes=llm_notes, run_id=audit.run_id)
    manifest = audit.finalize(report, citations, coverage, pdf_path=args.out)
    print(f"PDF written: {os.path.abspath(args.out)}", file=sys.stderr)
    if args.audit_dir:
        print(f"Audit manifest: {args.audit_dir}/{audit.run_id}.manifest.json",
              file=sys.stderr)

    if args.json:
        payload = report.to_dict()
        payload["coverage"] = coverage
        payload["references"] = citations.as_list()
        payload["audit"] = {"run_id": manifest["run_id"],
                            "analysis_fingerprint": manifest["analysis_fingerprint_sha256"]}
        print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
