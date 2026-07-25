"""Chemistry primitives built on RDKit.

Kept deliberately small and pure so they can be unit-tested without any
network access. This is the deterministic backbone of similarity, novelty
and FTO scoring.
"""
from __future__ import annotations

from typing import Optional

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, DataStructs

RDLogger.DisableLog("rdApp.*")  # silence parse warnings; we handle None ourselves

_FP_RADIUS = 2
_FP_BITS = 2048


def mol_from_smiles(smiles: str):
    if not smiles:
        return None
    return Chem.MolFromSmiles(smiles)


def canonical_smiles(smiles: str) -> Optional[str]:
    """Return canonical SMILES, or None if the input can't be parsed."""
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def fingerprint(smiles: str):
    """Morgan (ECFP4-like) fingerprint as an RDKit bit vector, or None."""
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(mol, _FP_RADIUS, nBits=_FP_BITS)


def tanimoto(smiles_a: str, smiles_b: str) -> Optional[float]:
    """Tanimoto similarity in [0, 1]; None if either structure is invalid."""
    fp_a = fingerprint(smiles_a)
    fp_b = fingerprint(smiles_b)
    if fp_a is None or fp_b is None:
        return None
    return float(DataStructs.TanimotoSimilarity(fp_a, fp_b))


def substructure_match(query_smarts: str, target_smiles: str) -> bool:
    """True if target contains the query substructure (SMARTS or SMILES)."""
    target = mol_from_smiles(target_smiles)
    if target is None:
        return False
    patt = Chem.MolFromSmarts(query_smarts) or Chem.MolFromSmiles(query_smarts)
    if patt is None:
        return False
    return target.HasSubstructMatch(patt)


def nearest(query_smiles: str, candidates: list[str]) -> list[tuple[str, float]]:
    """Rank candidate SMILES by Tanimoto to the query, descending.

    Invalid candidates are skipped. Returns (smiles, similarity) pairs.
    """
    q_fp = fingerprint(query_smiles)
    if q_fp is None:
        return []
    scored: list[tuple[str, float]] = []
    for cand in candidates:
        fp = fingerprint(cand)
        if fp is None:
            continue
        scored.append((cand, float(DataStructs.TanimotoSimilarity(q_fp, fp))))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
