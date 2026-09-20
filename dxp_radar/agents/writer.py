"""Writer: drafts the cited brief section from the winning interpretation.

Only ever invoked on a candidate that has already passed the Critic's
hard gates -- the Writer's job is presentation, not judgment, and it has
no path to override or re-score anything upstream.
"""

from __future__ import annotations

from ..schemas import BriefSection, ScoredCandidate, SignalRecord


def draft_section(signal: SignalRecord, winner: ScoredCandidate) -> BriefSection:
    citations = [f"[{item.source}]({item.url})" for item in signal.evidence]
    candidate = winner.candidate
    body = (
        f"{candidate.rationale} "
        f"(critic score {winner.score}/10). "
        f"Recommended action: {candidate.recommended_action}"
    )
    return BriefSection(
        cluster_id=signal.cluster_id,
        headline=f"{signal.claim} — {candidate.implication.upper()}",
        body=body,
        citations=citations,
        status="auto_published",
    )


def draft_escalation(signal: SignalRecord, winner: ScoredCandidate | None, reason: str) -> BriefSection:
    citations = [f"[{item.source}]({item.url})" for item in signal.evidence]
    if winner is not None:
        body = (
            f"Top candidate: {winner.candidate.implication} "
            f"(score {winner.score}/10). Escalated for PM review: {reason}."
        )
    else:
        body = f"No candidate passed the hard gates. Escalated for PM review: {reason}."
    return BriefSection(
        cluster_id=signal.cluster_id,
        headline=f"{signal.claim} — NEEDS PM REVIEW",
        body=body,
        citations=citations,
        status="escalated",
        escalation_reason=reason,
    )


def draft_insufficient_evidence(signal: SignalRecord) -> BriefSection:
    return BriefSection(
        cluster_id=signal.cluster_id,
        headline=f"{signal.claim} — INSUFFICIENT EVIDENCE",
        body="No candidate interpretation passed the hard evidence gates after one revision.",
        citations=[f"[{item.source}]({item.url})" for item in signal.evidence],
        status="insufficient_evidence",
    )


class Writer:
    def write(self, signal: SignalRecord, winner: ScoredCandidate) -> BriefSection:
        return draft_section(signal, winner)

    def write_escalation(self, signal: SignalRecord, winner: ScoredCandidate | None, reason: str) -> BriefSection:
        return draft_escalation(signal, winner, reason)

    def write_insufficient_evidence(self, signal: SignalRecord) -> BriefSection:
        return draft_insufficient_evidence(signal)
