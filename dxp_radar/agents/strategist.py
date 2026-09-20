"""Strategist: proposes candidate readings of a signal cluster.

For a routine, well-sourced, single-reading cluster this collapses to
one candidate -- chain-of-thought, effectively Tree-of-Thought at
width 1. For an ambiguous cluster (multiple independent sources, or a
dimension the rubric treats as consequential) it proposes 2-3
candidates spanning the plausible stances, matching the ToT design in
the capstone's Module 4 submission.

The `revise` path is what lets the Strategist-Critic pair form a small
graph rather than a strict pipeline: on a Critic "revise" verdict, the
Strategist gets exactly one more turn with the failure reasons attached,
and must ground its rationale in the evidence explicitly rather than
hedge.
"""

from __future__ import annotations

from ..schemas import Candidate, SignalRecord

_STANCES = ("threat", "parity", "opportunity", "noise")


def _base_confidence(signal: SignalRecord) -> float:
    # More independent sources and a recognized capability dimension
    # both raise how confidently we can characterize the signal at all
    # (not which stance is right -- that's what the candidates are for).
    score = 0.4
    score += min(signal.num_sources, 3) * 0.15
    if signal.capability_dimension != "unclassified":
        score += 0.15
    return min(score, 0.95)


def _is_ambiguous(signal: SignalRecord) -> bool:
    return signal.num_sources >= 2 and signal.capability_dimension != "unclassified"


def generate_candidates(signal: SignalRecord, *, revising: bool = False, gate_failures: list[str] | None = None) -> list[Candidate]:
    base_conf = _base_confidence(signal)
    hedge = not revising  # first pass may hedge; revision must not

    def rationale(stance: str) -> str:
        sources = ", ".join(sorted({item.source for item in signal.evidence}))
        lead = "This probably means" if hedge else "Based on the cited evidence,"
        return (
            f"{lead} {signal.claim!r} represents a {stance} signal for the "
            f"{signal.capability_dimension} capability, per {sources}."
        )

    if signal.num_sources == 0:
        return [
            Candidate(
                implication="noise",
                rationale="No corroborating evidence was retrieved for this claim.",
                recommended_action="Discard; re-check next cycle if it resurfaces with sources.",
                confidence=0.1,
            )
        ]

    if not _is_ambiguous(signal):
        # Routine path: one grounded candidate, width 1.
        stance = "parity" if signal.num_sources >= 1 else "noise"
        return [
            Candidate(
                implication=stance,
                rationale=rationale(stance),
                recommended_action="Log to the competitive tracker; no stack-rank change proposed.",
                confidence=base_conf,
            )
        ]

    # Ambiguous path: propose the most plausible stances.
    candidates = []
    for stance in ("threat", "parity", "opportunity"):
        candidates.append(
            Candidate(
                implication=stance,
                rationale=rationale(stance),
                recommended_action={
                    "threat": "Flag for stack-rank review this cycle.",
                    "parity": "Log as parity; monitor for follow-on signals.",
                    "opportunity": "Route to PMM for a differentiation angle.",
                }[stance],
                confidence=base_conf - {"threat": 0.0, "parity": 0.05, "opportunity": 0.1}[stance],
            )
        )
    return candidates


class Strategist:
    def propose(self, signal: SignalRecord) -> list[Candidate]:
        return generate_candidates(signal)

    def revise(self, signal: SignalRecord, gate_failures: list[str]) -> list[Candidate]:
        return generate_candidates(signal, revising=True, gate_failures=gate_failures)
