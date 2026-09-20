"""The controller: owns the hybrid sequential/graph state machine.

Backbone is sequential -- Scout -> Analyst -> Strategist -> Critic ->
Writer -> PM confirm. Where a cluster is ambiguous and the top candidate
fails a hard gate, Strategist and Critic form a small graph: one
revision round-trip before the cluster is either written up or flagged
"insufficient evidence" for PM review. This is the same control-flow
shape as the ToT beam-search / LangGraph design in the Module 4 and
Module 5 submissions, implemented here in plain Python so the whole
pipeline runs with no framework dependency.

Every step appends a structured entry to `trace` -- sender, action, and
the state it touched -- which is what the README calls the audit log,
and what the eval harness reads to compute escalation rate and latency.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .agents.analyst import Analyst
from .agents.critic import Critic
from .agents.scout import Scout
from .agents.strategist import Strategist
from .agents.writer import Writer
from .guardrails import check_input, requires_escalation
from .schemas import BriefSection, RawItem, SignalRecord

MAX_REVISIONS = 1


@dataclass
class TraceEvent:
    agent: str
    action: str
    cluster_id: str | None
    detail: str
    elapsed_ms: float


@dataclass
class RunResult:
    brief_sections: list[BriefSection] = field(default_factory=list)
    trace: list[TraceEvent] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "brief_sections": [asdict(s) for s in self.brief_sections],
            "trace": [asdict(t) for t in self.trace],
        }


class Orchestrator:
    def __init__(self, source_path: str | Path, cluster_hint_path: str | Path):
        self.scout = Scout(source_path)
        self.analyst = Analyst(cluster_hint_path)
        self.strategist = Strategist()
        self.critic = Critic()
        self.writer = Writer()

    def _log(self, result: RunResult, agent: str, action: str, cluster_id: str | None, detail: str, t0: float) -> None:
        result.trace.append(
            TraceEvent(
                agent=agent,
                action=action,
                cluster_id=cluster_id,
                detail=detail,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 3),
            )
        )

    def _process_cluster(self, signal: SignalRecord, input_flagged: bool, result: RunResult) -> None:
        t0 = time.perf_counter()
        candidates = self.strategist.propose(signal)
        self._log(result, "Strategist", "propose", signal.cluster_id, f"{len(candidates)} candidate(s)", t0)

        t0 = time.perf_counter()
        scored = self.critic.score_all(signal, candidates)
        top = scored[0]
        second_score = scored[1].score if len(scored) > 1 else None
        self._log(
            result, "Critic", "score", signal.cluster_id,
            f"top={top.candidate.implication}:{top.score} gates_passed={top.passed_hard_gates}", t0,
        )

        revisions = 0
        while not top.passed_hard_gates and revisions < MAX_REVISIONS:
            t0 = time.perf_counter()
            candidates = self.strategist.revise(signal, top.gate_failures)
            self._log(result, "Strategist", "revise", signal.cluster_id, f"retry {revisions + 1}", t0)

            t0 = time.perf_counter()
            scored = self.critic.score_all(signal, candidates)
            top = scored[0]
            second_score = scored[1].score if len(scored) > 1 else None
            self._log(
                result, "Critic", "re-score", signal.cluster_id,
                f"top={top.candidate.implication}:{top.score} gates_passed={top.passed_hard_gates}", t0,
            )
            revisions += 1

        if not top.passed_hard_gates:
            t0 = time.perf_counter()
            section = self.writer.write_insufficient_evidence(signal)
            self._log(result, "Writer", "write_insufficient_evidence", signal.cluster_id, "flagged for PM", t0)
            result.brief_sections.append(section)
            return

        escalate, reason = requires_escalation(
            top_score=top.score,
            second_score=second_score,
            capability_dimension=signal.capability_dimension,
            input_flagged=input_flagged,
        )

        t0 = time.perf_counter()
        if escalate:
            section = self.writer.write_escalation(signal, top, reason or "unspecified")
            self._log(result, "Writer", "write_escalation", signal.cluster_id, reason or "", t0)
        else:
            section = self.writer.write(signal, top)
            self._log(result, "Writer", "write", signal.cluster_id, "auto-published", t0)
        result.brief_sections.append(section)

    def run(self) -> RunResult:
        result = RunResult()

        t0 = time.perf_counter()
        raw_items = self.scout.run()
        self._log(result, "Scout", "fetch", None, f"{len(raw_items)} raw item(s)", t0)

        flagged_urls: set[str] = set()
        for item in raw_items:
            check = check_input(item)
            if not check.is_safe:
                flagged_urls.add(item.url)
                self._log(result, "InputCheck", "flag", None, f"{item.url}: {check.flags}", time.perf_counter())

        t0 = time.perf_counter()
        signals = self.analyst.run(raw_items)
        self._log(result, "Analyst", "cluster", None, f"{len(signals)} cluster(s)", t0)

        for signal in signals:
            input_flagged = any(item.url in flagged_urls for item in signal.evidence)
            self._process_cluster(signal, input_flagged, result)

        return result
