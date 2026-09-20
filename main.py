#!/usr/bin/env python3
"""CLI entry point: run the DXP Radar pipeline over the mock dataset.

Usage:
    python main.py
    python main.py --out sample_outputs/brief_example.md --trace sample_outputs/trace_log_example.json

No API key is required -- the reasoning agents use documented,
deterministic heuristics unless ANTHROPIC_API_KEY is set (see
dxp_radar/llm.py).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dxp_radar.orchestrator import Orchestrator

ROOT = Path(__file__).parent
DEFAULT_SIGNALS = ROOT / "data" / "mock_signals.json"
DEFAULT_HINTS = ROOT / "data" / "cluster_hints.json"


def render_markdown(result) -> str:
    lines = ["# DXP Radar — Weekly Competitive Brief\n"]
    status_emoji = {
        "auto_published": "✅",
        "escalated": "\U0001F6A9",
        "insufficient_evidence": "❓",
    }
    for section in result.brief_sections:
        lines.append(f"## {status_emoji.get(section.status, '')} {section.headline}\n")
        lines.append(section.body + "\n")
        if section.escalation_reason:
            lines.append(f"*Escalation reason: {section.escalation_reason}*\n")
        lines.append("Sources: " + ", ".join(section.citations) + "\n")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DXP Radar pipeline.")
    parser.add_argument("--signals", default=str(DEFAULT_SIGNALS))
    parser.add_argument("--hints", default=str(DEFAULT_HINTS))
    parser.add_argument("--out", default=None, help="Write the rendered brief (Markdown) to this path.")
    parser.add_argument("--trace", default=None, help="Write the full run trace (JSON) to this path.")
    args = parser.parse_args()

    orchestrator = Orchestrator(args.signals, args.hints)
    result = orchestrator.run()

    brief_md = render_markdown(result)
    print(brief_md)

    if args.out:
        Path(args.out).write_text(brief_md)
        print(f"\n[written to {args.out}]")
    if args.trace:
        Path(args.trace).write_text(json.dumps(result.as_dict(), indent=2, default=str))
        print(f"[trace written to {args.trace}]")


if __name__ == "__main__":
    main()
