"""Markush / claim-scope reasoning.

Tests whether a target structure falls within a claim's genus. Three claim
shapes are supported:

  * specific claim  -> {specific_smiles}                 (salt/polymorph/compound)
  * genus claim     -> {scaffold_smarts, allowed_classes} (position-agnostic)
  * positional claim-> {labeled_core, rgroups}           (per-position constraints)

Substituent classification is functional-group aware, with a small subsumption
lattice so a broad claimed class ("alkyl") admits its narrower members
("lower_alkyl"). Limits remain explicit: coarse classification; position-agnostic
mode does not bind class-to-position; no "optionally substituted"/nested-Markush
constraints beyond the positional mode's direct per-label sets. This triages
claim scope; it is not legal claim construction.
"""
from __future__ import annotations

from typing import Optional

from rdkit import Chem
from rdkit.Chem import rdRGroupDecomposition as _rdRGD

from ..config import settings
from ..models import ClaimScopeResult

_HALOGENS = {9, 17, 35, 53}

_FG_SMARTS = [
    ("haloalkyl", "[CX4][F,Cl,Br,I]"),
    ("nitro",     "[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    ("cyano",     "[CX2]#[NX1]"),
    ("carboxyl",  "[CX3](=O)[OX2H1,OX1-]"),
    ("ester",     "[CX3](=O)[OX2][#6]"),
    ("amide",     "[CX3](=O)[NX3]"),
    ("sulfonyl",  "[SX4](=O)(=O)"),
    ("alkoxy",    "[OX2]([#6])[#6,#0]"),
    ("hydroxyl",  "[OX2H1,OX1-]"),
    ("amino",     "[NX3;!$(NC=O);!$(N=O);!$(N=N)]"),
]
_FG_QUERIES = [(n, Chem.MolFromSmarts(s)) for n, s in _FG_SMARTS]

_ALL_CLASSES = {"hydrogen", "halogen", "haloalkyl", "alkoxy", "hydroxyl", "amino",
                "amide", "ester", "carboxyl", "nitro", "cyano", "sulfonyl",
                "aryl", "heteroaryl", "cycloalkyl", "heterocyclyl",
                "lower_alkyl", "alkyl", "complex"}
_SUBSUMES = {
    "alkyl": {"alkyl", "lower_alkyl", "cycloalkyl", "haloalkyl"},
    "lower_alkyl": {"lower_alkyl"},
    "aromatic": {"aryl", "heteroaryl"},
    "carbocycle": {"aryl", "cycloalkyl"},
    "heterocycle": {"heteroaryl", "heterocyclyl"},
    "any": set(_ALL_CLASSES),
}


def _clean(frag) -> None:
    try:
        Chem.SanitizeMol(frag)
    except Exception:
        try:
            Chem.FastFindRings(frag)
        except Exception:
            pass


def classify_fragment(frag) -> str:
    if frag is None:
        return "hydrogen"
    _clean(frag)
    heavy = [a for a in frag.GetAtoms() if a.GetAtomicNum() > 0]
    if not heavy:
        return "hydrogen"
    if len(heavy) == 1 and heavy[0].GetAtomicNum() in _HALOGENS:
        return "halogen"
    only_carbon = all(a.GetAtomicNum() == 6 for a in heavy)
    if any(a.GetIsAromatic() for a in heavy):
        return "aryl" if only_carbon else "heteroaryl"
    try:
        nrings = frag.GetRingInfo().NumRings()
    except Exception:
        nrings = 0
    if nrings > 0:
        return "cycloalkyl" if only_carbon else "heterocyclyl"
    for name, q in _FG_QUERIES:
        if q is not None and frag.HasSubstructMatch(q):
            return name
    if only_carbon:
        return "lower_alkyl" if len(heavy) <= 6 else "alkyl"
    return "complex"


def _class_allowed(observed: str, allowed: set[str]) -> bool:
    if observed in allowed or "any" in allowed:
        return True
    for claimed in allowed:
        if observed in _SUBSUMES.get(claimed, {claimed}):
            return True
    return False


def scaffold_substituents(target_smiles: str, scaffold_smarts: str):
    tgt = Chem.MolFromSmiles(target_smiles)
    core = Chem.MolFromSmarts(scaffold_smarts)
    if tgt is None or core is None:
        return False, []
    match = tgt.GetSubstructMatch(core)
    if not match:
        return False, []
    core_atoms = set(match)
    exit_bonds = [
        b.GetIdx() for b in tgt.GetBonds()
        if (b.GetBeginAtomIdx() in core_atoms) ^ (b.GetEndAtomIdx() in core_atoms)
    ]
    if not exit_bonds:
        return True, []
    fragmented = Chem.FragmentOnBonds(tgt, exit_bonds, addDummies=True)
    subs = []
    for piece in Chem.GetMolFrags(fragmented, asMols=True, sanitizeFrags=False):
        _clean(piece)
        if piece.HasSubstructMatch(core):
            continue
        subs.append((classify_fragment(piece), Chem.MolToSmiles(piece)))
    return True, subs


def claim_covers(target_smiles: str, claim: dict) -> ClaimScopeResult:
    pid = claim.get("patent_id", "")
    cnum = claim.get("claim_number", 0)
    if claim.get("specific_smiles"):
        return _specific(target_smiles, claim, pid, cnum)
    if claim.get("labeled_core") and claim.get("rgroups"):
        return _positional(target_smiles, claim, pid, cnum)
    return _genus(target_smiles, claim, pid, cnum)


def _specific(target_smiles, claim, pid, cnum) -> ClaimScopeResult:
    from ..chem.structure import tanimoto
    sim = tanimoto(target_smiles, claim["specific_smiles"]) or 0.0
    covered = sim >= claim.get("identity_threshold", 0.98)
    return ClaimScopeResult(
        patent_id=pid, claim_number=cnum, covered=covered,
        verdict="covered" if covered else "specific-compound-mismatch",
        matched_scaffold=covered,
        substituents=[{"class": "identity", "smiles": claim["specific_smiles"],
                       "allowed": covered}],
        rationale=(f"Specific-compound claim (identity {sim:.2f}); "
                   + ("reads on this claim." if covered
                      else "target is not the claimed compound.")))


def _genus(target_smiles, claim, pid, cnum) -> ClaimScopeResult:
    scaffold = claim.get("scaffold_smarts", "")
    allowed = set(claim.get("allowed_classes", [])) | {"hydrogen"}
    matched, subs = scaffold_substituents(target_smiles, scaffold)
    if not matched:
        return ClaimScopeResult(
            patent_id=pid, claim_number=cnum, covered=False,
            verdict="scaffold-absent", scaffold_smarts=scaffold,
            rationale="Target does not contain the claimed scaffold; outside the genus.")
    if not claim.get("allowed_classes"):
        return ClaimScopeResult(
            patent_id=pid, claim_number=cnum, covered=True,
            verdict="scaffold-only-review", scaffold_smarts=scaffold,
            matched_scaffold=True,
            substituents=[{"class": c, "smiles": s, "allowed": None} for c, s in subs],
            rationale="Scaffold matches; substituent scope not specified -- "
                      "treat as potentially covered pending attorney review.")
    detail, outside = [], []
    for cls, smi in subs:
        ok = _class_allowed(cls, allowed)
        detail.append({"class": cls, "smiles": smi, "allowed": ok})
        if not ok:
            outside.append(cls)
    if outside:
        return ClaimScopeResult(
            patent_id=pid, claim_number=cnum, covered=False,
            verdict="substituent-outside", scaffold_smarts=scaffold,
            matched_scaffold=True, substituents=detail,
            rationale=(f"Scaffold matches, but target bears substituent class(es) "
                       f"{sorted(set(outside))} outside the claimed genus "
                       f"({sorted(allowed)})."))
    return ClaimScopeResult(
        patent_id=pid, claim_number=cnum, covered=True, verdict="covered",
        scaffold_smarts=scaffold, matched_scaffold=True, substituents=detail,
        rationale="Target contains the claimed scaffold and all substituents fall "
                  "within the claimed genus -- reads on this claim (triage).")


def _positional(target_smiles, claim, pid, cnum) -> ClaimScopeResult:
    tgt = Chem.MolFromSmiles(target_smiles)
    core = Chem.MolFromSmiles(claim["labeled_core"])
    if tgt is None or core is None:
        return ClaimScopeResult(pid, cnum, False, "scaffold-absent",
                                rationale="Unparseable target or labeled core.")
    try:
        res, unmatched = _rdRGD.RGroupDecompose([core], [tgt], asSmiles=True)
    except Exception:
        res, unmatched = [], [0]
    if not res or (unmatched and 0 in unmatched):
        return ClaimScopeResult(pid, cnum, False, "scaffold-absent",
                                scaffold_smarts=claim["labeled_core"],
                                rationale="Target does not contain the claimed core.")
    row = res[0]
    detail, outside = [], []
    for label, allowed_list in claim["rgroups"].items():
        rsmiles = row.get(label)
        allowed = set(allowed_list) | {"hydrogen"}
        cls = classify_fragment(Chem.MolFromSmiles(rsmiles)) if rsmiles else "hydrogen"
        ok = _class_allowed(cls, allowed)
        detail.append({"position": label, "class": cls, "smiles": rsmiles,
                       "allowed": ok})
        if not ok:
            outside.append((label, cls))
    if outside:
        return ClaimScopeResult(
            patent_id=pid, claim_number=cnum, covered=False,
            verdict="substituent-outside", scaffold_smarts=claim["labeled_core"],
            matched_scaffold=True, substituents=detail,
            rationale=(f"Core matches, but position(s) "
                       f"{[f'{l}={c}' for l, c in outside]} fall outside the "
                       f"claimed per-position genus."))
    return ClaimScopeResult(
        patent_id=pid, claim_number=cnum, covered=True, verdict="covered",
        scaffold_smarts=claim["labeled_core"], matched_scaffold=True,
        substituents=detail,
        rationale="Core matches and every claimed position is within its "
                  "per-position genus -- reads on this claim (triage).")


def claims_for_patent(patent) -> list[dict]:
    if settings.mock:
        from ..data.mock_data import MOCK_MARKUSH
        return MOCK_MARKUSH.get(patent.id, [])
    from .claim_parser import parse_genus_from_claim
    genera = []
    for c in getattr(patent, "claims", []):
        if getattr(c, "is_markush", False):
            g = parse_genus_from_claim(c.text)
            if g:
                g.update({"patent_id": patent.id, "claim_number": c.number})
                genera.append(g)
    return genera
