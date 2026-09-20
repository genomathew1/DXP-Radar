"""Analyst: normalizes raw items into structured, clustered SignalRecords.

Grouping related items is a retrieval/embedding problem in a production
system (cluster by semantic similarity over titles + text). This
prototype keeps that step honest and simple: each mock RawItem carries a
`cluster_hint` (the mock stand-in for "these three items are about the
same underlying event"), and the Analyst groups on that hint and tags a
capability dimension from a small keyword map. Swapping in a real
embedding-based clusterer only changes the body of `_cluster`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schemas import RawItem, SignalRecord

# Ordered by specificity, not alphabetically: a more specific or higher-
# stakes term (pricing, legal) must be checked before a broader one
# (headless) that might also appear in the same sentence, or a pricing
# change described on a headless-CMS page would be misclassified as a
# routine platform update instead of the policy-sensitive dimension it
# actually is. This ordering bug was caught during evaluation (see
# eval/README notes) -- an argument for the eval harness catching
# exactly the kind of silent misclassification that would otherwise
# slip a pricing signal past the policy-sensitive escalation rule.
_DIMENSION_KEYWORDS: list[tuple[str, str]] = [
    ("pricing", "pricing"),
    ("price", "pricing"),
    ("license", "legal"),
    ("terms of service", "legal"),
    ("model context protocol", "developer_platform"),
    ("mcp", "developer_platform"),
    ("headless", "headless_cms"),
    ("cdn", "cdn_performance"),
    ("build your own", "byo_template"),
    ("template", "byo_template"),
    ("portal", "use_case_portals"),
]


def infer_capability_dimension(items: list[RawItem]) -> str:
    text = " ".join(item.title.lower() + " " + item.text.lower() for item in items)
    for keyword, dimension in _DIMENSION_KEYWORDS:
        if keyword in text:
            return dimension
    return "unclassified"


def _cluster(items: list[RawItem], hints: dict[str, str]) -> dict[str, list[RawItem]]:
    clusters: dict[str, list[RawItem]] = {}
    for item in items:
        cluster_id = hints.get(item.url, item.url)
        clusters.setdefault(cluster_id, []).append(item)
    return clusters


def _summarize_claim(items: list[RawItem]) -> str:
    # A real Analyst would call the model to synthesize one claim
    # sentence from the cluster; the prototype uses the lead item's
    # title, which is already a faithful one-line claim in the mock
    # dataset.
    lead = min(items, key=lambda i: i.published)
    return lead.title


class Analyst:
    def __init__(self, hint_path: str | Path):
        self._hints: dict[str, str] = json.loads(Path(hint_path).read_text())

    def run(self, items: list[RawItem]) -> list[SignalRecord]:
        clusters = _cluster(items, self._hints)
        records = []
        for cluster_id, cluster_items in clusters.items():
            records.append(
                SignalRecord(
                    cluster_id=cluster_id,
                    claim=_summarize_claim(cluster_items),
                    capability_dimension=infer_capability_dimension(cluster_items),
                    evidence=cluster_items,
                )
            )
        return records
