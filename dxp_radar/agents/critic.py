"""Critic: scores candidate interpretations and enforces hard gates.

Runs on a separate code path from the Strategist by design -- it never
sees the Strategist's confidence number, only the evidence and the
candidate's own text, so it cannot simply defer to a confident-sounding
rationale. This is the guardrail against self-grading called out in the
Module 4 and Module 6 submissions.
"""

from __future__ import annotations

from ..guardrails import evaluate_hard_gates
from ..schemas import Candidate, ScoredCandidate, SignalRecord

# A tiny mock "knowledge base" standing in for the PM's existing stack
# rank. A real system would query the shared MCP-backed store described
# in the architecture doc.
KNOWLEDGE_BASE_POSITIONS: dict[str, str] = {
    "developer_platform": "parity",
    "headless_cms": "threat",
}

WEIGHTS = {
    "evidence_grounding": 0.30,
    "source_freshness": 0.15,
    "consistency": 0.20,
    "relevance": 0.20,
    "calibration": 0.15,
}


def _evidence_grounding(signal: SignalRecord) -> float:
    # More independent sources = stronger grounding; capped at 3 sources.
    return min(signal.num_sources / 2, 1.0) * 10


def _source_freshness(signal: SignalRecord) -> float:
    from datetime import date

    age_days = (date.today() - signal.most_recent_date).days
    if age_days <= 30:
        return 10.0
    if age_days <= 90:
        return 7.0
    return 3.0


def _consistency(signal: SignalRecord, candidate: Candidate) -> float:
    prior = KNOWLEDGE_BASE_POSITIONS.get(signal.capability_dimension)
    if prior is None:
        return 6.0  # no prior position to be consistent or inconsistent with
    return 9.0 if candidate.implication == prior else 5.0


def _relevance(signal: SignalRecord) -> float:
    return 8.0 if signal.capability_dimension != "unclassified" else 3.0


def _calibration(candidate: Candidate, hedge_penalty: bool) -> float:
    base = candidate.confidence * 10
    return max(base - 4, 0) if hedge_penalty else base


def score_candidate(signal: SignalRecord, candidate: Candidate) -> ScoredCandidate:
    gate_failures = evaluate_hard_gates(signal, candidate)
    hedge_penalty = "unsupported_hedge_language" in gate_failures

    subscores = {
        "evidence_grounding": _evidence_grounding(signal),
        "source_freshness": _source_freshness(signal),
        "consistency": _consistency(signal, candidate),
        "relevance": _relevance(signal),
        "calibration": _calibration(candidate, hedge_penalty),
    }
    weighted = sum(subscores[k] * WEIGHTS[k] for k in WEIGHTS)

    return ScoredCandidate(
        candidate=candidate,
        score=round(weighted, 2),
        subscores=subscores,
        passed_hard_gates=not gate_failures,
        gate_failures=gate_failures,
    )


class Critic:
    def score_all(self, signal: SignalRecord, candidates: list[Candidate]) -> list[ScoredCandidate]:
        scored = [score_candidate(signal, c) for c in candidates]
        # Rank passing candidates above failing ones, then by score.
        scored.sort(key=lambda sc: (sc.passed_hard_gates, sc.score), reverse=True)
        return scored
