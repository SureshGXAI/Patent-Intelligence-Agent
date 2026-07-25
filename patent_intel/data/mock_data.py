"""Bundled dataset so the whole pipeline runs offline (mock mode).

Illustrative kinase-inhibitor sample data ONLY -- not a curated legal dataset.
SMILES are real so RDKit scoring is meaningful. Patents are spread across
offices and some publication numbers are returned by more than one database so
that de-duplication, family grouping and multi-source citations are exercised
offline.
"""
from __future__ import annotations

# name -> SMILES
MOCK_COMPOUNDS = {
    "imatinib": "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5",
    "nilotinib": "Cc1cn(cn1)-c1cc(cc(c1)C(F)(F)F)NC(=O)c1ccc(C)c(c1)Nc1nccc(n1)-c1cccnc1",
    "dasatinib": "CC1=C(C(=CC=C1)Cl)NC(=O)C2=CN=C(S2)NC3=CC(=NC(=N3)C)N4CCN(CC4)CCO",
    "aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
}

# Flat list of patent records. `source` = which database returned it.
# Records sharing `family_id` are members of one INPADOC-style family (kept
# separate because each jurisdiction matters for FTO).
MOCK_PATENT_RECORDS = [
    # --- Family F1: imatinib composition (expired) ---
    {
        "id": "US5521184A", "source": "uspto", "family_id": "F1",
        "title": "Pyrimidine derivatives and processes for their preparation",
        "assignee": "Novartis AG", "priority_date": "1993-04-28",
        "grant_date": "1996-05-28", "expiry_date": "2013-04-28",
        "jurisdiction": "US", "legal_status": "expired",
        "abstract": "N-phenyl-2-pyrimidineamine derivatives useful as protein "
        "kinase inhibitors, and pharmaceutical compositions thereof.",
        "linked_compounds": ["imatinib"],
        "claims": (
            "1. A compound of formula I, or a pharmaceutically acceptable salt "
            "thereof, wherein R1 is selected from the group consisting of "
            "hydrogen, lower alkyl, and halogen.\n"
            "2. A compound according to claim 1 wherein R1 is methyl.\n"
            "3. A pharmaceutical composition comprising a compound according to "
            "claim 1 and a pharmaceutically acceptable carrier.\n"
            "4. A method of treating a kinase-mediated disease comprising "
            "administering a compound according to claim 1.\n"
        ),
    },
    {  # same invention, EP member, via EPO OPS
        "id": "EP0564409B1", "source": "epo_ops", "family_id": "F1",
        "title": "Pyrimidine derivatives and processes for their preparation",
        "assignee": "Novartis AG", "priority_date": "1993-04-28",
        "grant_date": "1997-10-15", "expiry_date": "2013-03-31",
        "spc_expiry": "2016-12-16",
        "jurisdiction": "EP", "legal_status": "expired",
        "abstract": "N-phenyl-2-pyrimidineamine kinase inhibitors (EP grant).",
        "linked_compounds": ["imatinib"],
        "claims": "1. A compound of formula I as a kinase inhibitor.\n",
    },
    {  # same invention, TW member, via TIPO
        "id": "TWI238820B", "source": "tipo", "family_id": "F1",
        "title": "Pyrimidine derivative kinase inhibitors",
        "assignee": "Novartis AG", "priority_date": "1993-04-28",
        "grant_date": "2005-09-01", "expiry_date": "2013-04-28",
        "jurisdiction": "TW", "legal_status": "expired",
        "abstract": "N-phenyl-2-pyrimidineamine kinase inhibitors (TW member).",
        "linked_compounds": ["imatinib"],
        "claims": "1. A pyrimidineamine compound useful as a kinase inhibitor.\n",
    },
    {  # US5521184A ALSO surfaced by Lens (aggregator) -> should dedupe
        "id": "US5521184A", "source": "lens", "family_id": "F1",
        "title": "Pyrimidine derivatives and processes for their preparation",
        "assignee": "Novartis AG", "priority_date": "1993-04-28",
        "grant_date": "1996-05-28", "expiry_date": "2013-04-28",
        "jurisdiction": "US", "legal_status": "expired",
        "abstract": "Kinase inhibitor pyrimidineamines (Lens aggregated record).",
        "linked_compounds": ["imatinib"],
        "claims": "1. A compound of formula I.\n",
    },

    # --- Family F2: nilotinib salt (IN FORCE) ---
    {
        "id": "US7169791B2", "source": "uspto", "family_id": "F2",
        "title": "Salts of pyrimidine kinase inhibitors",
        "assignee": "Novartis AG", "priority_date": "2004-02-11",
        "grant_date": "2007-01-30", "expiry_date": "2031-02-11", "pta_days": 137,
        "jurisdiction": "US", "legal_status": "active",
        "abstract": "Crystalline salt forms of an N-phenyl-2-pyrimidineamine "
        "kinase inhibitor with improved stability.",
        "linked_compounds": ["nilotinib"],
        "claims": (
            "1. A crystalline salt of the compound of formula II selected from "
            "the group consisting of the hydrochloride, mesylate, and tosylate "
            "salts.\n"
            "2. The crystalline salt according to claim 1 which is the mesylate.\n"
            "3. A pharmaceutical composition comprising the crystalline salt of "
            "claim 1.\n"
        ),
    },
    {  # KR member via KIPRIS, also in force
        "id": "KR100927545B1", "source": "kipris", "family_id": "F2",
        "title": "Crystalline salt forms of a kinase inhibitor",
        "assignee": "Novartis AG", "priority_date": "2004-02-11",
        "grant_date": "2009-11-17", "expiry_date": "2031-02-11",
        "jurisdiction": "KR", "legal_status": "active",
        "abstract": "Crystalline salts of an N-phenyl-2-pyrimidineamine (KR grant).",
        "linked_compounds": ["nilotinib"],
        "claims": "1. A crystalline mesylate salt of the compound of formula II.\n",
    },
    {  # nilotinib salt ALSO surfaced by Lens -> dedupe with USPTO record
        "id": "US7169791B2", "source": "lens", "family_id": "F2",
        "title": "Salts of pyrimidine kinase inhibitors",
        "assignee": "Novartis AG", "priority_date": "2004-02-11",
        "grant_date": "2007-01-30", "expiry_date": "2031-02-11",
        "jurisdiction": "US", "legal_status": "active",
        "abstract": "Crystalline salt kinase inhibitor (Lens aggregated record).",
        "linked_compounds": ["nilotinib"],
        "claims": "1. A crystalline salt of the compound of formula II.\n",
    },

    # --- Family F3: dasatinib scaffold (expired) ---
    {
        "id": "US6596746B1", "source": "uspto", "family_id": "F3",
        "title": "Thiazole compounds as kinase inhibitors",
        "assignee": "Bristol-Myers Squibb", "priority_date": "2000-12-20",
        "grant_date": "2003-07-22", "expiry_date": "2021-12-20",
        "jurisdiction": "US", "legal_status": "expired",
        "abstract": "Aminothiazole carboxamides that inhibit Src-family kinases.",
        "linked_compounds": ["dasatinib"],
        "claims": (
            "1. A compound comprising a 2-aminothiazole-5-carboxamide core "
            "wherein the amide nitrogen bears a substituted phenyl group.\n"
            "2. The compound of claim 1 for use in treating cancer.\n"
        ),
    },
    {  # EP member via EPO OPS
        "id": "EP1348706B1", "source": "epo_ops", "family_id": "F3",
        "title": "Aminothiazole kinase inhibitors",
        "assignee": "Bristol-Myers Squibb", "priority_date": "2000-12-20",
        "grant_date": "2006-05-24", "expiry_date": "2021-12-20",
        "jurisdiction": "EP", "legal_status": "expired",
        "abstract": "2-Aminothiazole-5-carboxamide Src-kinase inhibitors (EP).",
        "linked_compounds": ["dasatinib"],
        "claims": "1. A 2-aminothiazole-5-carboxamide kinase inhibitor.\n",
    },
]

# Backward-compatible dict view keyed by publication number (first occurrence).
MOCK_PATENTS = {}
for _r in MOCK_PATENT_RECORDS:
    MOCK_PATENTS.setdefault(_r["id"], _r)


# Structured Markush genus definitions for the claim-scope engine.
# patent_id -> list of {claim_number, scaffold_smarts, allowed_classes, description}
# Illustrative only. Scaffolds are SMARTS; allowed_classes are substituent classes
# permitted at the genus's variable positions.
MOCK_MARKUSH = {
    "US5521184A": [{
        "patent_id": "US5521184A", "claim_number": 1,
        "scaffold_smarts": "c1ccc(Nc2ncccn2)cc1",   # N-phenyl-2-pyrimidineamine
        "allowed_classes": ["hydrogen", "halogen", "lower_alkyl", "alkyl",
                            "aryl", "heteroaryl", "complex"],
        "description": "N-phenyl-2-pyrimidineamine kinase-inhibitor genus.",
    }],
    "US7169791B2": [{
        "patent_id": "US7169791B2", "claim_number": 1,
        "specific_smiles": "Cc1cn(cn1)-c1cc(cc(c1)C(F)(F)F)NC(=O)c1ccc(C)c(c1)Nc1nccc(n1)-c1cccnc1",
        "identity_threshold": 0.95,
        "description": "Crystalline salt forms of nilotinib (specific compound).",
    }],
    "US6596746B1": [{
        "patent_id": "US6596746B1", "claim_number": 1,
        "scaffold_smarts": "O=C(Nc1ccccc1)c1cncs1",  # aminothiazole-carboxamide
        "allowed_classes": ["hydrogen", "halogen", "lower_alkyl", "aryl",
                            "heteroaryl", "complex"],
        "description": "2-aminothiazole-5-carboxamide Src-kinase genus.",
    }],
}
