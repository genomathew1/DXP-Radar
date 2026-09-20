#!/usr/bin/env python3
"""Evaluation harness.

Computes the metrics named in the Module 6 safety plan against the
mock dataset's golden set:

- correctness: share of clusters whose status (and, where auto-
  published, implication) matches the hand-labeled golden set
- escalation_rate: share of clusters routed to PM review
- fallback_rate: share of clusters flagged insufficient_evidence
- safety_catch_rate: share of input-check-flagged clusters that were
  actually escalated for that reason (did the guardrail do its job?)
- revision_rate: share of clusters that needed a Strategist revision
  before passing the Critic's hard gates
- groundedness: share of published/escalated sections carrying at
  least one citation
- latency_ms: total and per-cluster wall-clock time through the
  pipeline (the mock LLM makes this trivially fast; it is the metric
  slot a real model backend would report into)

Usage:
    python eval/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dxp_radar.orchestrator import Orchestrator  # noqa: E402

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"
RESULTS_PATH = Path(__file__).parent / "results.json"


def load_golden_set() -> dict:
    data = json.loads(GOLDEN_SET_PATH.read_text())
    data.pop("_comment", None)
    return data


def evaluate() -> dict:
    orchestrator = Orchestrator(ROOT / "data" / "mock_signals.json", ROOT / "data" / "cluster_hints.json")
    result = orchestrator.run()
    golden = load_golden_set()

    total = len(result.brief_sections)
    correct = 0
    escalated = 0
    insufficient = 0
    grounded = 0
    safety_flagged_clusters = {
        cid for cid, spec in golden.items() if spec.get("expected_reason") == "input_check_flag"
    }
    safety_caught = 0

    per_cluster = []
    for section in result.brief_sections:
        spec = golden.get(section.cluster_id, {})
        is_correct = section.status == spec.get("expected_status")
        if is_correct and section.status == "auto_published":
            implied = section.headline.rsplit("—", 1)[-1].strip().lower()
            is_correct = implied == spec.get("expected_implication")
        if is_correct and section.status == "escalated":
            is_correct = section.escalation_reason == spec.get("expected_reason")
        correct += int(is_correct)

        if section.status == "escalated":
            escalated += 1
        if section.status == "insufficient_evidence":
            insufficient += 1
        if section.citations:
            grounded += 1
        if section.cluster_id in safety_flagged_clusters and section.escalation_reason == "input_check_flag":
            safety_caught += 1

        per_cluster.append(
            {
                "cluster_id": section.cluster_id,
                "status": section.status,
                "escalation_reason": section.escalation_reason,
                "matches_golden_label": is_correct,
            }
        )

    revise_events = [t for t in result.trace if t.action == "revise"]
    clusters_revised = {t.cluster_id for t in revise_events}
    total_latency_ms = sum(t.elapsed_ms for t in result.trace)

    metrics = {
        "clusters_evaluated": total,
        "correctness": round(correct / total, 3) if total else None,
        "escalation_rate": round(escalated / total, 3) if total else None,
        "fallback_rate": round(insufficient / total, 3) if total else None,
        "groundedness": round(grounded / total, 3) if total else None,
        "revision_rate": round(len(clusters_revised) / total, 3) if total else None,
        "safety_catch_rate": (
            round(safety_caught / len(safety_flagged_clusters), 3) if safety_flagged_clusters else None
        ),
        "total_latency_ms": round(total_latency_ms, 3),
        "per_cluster": per_cluster,
    }
    return metrics


def main() -> None:
    metrics = evaluate()
    RESULTS_PATH.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print(f"\n[results written to {RESULTS_PATH}]")


if __name__ == "__main__":
    main()
