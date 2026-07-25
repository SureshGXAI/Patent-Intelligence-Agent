"""Chemical data source: PubChem PUG-REST (free, no API key).

In mock mode everything is served from the bundled dataset so the pipeline
runs with no network. In live mode this hits PubChem's public REST endpoints.
Live similarity search is asynchronous on PubChem (submit -> poll ListKey);
that flow is implemented in `similarity_search`.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from ..chem.structure import canonical_smiles, nearest
from ..config import settings
from ..data.mock_data import MOCK_COMPOUNDS


def _canon_mock() -> dict[str, str]:
    return {k: (canonical_smiles(v) or v) for k, v in MOCK_COMPOUNDS.items()}


def resolve(query: str) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Resolve input to (canonical_smiles, cid, name).

    Input is expected to be a SMILES string. If it parses as a structure it is
    used directly. As a convenience, a bare name is accepted too (mock lookup,
    or a live PubChem name->structure call).
    """
    smi = canonical_smiles(query)
    if smi is not None:
        # Valid structure. In live mode, look up the CID/name for citation.
        if not settings.mock:
            try:
                r = requests.get(
                    f"{settings.pubchem_base}/compound/smiles/"
                    f"{requests.utils.quote(smi)}/property/IUPACName/JSON",
                    timeout=settings.http_timeout,
                )
                if r.ok:
                    p = r.json()["PropertyTable"]["Properties"][0]
                    return smi, p.get("CID"), p.get("IUPACName")
            except Exception:
                pass
        # mock: try to name it from the bundled table
        name = {v: k for k, v in _canon_mock().items()}.get(smi)
        return smi, None, name

    # Not a structure -> treat as a name.
    if settings.mock:
        table = _canon_mock()
        key = query.strip().lower()
        return (table[key], None, key) if key in table else (None, None, None)
    try:
        r = requests.get(
            f"{settings.pubchem_base}/compound/name/{requests.utils.quote(query)}/"
            f"property/CanonicalSMILES/JSON",
            timeout=settings.http_timeout,
        )
        r.raise_for_status()
        props = r.json()["PropertyTable"]["Properties"][0]
        return canonical_smiles(props["CanonicalSMILES"]), props.get("CID"), query
    except Exception:
        return None, None, None


def similarity_search(
    smiles: str, threshold: float = 0.75, max_records: int = 25
) -> list[tuple[str, float, Optional[int]]]:
    """Return (smiles, tanimoto, cid) neighbours ranked by similarity.

    Mock mode ranks the bundled compounds by RDKit Tanimoto. Live mode submits
    a 2D similarity search to PubChem and polls for the result list.
    """
    if settings.mock:
        table = _canon_mock()
        ranked = nearest(smiles, list(table.values()))
        name_by_smiles = {v: k for k, v in table.items()}
        out = []
        for cand_smiles, sim in ranked:
            if sim >= threshold and cand_smiles != (canonical_smiles(smiles)):
                out.append((cand_smiles, sim, None))
        # if nothing passes threshold, still return the closest few for context
        if not out:
            out = [(s, sim, None) for s, sim in ranked[:3]]
        return out

    pct = int(round(threshold * 100))
    try:
        submit = requests.get(
            f"{settings.pubchem_base}/compound/similarity/smiles/"
            f"{requests.utils.quote(smiles)}/JSON?Threshold={pct}&MaxRecords={max_records}",
            timeout=settings.http_timeout,
        )
        submit.raise_for_status()
        listkey = submit.json()["Waiting"]["ListKey"]
        # poll
        cids: list[int] = []
        for _ in range(20):
            time.sleep(1.5)
            poll = requests.get(
                f"{settings.pubchem_base}/compound/listkey/{listkey}/cids/JSON",
                timeout=settings.http_timeout,
            )
            data = poll.json()
            if "IdentifierList" in data:
                cids = data["IdentifierList"]["CID"][:max_records]
                break
        if not cids:
            return []
        # fetch SMILES for the CIDs
        joined = ",".join(str(c) for c in cids)
        props = requests.get(
            f"{settings.pubchem_base}/compound/cid/{joined}/property/CanonicalSMILES/JSON",
            timeout=settings.http_timeout,
        ).json()["PropertyTable"]["Properties"]
        from ..chem.structure import tanimoto
        out = []
        for p in props:
            cs = canonical_smiles(p.get("CanonicalSMILES", ""))
            if not cs:
                continue
            sim = tanimoto(smiles, cs) or 0.0
            out.append((cs, sim, p.get("CID")))
        out.sort(key=lambda x: x[1], reverse=True)
        return out
    except Exception:
        return []
