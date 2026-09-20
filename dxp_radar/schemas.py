"""Typed data structures passed between agents.

These mirror the structured, schema-based handoffs described in the
capstone design docs: agents exchange these objects (through shared
state in the orchestrator) rather than free-text chat, so downstream
agents never have to re-parse prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

ImplicationType = Literal["threat", "parity", "opportunity", "noise"]


@dataclass
class RawItem:
    """A single unprocessed item pulled by the Scout agent."""

    source: str
    url: str
    published: date
    title: str
    text: str
    source_type: Literal["competitor_doc", "analyst_report", "registry"] = "competitor_doc"


@dataclass
class SignalRecord:
    """A structured signal produced by the Analyst agent from one or more RawItems."""

    cluster_id: str
    claim: str
    capability_dimension: str
    evidence: list[RawItem] = field(default_factory=list)

    @property
    def num_sources(self) -> int:
        return len({item.url for item in self.evidence})

    @property
    def most_recent_date(self) -> date:
        return max(item.published for item in self.evidence)


@dataclass
class Candidate:
    """One candidate interpretation proposed by the Strategist agent."""

    implication: ImplicationType
    rationale: str
    recommended_action: str
    confidence: float  # 0-1, self-reported by the Strategist


@dataclass
class ScoredCandidate:
    """A Candidate after the Critic agent has scored it against the rubric."""

    candidate: Candidate
    score: float  # 0-10, weighted rubric score
    subscores: dict[str, float]
    passed_hard_gates: bool
    gate_failures: list[str] = field(default_factory=list)


@dataclass
class BriefSection:
    """The Writer agent's cited output for one signal cluster."""

    cluster_id: str
    headline: str
    body: str
    citations: list[str]
    status: Literal["auto_published", "escalated", "insufficient_evidence"]
    escalation_reason: str | None = None
