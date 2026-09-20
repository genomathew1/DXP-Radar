# DXP Radar

A multi-agent competitive & analyst intelligence assistant for Salesforce Experience Cloud product management, built as a capstone for the CMU Agentic AI Program.

DXP Radar monitors competitor documentation, analyst publications, and MCP/developer registries, clusters related signals, reasons about what each cluster means competitively, and drafts a cited, PM-ready brief — with guardrails and a human-in-the-loop escalation path for anything ambiguous, policy-sensitive, or under-evidenced.

## The problem

A Digital Experience Platform PM tracks competitor moves across dozens of scattered sources (release notes, analyst notes, registries, forums) and has to turn that into an evidence-backed point of view fast enough to matter for stack-rank and roadmap decisions. Doing this by hand doesn't scale, and a single generalist LLM prompt over the same sources tends to retrieve shallowly and state an unverified reading with false confidence. DXP Radar is built for that PM (this repo's author, a Salesforce Experience Cloud PM), as a domain-specific research assistant rather than a generic summarizer.

## Architecture

Five single-responsibility agents hand off structured, typed objects (see `dxp_radar/schemas.py`) through a controller — no free-text chat between agents:

```
Scout ──▶ Analyst ──▶ Strategist ──▶ Critic ──┬─▶ Writer ──▶ PM confirms
                            ▲                  │
                            └── revise (×1) ───┘
                                                └─▶ escalate / insufficient evidence
```

| Agent | File | Responsibility |
| --- | --- | --- |
| Scout | `dxp_radar/agents/scout.py` | Reads raw items from allowlisted sources (read-only) |
| Analyst | `dxp_radar/agents/analyst.py` | Clusters raw items into structured `SignalRecord`s and tags a capability dimension |
| Strategist | `dxp_radar/agents/strategist.py` | Proposes 1 candidate (routine signal) or 2–3 candidates (ambiguous signal) |
| Critic | `dxp_radar/agents/critic.py` | Scores candidates against a weighted rubric and enforces hard evidence gates, on a separate code path so it never just defers to a confident-sounding rationale |
| Writer | `dxp_radar/agents/writer.py` | Drafts the cited brief section, escalation note, or insufficient-evidence flag |

**Coordination** is a hybrid: sequential backbone (Scout → Analyst → Strategist → Critic → Writer), with a small graph loop between Strategist and Critic — one revision round-trip if the top candidate fails a hard gate, mirroring a self-correcting retrieval pattern rather than a pipeline that fails silently.

**Guardrails** (`dxp_radar/guardrails.py`), all deterministic and independent of any model call:
- **Input checks** — scraped text is scanned for prompt-injection markers before the Strategist ever sees it.
- **Source verification / tool access limits** — Scout is read-only; only a human PM confirm step can write to the knowledge base (not implemented as a real store in this prototype; see Limitations).
- **Output constraints (hard gates)** — every claim must resolve to a cited, dated source under 90 days old, and unsupported hedge language ("I guess", "probably") is rejected outright.
- **Escalation rules** — a low or tied Critic score, a policy-sensitive capability dimension (pricing, legal), or an input-check flag routes the cluster to the PM instead of auto-publishing.

**Reasoning mode**: routine, well-sourced signals get one candidate (chain-of-thought, width 1); ambiguous signals (multiple independent sources, a recognized capability dimension) get 2–3 candidate readings scored and ranked — a bounded Tree-of-Thought, not open-ended branching.

**Model backend** (`dxp_radar/llm.py`): the prototype defaults to a documented, deterministic `MockLLM` so it is fully runnable and reviewable with **no API key**. Setting `ANTHROPIC_API_KEY` switches the interface to a real Claude call (the `LLMClient` abstraction is a drop-in swap — see Limitations for what would need to change to route the Strategist/Critic reasoning through it).

## Design evolution

This capstone was built module-by-module across the program; the design changed materially at each checkpoint:

1. **Single-agent research assistant concept** — started as one generalist agent retrieving and summarizing competitor signals.
2. **Tree-of-Thought reasoning (Module 4)** — recognized that only *signal interpretation* benefits from branching search; added a bounded beam-search-style reasoning step (this became the Strategist/Critic split) instead of applying ToT to the whole pipeline.
3. **Multi-agent architecture (Module 5)** — decomposed the single agent into five role-specialized agents once it was clear retrieval, extraction, judgment, and writing are distinct failure modes that need independent verification; settled on five agents after concluding a sixth (e.g., a separate fact-checker) would duplicate the Critic's job.
4. **Safety & guardrails (Module 6)** — added the input-check/hard-gate/escalation-rule guardrail layer and defined evaluation metrics (groundedness, escalation rate, calibration) after mapping out what could silently go wrong: hallucinated claims, injected content, stale evidence, and unreviewed knowledge-base writes.
5. **Final implementation (Module 7, this repo)** — built the design as runnable code; evaluation against a small hand-labeled golden set caught a real bug (a capability-dimension classifier that let a pricing signal slip past the policy-sensitive escalation rule because "headless" matched before "pricing" — fixed in `analyst.py`, see the comment there). That bug is a concrete argument for why the eval harness, not just design intent, belongs in the capstone.

## Implementation overview

- **Language**: Python 3.10+, standard library only for the default run (no required third-party packages).
- **Structure**: plain functions and small classes per agent, orchestrated by `dxp_radar/orchestrator.py`, which owns the sequential/graph state machine and writes a structured trace (sender, action, cluster, elapsed time) for every step — the audit log referenced in the safety plan.
- **Data**: `data/mock_signals.json` and `data/cluster_hints.json` stand in for a live scrape of competitor docs, analyst publications, and registries. Swapping in real fetchers only changes `Scout`; every downstream agent's contract is the `RawItem`/`SignalRecord` schema, not the data source.
- **Model backend**: `dxp_radar/llm.py` provides an `LLMClient` interface with a deterministic `MockLLM` (default) and an `AnthropicLLM` (used automatically if `ANTHROPIC_API_KEY` is set).
- **Testing**: `tests/test_pipeline.py` — 11 unit/integration tests covering the guardrails and the end-to-end pipeline, runnable with no dependencies via `unittest`.
- **Evaluation**: `eval/evaluate.py` — runs the full pipeline against `eval/golden_set.json` and reports correctness, escalation rate, fallback rate, groundedness, revision rate, safety-catch rate, and latency.

## Evaluation and results

Running `python eval/evaluate.py` against the 6-cluster mock dataset (results also saved at `sample_outputs/eval_results_example.json`):

| Metric | Result |
| --- | --- |
| Correctness vs. golden labels | 6/6 (1.0) |
| Escalation rate | 3/6 (0.5) |
| Fallback (insufficient evidence) rate | 1/6 (0.167) |
| Groundedness (every section cited) | 6/6 (1.0) |
| Strategist revision rate | 6/6 (1.0) |
| Safety catch rate (injected content) | 1/1 (1.0) |
| Total pipeline latency | < 1 ms (mock backend; a real model backend would report real per-call latency here) |

The dataset is deliberately built to exercise every guardrail path at least once: a routine parity signal, a policy-sensitive pricing signal, a low-confidence single-source signal, an injected-content signal, a stale registry listing, and a well-corroborated threat signal. The 100% Strategist revision rate is not a bug: the first-pass rationale intentionally hedges ("this probably means…"), the Critic's hard gate rejects unsupported hedge language, and the one-retry loop forces evidence-grounded language before a section can publish — a small, concrete demonstration of the self-correcting loop described in the architecture.

## Safety, reliability, and human oversight

See `dxp_radar/guardrails.py` for the enforcement code. In summary: every knowledge-base write would require PM confirmation regardless of confidence (not yet wired to a real store in this prototype); any Critic score below 7.5, a tie between top candidates, a policy-sensitive dimension, or a flagged input routes to escalation rather than auto-publishing; and every agent handoff is logged to a trace for after-the-fact audit. Guardrails, evaluation, and human review are meant to work as layered defense-in-depth, not any single point of failure: a bad input is structurally caught before reasoning starts, a bad interpretation is caught before writing, and anything left uncertain is caught before it would reach a PM as a stated fact.

## Limitations and next steps

- **Mock data and mock reasoning by default.** The Scout reads a static local file, not live sources, and the Strategist/Critic use documented heuristics, not a real model, unless `ANTHROPIC_API_KEY` is set — and even then, only the `LLMClient.complete` plumbing exists; wiring the Strategist/Critic to actually call it (with real prompts) is the next step, not yet done in this snapshot.
- **No real knowledge-base store.** The "PM confirms before a write" gate is described and tested at the escalation-routing level, but there is no actual persistent store or MCP server behind it yet.
- **Clustering is hint-based, not embedding-based.** `cluster_hints.json` stands in for a real semantic clustering step; swapping in an embedding-based clusterer is a contained change to `analyst.py`.
- **Small golden set.** Six hand-labeled clusters is enough to catch a real classification bug (see Design evolution) but far too small to trust as a general accuracy estimate; a next step is a larger, harder golden set including deliberately adversarial and edge-case signals.
- **No UI.** Output is Markdown to stdout/file; a PM-facing review queue (approve/reject with one click) is the natural next interface layer.

## Setup and usage

```bash
git clone https://github.com/genomathew1/DXP-Radar.git
cd DXP-Radar

# No dependencies required for the default (mock) run.
python3 main.py

# Write the brief and full trace log to files:
python3 main.py --out sample_outputs/brief_example.md --trace sample_outputs/trace_log_example.json

# Run the evaluation harness:
python3 eval/evaluate.py

# Run the test suite:
python3 -m unittest discover tests -v

# Optional: use a real Claude backend instead of the mock heuristics
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python3 main.py
```

## Repository layout

```
DXP-Radar/
├── main.py                  # CLI entry point
├── dxp_radar/
│   ├── schemas.py            # Typed objects passed between agents
│   ├── llm.py                 # Pluggable model backend (mock + Anthropic)
│   ├── guardrails.py           # Input checks, hard gates, escalation rules
│   ├── orchestrator.py          # Sequential + graph controller, trace logging
│   └── agents/
│       ├── scout.py
│       ├── analyst.py
│       ├── strategist.py
│       ├── critic.py
│       └── writer.py
├── data/
│   ├── mock_signals.json     # Mock scraped items (stands in for a live feed)
│   └── cluster_hints.json    # Mock stand-in for embedding-based clustering
├── eval/
│   ├── golden_set.json        # Hand-labeled expected outcomes
│   ├── evaluate.py             # Evaluation harness
│   └── results.json            # Latest run's metrics (generated)
├── sample_outputs/
│   ├── brief_example.md         # Example rendered brief
│   ├── trace_log_example.json    # Example full run trace
│   └── eval_results_example.json  # Example evaluation output
├── tests/
│   └── test_pipeline.py       # Unit + integration tests
└── requirements.txt
```

## Related capstone documents

This repository implements the design from four earlier module submissions: Tree-of-Thought reasoning (Module 4), multi-agent architecture (Module 5), safety & intervention plan (Module 6), and this final report (Module 7). See the final capstone report for the full narrative and evaluation writeup.
