"""Structural guardrails: input checks, hard output gates, and escalation rules.

These implement the guardrail categories from the Module 6 safety plan:
input checks, source verification, tool access limits, output
constraints, and escalation rules. Nothing here depends on a model call
-- these are deterministic checks, on purpose, so they cannot be
argued or prompt-injected around.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .schemas import Candidate, RawItem, SignalRecord

# --- Source verification -----------------------------------------------

ALLOWED_SOURCE_TYPES = {"competitor_doc", "analyst_report", "registry"}

# --- Input checks --------------------------------------------------------

# A short, illustrative list of patterns that indicate a scraped page is
# trying to address instructions directly to the agent, rather than
# describing a product. This is intentionally simple and pattern-level:
# a real deployment would use a dedicated classifier, not a keyword list.
_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "you are now",
    "disregard the above",
    "act as if",
)


@dataclass
class InputCheckResult:
    is_safe: bool
    flags: list[str]


def check_input(item: RawItem) -> InputCheckResult:
    """Flag scraped content that looks like it is addressing the agent
    directly rather than describing a product or market fact."""
    text_lower = item.text.lower()
    flags = [marker for marker in _INJECTION_MARKERS if marker in text_lower]
    return InputCheckResult(is_safe=not flags, flags=flags)


# --- Output / hard gates --------------------------------------------------

FRESHNESS_LIMIT_DAYS = 90


def evaluate_hard_gates(signal: SignalRecord, candidate: Candidate) -> list[str]:
    """Deterministic, non-negotiable checks. Any failure here prunes the
    candidate outright, regardless of how well the critic score reads."""
    failures: list[str] = []

    if signal.num_sources == 0:
        failures.append("no_evidence")

    if not all(item.url for item in signal.evidence):
        failures.append("citation_missing_url")

    age_days = (date.today() - signal.most_recent_date).days
    if age_days > FRESHNESS_LIMIT_DAYS:
        failures.append(f"evidence_stale_{age_days}d")

    if not signal.capability_dimension:
        failures.append("missing_capability_dimension")

    if any(marker in candidate.rationale.lower() for marker in ("i assume", "probably", "i guess")):
        failures.append("unsupported_hedge_language")

    return failures


# --- Escalation rules ------------------------------------------------------

CRITIC_SCORE_THRESHOLD = 7.5
TIE_MARGIN = 0.5

# Signals about these capability dimensions are treated as policy-sensitive
# regardless of score, and always route to the PM.
POLICY_SENSITIVE_DIMENSIONS = {"pricing", "legal", "contractual_terms"}


def requires_escalation(
    top_score: float,
    second_score: float | None,
    capability_dimension: str,
    input_flagged: bool,
) -> tuple[bool, str | None]:
    """Return (should_escalate, reason)."""
    if input_flagged:
        return True, "input_check_flag"
    if capability_dimension in POLICY_SENSITIVE_DIMENSIONS:
        return True, "policy_sensitive_dimension"
    if top_score < CRITIC_SCORE_THRESHOLD:
        return True, "low_confidence"
    if second_score is not None and (top_score - second_score) < TIE_MARGIN:
        return True, "tie_between_candidates"
    return False, None
