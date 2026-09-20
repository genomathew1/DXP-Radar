"""Scout: pulls raw items from allowlisted sources.

In this prototype, "pulling" means reading a local mock dataset that
stands in for scheduled scrapes of competitor docs, analyst
publications, and MCP/GitHub registries. Swapping in real fetchers
(requests + an HTML/PDF parser, an RSS reader, a registry API client)
does not change anything downstream, because the Scout's only contract
with the rest of the system is the RawItem schema.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..schemas import RawItem


def load_raw_items(path: str | Path) -> list[RawItem]:
    """Read a JSON file of raw items (the mock stand-in for a live scrape)."""
    data = json.loads(Path(path).read_text())
    items = []
    for row in data:
        items.append(
            RawItem(
                source=row["source"],
                url=row["url"],
                published=date.fromisoformat(row["published"]),
                title=row["title"],
                text=row["text"],
                source_type=row.get("source_type", "competitor_doc"),
            )
        )
    return items


class Scout:
    """Read-only agent. Holds no write access to any downstream store."""

    def __init__(self, source_path: str | Path):
        self.source_path = source_path

    def run(self) -> list[RawItem]:
        return load_raw_items(self.source_path)
