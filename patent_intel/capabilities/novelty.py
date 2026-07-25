"""Novelty / non-obviousness estimation (triage heuristic).

Transparent scoring so a reviewer can see exactly why a verdict was reached:
  * exact / near-exact structural match to prior art  -> "anticipated"
  * high similarity below that                        -> "obviousness-risk"
  * no close art                                      -> "likely-novel"

Structural similarity is only a proxy. Real anticipation turns on whether a
single prior-art reference discloses the claimed subject matter, and
obviousness on the statutory multi-factor test. Output is for triage only.
"""
from __future__ import annotations

from ..config import settings
from ..models import Compound, CompoundHit, NoveltyResult
from . import similar_compounds


def estimate(compound: Compound) -> NoveltyResult:
    if not compound.smiles:
        return NoveltyResult(
            target=compound,
            novelty_score=0.0,
            verdict="unknown",
            rationale="Could not resolve the query to a valid structure.",
        )

    hits = similar_compounds.find(compound.smiles, threshold=0.0)
    # exclude the compound itself
    hits = [h for h in hits if h.smiles != compound.smiles]
    hits.sort(key=lambda h: h.similarity, reverse=True)
    closest = hits[:5]

    if not closest:
        return NoveltyResult(
            target=compound,
            novelty_score=1.0,
            verdict="likely-novel",
            closest_art=[],
            rationale="No structurally related prior art found in the searched "
            "sources. Expand the corpus before relying on this.",
        )

    top = closest[0].similarity
    if top >= settings.anticipation_tanimoto:
        verdict = "anticipated"
        rationale = (
            f"Near-identical structure already disclosed "
            f"(Tanimoto {top:.2f}); likely anticipated by prior art"
        )
        if closest[0].disclosed_in:
            rationale += f" in {', '.join(closest[0].disclosed_in)}"
        rationale += "."
    elif top >= settings.obviousness_tanimoto:
        verdict = "obviousness-risk"
        rationale = (
            f"Close structural analogue exists (Tanimoto {top:.2f}); "
            f"obviousness/inventive-step objections are plausible."
        )
    else:
        verdict = "likely-novel"
        rationale = (
            f"Closest prior art is structurally distinct (Tanimoto {top:.2f}); "
            f"no anticipation signal, but confirm against full-text prior art."
        )

    return NoveltyResult(
        target=compound,
        novelty_score=round(1.0 - top, 4),
        verdict=verdict,
        closest_art=closest,
        rationale=rationale,
    )
