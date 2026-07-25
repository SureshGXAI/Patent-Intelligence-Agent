# Patent Intelligence Agent

Chemistry/pharma IP triage from a **compound SMILES** to a **cited, auditable PDF**.

**Input:** a SMILES string.
**Output:** a PDF with an executive summary, multi-office patent landscape,
structural neighbours, novelty estimate (with full-text prior art),
**claim-scope-driven** freedom-to-operate triage, and a numbered **References**
section — plus an **audit manifest** so any run is reproducible and verifiable.

Runs **fully offline** out of the box (bundled data + RDKit). Flip one env flag
for live databases. Optional narrative enrichment runs on a **local Ollama** model.

> WARNING: **Not legal advice.** FTO and novelty outputs are triage signals with
> evidence attached to prioritise human review — never legal conclusions.

---

## Quick start

```bash
pip install -r requirements.txt

python -m patent_intel.cli "CC(=O)Oc1ccccc1C(=O)O" -o report.pdf
python -m patent_intel.cli "<SMILES>" -o report.pdf --json --audit-dir audit/
python -m patent_intel.demo                # offline: two sample PDFs + audit trail
pip install pytest && pytest -q            # 12 tests
```

## Claim-scope engine (Markush)

FTO's primary test is **genus membership**, not linked-compound proximity. Three
claim shapes are handled:

- **genus** — `scaffold_smarts` + `allowed_classes` (position-agnostic);
- **positional** — a labeled core (`[*:1]`, `[*:2]`, …) + per-position `rgroups`,
  checked via RDKit R-group decomposition so a class allowed at one position but
  not another is distinguished;
- **specific** — salt/polymorph/single-compound claims, tested by near-exact
  identity.

Substituent classification is **functional-group aware** (halogen, haloalkyl,
alkoxy, hydroxyl, amino, amide, ester, carboxyl, nitro, cyano, sulfonyl, aryl,
heteroaryl, cycloalkyl, heterocyclyl, lower/higher alkyl), with a subsumption
lattice so a broad claimed class ("alkyl") admits its narrower members. Verdicts:
`covered` / `scaffold-absent` / `substituent-outside` / `scaffold-only-review` /
`specific-compound-mismatch`. Proximity survives only as a fallback when no
structured genus is available.

A **claim-text → structured-genus parser** (`capabilities/claim_parser.py`) turns
Markush prose ("R1 is selected from the group consisting of …") into the engine's
class vocabulary, per variable. It deliberately errs broad (over-inclusion flags
more for review — the safe direction for FTO). Its honest gap: a scaffold SMARTS
isn't derivable from claim *text* alone, so parsed genera carry substituent scope
but no scaffold and yield `scaffold-only-review` until paired with a
formula/structure extractor.

Limits remain explicit: coarse classification; no nested Markush or "optionally
substituted"/"wherein" cross-constraints beyond the positional per-label sets.
It triages claim scope — it is not legal claim construction.

## Patent databases (multi-office + chemistry-aware)

Common adapter interface; results normalised, **de-duplicated by publication
number** (recording every DB a record was found in) and grouped by family:

| Source | Kind | Env credentials |
|---|---|---|
| **SureChEMBL** | structure search (SMILES→patents) | (open data) |
| **USPTO** | keyword/field | `PIA_USPTO_KEY` |
| **EPO OPS** | keyword/field | `PIA_EPO_OPS_KEY`, `PIA_EPO_OPS_SECRET` |
| **TIPO** (Taiwan) | keyword | `PIA_TIPO_KEY` |
| **KIPRIS** (Korea) | keyword | `PIA_KIPRIS_KEY` |
| **Lens.org** | keyword/full-text | `PIA_LENS_KEY` |
| PubChem | compound resolve + similarity | (none) |

Enable/order via `PIA_PATENT_SOURCES`. Sources without credentials are skipped
and noted (with a citation) in the report's coverage section.

## Legal-status feed & prior art

- **Legal status:** FTO's enforceability gate consults `legal_status.py` instead
  of a static field, and computes an **effective expiry** — statutory term plus
  US **patent-term adjustment (PTA)** days, or a **supplementary protection
  certificate / term extension (SPC)** date where present (SPC supersedes). Mock
  echoes bundled status; live templates INPADOC (EPO OPS legal service) with
  hooks for USPTO PTAB/assignment and national registers.
- **Full-text prior art:** `prior_art.py` supplements structural similarity with
  document references (patent + scholarly) a reviewer should read for
  anticipation. Live templates Lens full-text / EPO published-data.

## Audit, reproducibility & sign-off

Every run produces (via `--audit-dir`):
- a **JSONL event log** (append-only) of each pipeline step and DB query;
- a **manifest** with the input hash, a **deterministic analysis fingerprint**,
  the config snapshot, citation set, verdicts, and the **SHA-256 of the PDF**.

`AuditLog.verify(manifest, pdf_path, report)` recomputes the artifact checksum
and analysis fingerprint so a reviewer can confirm a PDF matches its manifest.

**Reviewer sign-off** (`patent_intel.review`) records attorney decisions against
a run in a **hash-chained** trail anchored to the analysis fingerprint — any
later edit to a note, decision, or ordering breaks the chain:

```bash
python -m patent_intel.review run.manifest.json \
    --reviewer "A. Attorney" --decision approved --notes "FTO cleared"
python -m patent_intel.review run.manifest.json --verify   # check the chain
```

## Local LLM (Ollama)

```bash
ollama serve && ollama pull llama3.1
export PIA_USE_LLM=true PIA_OLLAMA_MODEL=llama3.1     # PIA_OLLAMA_BASE if remote
```
If Ollama is unreachable the pipeline runs unchanged, minus the narrative.
