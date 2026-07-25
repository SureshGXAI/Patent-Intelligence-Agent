"""Tests for the deterministic core + pipeline (mock mode, no network)."""
import os
import tempfile

from patent_intel.chem.structure import canonical_smiles, tanimoto, substructure_match, nearest
from patent_intel.capabilities.claims import parse_claims, summarize
from patent_intel.capabilities import markush
from patent_intel.agent import PatentIntelAgent
from patent_intel.audit import AuditLog
from patent_intel.models import RiskLevel
from patent_intel.data.mock_data import MOCK_COMPOUNDS, MOCK_MARKUSH


# --- chemistry ---------------------------------------------------------------

def test_canonicalization_and_similarity():
    assert canonical_smiles("C1=CC=CC=C1") == canonical_smiles("c1ccccc1") == "c1ccccc1"
    assert canonical_smiles("bad(((") is None
    assert tanimoto("CCO", "CCO") == 1.0


def test_substructure_and_ranking():
    assert substructure_match("c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O")
    ranked = nearest("CCO", ["CCCO", "c1ccccc1", "CCO"])
    assert ranked[0][1] == 1.0


# --- claim parsing -----------------------------------------------------------

RAW = ("1. A compound of formula I wherein R is selected from the group consisting "
       "of methyl, ethyl and propyl.\n"
       "2. The compound of claim 1 wherein R is methyl.\n"
       "3. A method comprising administering a compound of claims 1 or 2.\n")

def test_claim_structure():
    claims = parse_claims(RAW)
    assert [c.number for c in claims] == [1, 2, 3]
    assert claims[0].independent and claims[0].is_markush
    assert claims[2].depends_on == [1, 2]
    assert summarize(claims)["independent"] == [1]


# --- Markush / claim-scope engine -------------------------------------------

def test_claim_scope_membership():
    # imatinib reads on the imatinib genus; aspirin does not (scaffold absent)
    r1 = markush.claim_covers(MOCK_COMPOUNDS["imatinib"], MOCK_MARKUSH["US5521184A"][0])
    assert r1.covered and r1.verdict == "covered"
    r2 = markush.claim_covers(MOCK_COMPOUNDS["aspirin"], MOCK_MARKUSH["US5521184A"][0])
    assert not r2.covered and r2.verdict == "scaffold-absent"


def test_specific_compound_claim():
    # nilotinib salt claim reads on nilotinib but not imatinib
    claim = MOCK_MARKUSH["US7169791B2"][0]
    assert markush.claim_covers(MOCK_COMPOUNDS["nilotinib"], claim).covered
    assert not markush.claim_covers(MOCK_COMPOUNDS["imatinib"], claim).covered


def test_substituent_outside_genus():
    narrow = {"patent_id": "X", "claim_number": 1,
              "scaffold_smarts": "c1ccc(Nc2ncccn2)cc1",
              "allowed_classes": ["hydrogen", "halogen"]}
    r = markush.claim_covers(MOCK_COMPOUNDS["imatinib"], narrow)
    assert not r.covered and r.verdict == "substituent-outside"


# --- multi-database aggregation (incl. chemistry-aware SureChEMBL) -----------

def test_aggregation_includes_surechembl_and_dedupes():
    agent = PatentIntelAgent()
    report, citations, coverage, families, _, _ = agent.analyze(MOCK_COMPOUNDS["nilotinib"])
    assert "surechembl" in coverage["queried"]
    ids = [p.id for p in report.patents]
    assert ids.count("US7169791B2") == 1                 # deduped across sources
    merged = next(p for p in report.patents if p.id == "US7169791B2")
    assert merged.also_found_in                          # found in >1 database
    assert all(p.citation_id for p in report.patents)


def test_invalid_smiles_rejected():
    report, *_ = PatentIntelAgent().analyze("not smiles !!!")
    assert report.compound.smiles is None and report.novelty is None


# --- claim-scope-driven FTO --------------------------------------------------

def test_fto_uses_claim_scope():
    agent = PatentIntelAgent()
    rep_n, *_ = agent.analyze(MOCK_COMPOUNDS["nilotinib"])
    assert rep_n.fto.risk == RiskLevel.HIGH
    covered = [b for b in rep_n.fto.blocking_candidates
               if b["claim_scope_verdict"] == "covered"]
    assert covered and covered[0]["patent"] == "US7169791B2"
    # imatinib: own genus patent expired -> low
    rep_i, *_ = agent.analyze(MOCK_COMPOUNDS["imatinib"])
    assert rep_i.fto.risk == RiskLevel.LOW


# --- prior art ---------------------------------------------------------------

def test_prior_art_attached():
    rep, *_ = PatentIntelAgent().analyze(MOCK_COMPOUNDS["nilotinib"])
    assert rep.novelty.prior_art and "id" in rep.novelty.prior_art[0]


# --- audit + reproducibility -------------------------------------------------

def test_audit_manifest_and_verify(tmp_path):
    agent = PatentIntelAgent()
    out = str(tmp_path / "r.pdf")
    agent.generate_pdf(MOCK_COMPOUNDS["nilotinib"], out, audit_dir=str(tmp_path))
    manifests = list(tmp_path.glob("*.manifest.json"))
    assert len(manifests) == 1
    import json
    manifest = json.loads(manifests[0].read_text())
    assert manifest["analysis_fingerprint_sha256"] and manifest["pdf_artifact"]["sha256"]
    # re-run analysis -> deterministic fingerprint should match
    rep, *_ = agent.analyze(MOCK_COMPOUNDS["nilotinib"])
    checks = AuditLog.verify(manifest, pdf_path=out, report=rep)
    assert checks["pdf_sha256_match"] and checks["analysis_fingerprint_match"]


# --- PDF ---------------------------------------------------------------------

def test_pdf_generated():
    out = os.path.join(tempfile.gettempdir(), "t.pdf")
    if os.path.exists(out):
        os.remove(out)
    PatentIntelAgent().generate_pdf(MOCK_COMPOUNDS["dasatinib"], out)
    assert os.path.getsize(out) > 5000
    with open(out, "rb") as fh:
        assert fh.read(5) == b"%PDF-"


# --- richer classification + positional Markush (item 3) --------------------

def test_richer_substituent_classification():
    from rdkit import Chem
    from patent_intel.capabilities.markush import classify_fragment as cf
    cases = {"CO[*]": "alkoxy", "O=C(N)[*]": "amide", "N#C[*]": "cyano",
             "FC(F)(F)[*]": "haloalkyl", "O1CCN([*])CC1": "heterocyclyl",
             "C1CCCCC1[*]": "cycloalkyl", "OC(=O)[*]": "carboxyl"}
    for smi, expected in cases.items():
        assert cf(Chem.MolFromSmiles(smi)) == expected, smi


def test_positional_markush_per_position():
    from patent_intel.capabilities.markush import claim_covers
    claim = {"patent_id": "P", "claim_number": 1,
             "labeled_core": "[*:1]c1ccccc1", "rgroups": {"R1": ["halogen"]}}
    assert claim_covers("Clc1ccccc1", claim).verdict == "covered"
    assert claim_covers("Cc1ccccc1", claim).verdict == "substituent-outside"
    assert claim_covers("C1CCCCC1", claim).verdict == "scaffold-absent"


def test_class_subsumption():
    from patent_intel.capabilities.markush import claim_covers
    # genus allowing "alkyl" should admit a lower_alkyl substituent
    claim = {"patent_id": "P", "claim_number": 1,
             "scaffold_smarts": "c1ccccc1", "allowed_classes": ["alkyl"]}
    assert claim_covers("CCCc1ccccc1", claim).covered


# --- claim-text -> genus parser (item 2) ------------------------------------

def test_claim_parser_rgroups():
    from patent_intel.capabilities.claim_parser import parse_genus_from_claim
    g = parse_genus_from_claim(
        "wherein R1 is selected from the group consisting of hydrogen, halogen "
        "and C1-C6 alkyl; and R2 is aryl or heteroaryl.")
    assert "halogen" in g["rgroups"]["R1"] and "aryl" in g["rgroups"]["R2"]
    assert parse_genus_from_claim("A composition comprising the compound.") is None


# --- PTA / SPC in the legal gate (item 4) -----------------------------------

def test_pta_spc_effective_expiry():
    from patent_intel.legal_status import get_provider
    from patent_intel.sources.patents import get
    prov = get_provider()
    us = prov.status(get("US7169791B2"))          # base + PTA
    assert "PTA" in us["term"] and us["effective_expiry"] > "2031-02-11"
    ep = prov.status(get("EP0564409B1"))          # SPC supersedes base
    assert ep["effective_expiry"] == "2016-12-16" and ep["enforceable"] is False


# --- reviewer sign-off chain (item 5) ---------------------------------------

def test_signoff_chain_and_tamper_detection(tmp_path):
    from patent_intel.review import add_signoff, verify_reviews
    import json
    agent = PatentIntelAgent()
    out = str(tmp_path / "r.pdf")
    agent.generate_pdf(MOCK_COMPOUNDS["nilotinib"], out, audit_dir=str(tmp_path))
    mfp = str(next(tmp_path.glob("*.manifest.json")))
    add_signoff(mfp, "Analyst", "needs-work", "check claim 1")
    add_signoff(mfp, "Counsel", "approved", "proceed")
    manifest = json.loads(open(mfp).read())
    assert verify_reviews(manifest)["ok"]
    manifest["reviews"][0]["notes"] = "edited"
    assert verify_reviews(manifest)["ok"] is False
