"""PDF report generation (reportlab / Platypus).

Renders a cited patent-intelligence report from an IntelReport plus a
CitationManager. Every substantive datum carries an in-text [n] marker that
resolves in the References section.
"""
from __future__ import annotations

import datetime as _dt
import os
import tempfile
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    HRFlowable, KeepTogether,
)

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from .models import IntelReport, RiskLevel
from .citations import CitationManager

_RISK_COLOR = {
    RiskLevel.HIGH: colors.HexColor("#c0392b"),
    RiskLevel.MEDIUM: colors.HexColor("#e67e22"),
    RiskLevel.LOW: colors.HexColor("#27ae60"),
    RiskLevel.UNKNOWN: colors.HexColor("#7f8c8d"),
}
_INK = colors.HexColor("#1a1a2e")
_MUTED = colors.HexColor("#555")
_RULE = colors.HexColor("#d0d0d8")


def _hex(color) -> str:
    return "#" + color.hexval()[2:]


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1x", parent=ss["Heading1"], textColor=_INK,
                          spaceBefore=14, spaceAfter=6, fontSize=15))
    ss.add(ParagraphStyle("H2x", parent=ss["Heading2"], textColor=_INK,
                          spaceBefore=10, spaceAfter=4, fontSize=12))
    ss.add(ParagraphStyle("Bodyx", parent=ss["BodyText"], fontSize=9.5,
                          leading=13, alignment=TA_LEFT))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=8,
                          leading=10, textColor=_MUTED))
    ss.add(ParagraphStyle("Cell", parent=ss["BodyText"], fontSize=8, leading=10))
    ss.add(ParagraphStyle("CellMono", parent=ss["BodyText"], fontSize=7.5,
                          leading=9, fontName="Courier"))
    ss.add(ParagraphStyle("Ref", parent=ss["BodyText"], fontSize=8, leading=11,
                          leftIndent=16, firstLineIndent=-16))
    return ss


def _mol_png(smiles: str, path: str, size=(360, 220)) -> bool:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    d = rdMolDraw2D.MolDraw2DCairo(*size)
    opts = d.drawOptions()
    opts.padding = 0.08
    d.DrawMolecule(mol)
    d.FinishDrawing()
    with open(path, "wb") as fh:
        fh.write(d.GetDrawingText())
    return True


def _cref(ids) -> str:
    """Render an in-text citation marker like [1] or [1, 3]."""
    ids = [i for i in (ids if isinstance(ids, (list, tuple)) else [ids]) if i]
    return f" [{', '.join(str(i) for i in ids)}]" if ids else ""


def build_report_pdf(
    report: IntelReport,
    citations: CitationManager,
    out_path: str,
    coverage: Optional[dict] = None,
    families: Optional[dict] = None,
    llm_notes: Optional[dict] = None,
    run_id: Optional[str] = None,
) -> str:
    ss = _styles()
    story: list = []
    tmp_png = os.path.join(tempfile.gettempdir(), "pia_mol.png")

    def P(text, style="Bodyx"):
        story.append(Paragraph(text, ss[style]))

    def rule():
        story.append(HRFlowable(width="100%", thickness=0.6, color=_RULE,
                                spaceBefore=4, spaceAfter=8))

    comp = report.compound

    # ---- Header ----
    P("Patent Intelligence Report", "Title")
    P(f"Generated {_dt.date.today().isoformat()} &nbsp;·&nbsp; "
      f"triage decision-support &nbsp;·&nbsp; not legal advice"
      + (f" &nbsp;·&nbsp; run {run_id[:12]}" if run_id else ""), "Small")
    rule()

    # ---- Target compound + structure ----
    P("1. Target compound", "H1x")
    struct_cell = Paragraph("(structure could not be rendered)", ss["Cell"])
    if comp.smiles and _mol_png(comp.smiles, tmp_png):
        struct_cell = Image(tmp_png, width=6.4 * cm, height=3.9 * cm)
    comp_cite = _cref(citations.cite_compound(
        comp.smiles or comp.query, "structure resolution / canonicalisation"))
    info = [
        [Paragraph("<b>Input SMILES</b>", ss["Cell"]),
         Paragraph(comp.query, ss["CellMono"])],
        [Paragraph("<b>Canonical SMILES</b>", ss["Cell"]),
         Paragraph((comp.smiles or "-") + comp_cite, ss["CellMono"])],
        [Paragraph("<b>Name</b>", ss["Cell"]),
         Paragraph(comp.name or "(unnamed)", ss["Cell"])],
        [Paragraph("<b>PubChem CID</b>", ss["Cell"]),
         Paragraph(str(comp.cid) if comp.cid else "-", ss["Cell"])],
    ]
    t = Table([[struct_cell, Table(info, colWidths=[3.0 * cm, 6.0 * cm])]],
              colWidths=[7.0 * cm, 9.4 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)

    # ---- Executive summary ----
    P("2. Executive summary", "H1x")
    nv = report.novelty
    ft = report.fto
    risk = ft.risk if ft else RiskLevel.UNKNOWN
    summary_rows = [
        [Paragraph("<b>Novelty estimate</b>", ss["Cell"]),
         Paragraph(f"{(nv.verdict if nv else 'n/a').upper()} "
                   f"(score {nv.novelty_score if nv else '-'})", ss["Cell"])],
        [Paragraph("<b>FTO risk (triage)</b>", ss["Cell"]),
         Paragraph(f'<font color="{_hex(_RISK_COLOR[risk])}">'
                   f"<b>{risk.value.upper()}</b></font>", ss["Cell"])],
        [Paragraph("<b>Databases queried</b>", ss["Cell"]),
         Paragraph(", ".join((coverage or {}).get("queried", [])) or "-", ss["Cell"])],
        [Paragraph("<b>Patents retrieved</b>", ss["Cell"]),
         Paragraph(str(len(report.patents)), ss["Cell"])],
    ]
    st = Table(summary_rows, colWidths=[4.2 * cm, 12.2 * cm])
    st.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _RULE),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f4f8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(st)

    # ---- Database coverage ----
    P("3. Database coverage", "H1x")
    cov = coverage or {}
    queried = cov.get("queried", [])
    db_cites = {name: citations.cite_database(name, comp.smiles or comp.query, 0)
                for name in queried}
    # note: real per-DB counts are recorded during aggregation; here we only
    # ensure a citation exists for every queried DB.
    P("Sources searched: " + ", ".join(
        f"{n}{_cref(db_cites[n])}" for n in queried) or "none", "Bodyx")
    if cov.get("skipped"):
        skipped = "; ".join(f"{k} ({v})" for k, v in cov["skipped"].items())
        P(f"<i>Not searched:</i> {skipped}", "Small")

    # ---- Patent landscape ----
    P("4. Patent landscape", "H1x")
    if report.patents:
        header = [Paragraph(f"<b>{h}</b>", ss["Cell"]) for h in
                  ["Publication", "Juris.", "Assignee", "Status", "Expiry",
                   "Source", "Ref"]]
        rows = [header]
        for p in report.patents:
            also = f" (+{','.join(p.also_found_in)})" if p.also_found_in else ""
            rows.append([
                Paragraph(p.id, ss["Cell"]),
                Paragraph(p.jurisdiction or "-", ss["Cell"]),
                Paragraph(p.assignee or "-", ss["Cell"]),
                Paragraph(p.legal_status, ss["Cell"]),
                Paragraph(p.expiry_date or "-", ss["Cell"]),
                Paragraph((p.source or "-") + also, ss["Cell"]),
                Paragraph(str(p.citation_id or "-"), ss["Cell"]),
            ])
        pt = Table(rows, colWidths=[2.8*cm, 1.2*cm, 3.4*cm, 1.9*cm, 2.0*cm,
                                    3.1*cm, 1.0*cm], repeatRows=1)
        pt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _RULE),
            ("BACKGROUND", (0, 0), (-1, 0), _INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(pt)
        if families:
            fam_txt = "; ".join(
                f"{fid}: {', '.join(pp.id for pp in members)}"
                for fid, members in families.items() if len(members) > 1)
            if fam_txt:
                P(f"<b>Families (grouped):</b> {fam_txt}", "Small")
    else:
        P("No patents retrieved from the searched databases.", "Bodyx")

    # ---- Similar compounds ----
    P("5. Structurally similar compounds", "H1x")
    if report.similar_compounds:
        rows = [[Paragraph(f"<b>{h}</b>", ss["Cell"]) for h in
                 ["Compound / SMILES", "Tanimoto", "Disclosed in", "Ref"]]]
        for h in report.similar_compounds:
            cid = citations.cite_compound(
                h.name or h.smiles, "PubChem 2D similarity neighbour")
            disc = ", ".join(h.disclosed_in) if h.disclosed_in else "-"
            label = h.name or h.smiles
            rows.append([
                Paragraph(label, ss["Cell"] if h.name else ss["CellMono"]),
                Paragraph(f"{h.similarity:.3f}", ss["Cell"]),
                Paragraph(disc, ss["Cell"]),
                Paragraph(str(cid), ss["Cell"]),
            ])
        sct = Table(rows, colWidths=[8.6*cm, 2.0*cm, 4.8*cm, 1.0*cm], repeatRows=1)
        sct.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _RULE),
            ("BACKGROUND", (0, 0), (-1, 0), _INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(sct)
    else:
        P("No structural neighbours above threshold.", "Bodyx")

    # ---- Novelty ----
    P("6. Novelty / non-obviousness estimate", "H1x")
    if nv:
        P(f"<b>Verdict:</b> {nv.verdict.upper()} &nbsp; "
          f"<b>Novelty score:</b> {nv.novelty_score} (1 = no close art)", "Bodyx")
        P(nv.rationale, "Bodyx")
        if getattr(nv, "prior_art", None):
            P("<b>Full-text prior art to review:</b>", "Bodyx")
            for ref in nv.prior_art:
                dc = citations.cite_document(ref)
                P(f"&bull; [{ref.get('type','doc')}] {ref.get('title','')} "
                  f"({ref.get('id','')}){_cref(dc)}", "Bodyx")
        if llm_notes and llm_notes.get("novelty"):
            P(f"<i>LLM narrative (Ollama):</i> {llm_notes['novelty']}", "Small")
        P(f"<i>{nv.disclaimer}</i>", "Small")

    # ---- FTO ----
    P("7. Freedom-to-operate triage", "H1x")
    if ft:
        P(f'<b>Risk:</b> <font color="{_hex(_RISK_COLOR[risk])}">'
          f"<b>{risk.value.upper()}</b></font>", "Bodyx")
        P(ft.rationale, "Bodyx")
        for b in ft.blocking_candidates:
            pid = b["patent"]
            cnum = next((p.citation_id for p in report.patents if p.id == pid), None)
            verdict = b.get("claim_scope_verdict", "-")
            method = b.get("method", "-")
            basis = (f"reads on claim {b['covering_claim']}"
                     if verdict == "covered" and b.get("covering_claim")
                     else f"{verdict} ({method})")
            prox = b.get("structural_proximity")
            prox_txt = f" · proximity {prox}" if prox is not None else ""
            exp = b.get("effective_expiry") or b.get("expiry_date", "-")
            term = b.get("term")
            term_txt = f" ({term})" if term and term != "statutory term" else ""
            P(f"&bull; <b>{pid}</b>{_cref(cnum)} — {b['assignee']} · "
              f"status {b['legal_status']} · expiry {exp}{term_txt} · "
              f"<b>{basis}</b>{prox_txt} · review claims {b['claims_to_review']}",
              "Bodyx")
        if ft.claim_scope:
            covered = [s for s in ft.claim_scope if s.get("verdict") == "covered"]
            P(f"<i>Claim-scope engine evaluated {len(ft.claim_scope)} claim "
              f"genus/genera; {len(covered)} cover the target "
              f"(scaffold + substituent-class / specific-compound match).</i>",
              "Small")
        P(f"<i>{ft.disclaimer}</i>", "Small")
    else:
        P("FTO not assessed (unresolved structure).", "Bodyx")

    # ---- References ----
    story.append(Spacer(1, 6))
    P("8. References", "H1x")
    for c in citations.references():
        P(f"[{c.number}] {c.format()}", "Ref")

    # ---- Footer disclaimer ----
    rule()
    P("This report is automated triage output. Structural similarity is a "
      "proxy, not a legal test; novelty (anticipation) and freedom-to-operate "
      "are legal determinations requiring review by a qualified patent attorney "
      "in each jurisdiction of interest. Coverage is limited to the databases "
      "listed above and to the sample/live data available at generation time.",
      "Small")
    if run_id:
        P(f"Run ID {run_id} — see the audit manifest for the input hash, "
          f"analysis fingerprint and artifact checksum.", "Small")

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm, topMargin=1.6*cm, bottomMargin=1.6*cm,
        title="Patent Intelligence Report", author="Patent Intelligence Agent",
    )
    doc.build(story)
    return out_path
