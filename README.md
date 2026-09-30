# AegisFlow

> **Portfolio status (2026-09-30):** public **AegisFlow mirror** (`af_public`). Canonical private work: [`jmiaie/af`](https://github.com/jmiaie/af). SandFish ([`sandfish`](https://github.com/jmiaie/sandfish)) is the separate v1 swarm **demo**. See [`STATUS.md`](STATUS.md) and [`docs/POSITIONING.md`](docs/POSITIONING.md).


> A security-first, framework-agnostic Python harness for multi-agent workflows with persistent memory, sandboxed execution, and parallel sub-agent delegation.

[![CI](https://img.shields.io/badge/CI-pending-lightgrey)](.github/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-pending-lightgrey)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/pypi-v0.3.0-blue)](https://pypi.org/project/aegisflow/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](pyproject.toml)

## What it is

AegisFlow is a Python library that wires three concerns into one harness: **persistent memory** (an OMPA-compatible markdown vault plus a temporal knowledge graph), **sandboxed execution** (per-thread filesystem scopes for tool runs), and **swarm orchestration** (a lead agent that decomposes a task and runs sub-agents in parallel against any OpenAI-compatible endpoint or an OpenClaw session). It is designed for engineers who want LangGraph-style multi-agent capability without giving up the ability to swap any layer.

It competes with / overlaps: `langgraph`, `crewai`, `autogen`, `deer-flow`. Its differentiator is the explicit separation of memory / sandbox / orchestration as pluggable interfaces, plus a published microbenchmark suite (see [Performance](#performance)).

## Status

| | |
|---|---|
| **Maturity**       | Alpha — public API surface is stabilising. Breaking changes possible until `1.0`. |
| **Latest version** | `0.3.0` (see `pyproject.toml`) |
| **Last release**   | 2026-04-16 (`benchmarks/latest.md`) |
| **Support policy** | Last two minor versions get patch backports; older versions are best-effort. |

## Quickstart

```bash
git clone https://github.com/jmiaie/af_public.git aegisflow
cd aegisflow
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                        # 7 test modules
python benchmarks/bench_core.py --markdown benchmarks/latest.md
```

Minimal end-to-end run (mock LLM, no API key required):

```python
from aegisflow.memory import MemoryVault
from aegisflow.sandbox import LocalSandbox
from aegisflow.orchestration.swarm import LeadOrchestrator

memory  = MemoryVault(path="./vault")
sandbox = LocalSandbox(workspace_path="./sandbox_workspace")
swarm   = LeadOrchestrator(memory=memory, sandbox=sandbox, llm_backend="openai")

result = swarm.delegate_and_run(
    "Summarise the security incidents in ./vault/work",
    max_agents=3,
)
print(result["synthesis"])
```

Real LLM run: set `OPENAI_API_KEY` (or point `openai_config` at any OpenAI-compatible base URL — vLLM, Ollama, OpenRouter all work).

## Performance

Headline numbers from `benchmarks/bench_core.py` on Python 3.14 / Windows 11 / 16 vCPU. **All numbers are measured, not estimated** — full distribution in `benchmarks/latest.json`.

| KPI                                   | Measured                       |
|---------------------------------------|-------------------------------:|
| Startup (vault + sandbox + orch)      | **2.77 ms mean / 24.4 ms p95** |
| Vault writes                          | **5,376 ops/sec** (p95 0.276 ms) |
| Knowledge graph `add_triple`          | **1,198,265 ops/sec**          |
| Knowledge graph `query_entity` (10k)  | **0.011 ms mean / 0.021 ms p95** |
| Sandbox write+read cycle (Windows)    | **678 cycles/sec** (p95 2.47 ms) |
| Orchestration end-to-end (mock LLM)   | **2.07 ms mean / 3.84 ms p95** |
| Process RSS (cold + full suite)       | **39.7 MB**                    |

Three no-API-change wins from the audit shipped in 0.3: orchestration mean **−82.4 %**, KG query **−99.1 %** (113× faster), vault throughput **+156.9 %**. See [`docs/PERFORMANCE_AUDIT.md`](docs/PERFORMANCE_AUDIT.md) and [`BENCHMARKS.md`](BENCHMARKS.md) for methodology, regression policy, and the full optimization log.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│              LeadOrchestrator (orchestration/swarm.py)     │
│    decompose (LLM-driven) → spawn N SubAgents → synthesise │
└──────────┬──────────────┬──────────────┬───────────────────┘
           │              │              │
   ┌───────▼─────┐ ┌──────▼────┐ ┌───────▼─────────┐
   │ MemoryVault │ │ LocalSand │ │ AgenticLLM      │
   │ (OMPA)      │ │ box       │ │ OpenAI-compat / │
   │  + KG       │ │ + per-    │ │ OpenClaw        │
   │  + semantic │ │   thread  │ │ + pricing       │
   │             │ │   scopes  │ │                 │
   └─────────────┘ └───────────┘ └─────────────────┘
        ▲                                ▲
        │   SignalDetector (brain/)      │
        └────────────────────────────────┘
        ambient capture: ideas, entities, facts
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for component-by-component detail and the data-flow walkthrough.

## Usage

### Quick research

```python
swarm.run_research(topic="post-quantum signature schemes", depth="standard")
# depth ∈ {"quick" (1 agent), "standard" (3), "deep" (5)}
```

### Async swarm (3–5× wall-clock speedup with real LLM)

```python
import asyncio
result = asyncio.run(swarm.delegate_and_run_async("…", max_agents=5))
```

### Signal capture (ambient)

```python
from aegisflow.brain.signal_detector import SignalDetector
detector = SignalDetector(vault=memory)
summary = detector.detect("I think the Phoenix deal at MiCap looks mispriced")
print(detector.log_summary(summary))   # "Signals: 1 ideas, 1 entities, 0 facts (…)"
```

## Configuration

| Variable                    | Default                  | Description                                                  |
|-----------------------------|--------------------------|--------------------------------------------------------------|
| `OPENAI_API_KEY`            | —                        | Used by the `openai` backend.                                |
| `OPENAI_BASE_URL`           | `https://api.openai.com` | Point at vLLM / Ollama / OpenRouter for self-hosted models.  |
| `AEGISFLOW_VAULT_PATH`      | `./vault`                | Default `MemoryVault` root.                                  |
| `AEGISFLOW_SANDBOX_PATH`    | `./sandbox_workspace`    | Default `LocalSandbox` root.                                 |
| `AEGISFLOW_LOG_LEVEL`       | `INFO`                   | Standard logging level.                                      |
| `OPENCLAW_SESSION_BIN`      | `claw`                   | Path to the OpenClaw CLI if using the `openclaw` backend.    |

See `.env.example` for the full list.

## Compatibility

| Component | Versions                |
|-----------|-------------------------|
| Python    | 3.10, 3.11, 3.12, 3.13, 3.14 (tested on 3.14) |
| OS        | Linux, macOS, Windows (Windows + OneDrive is the worst-case I/O floor — see audit §2) |
| LLM       | Any OpenAI-compatible endpoint; OpenClaw CLI session |
| OMPA      | `ompa >= 0.3.0`         |

## Security

This package executes LLM-driven commands inside `LocalSandbox`, which scopes file access but is **not** an OS-level isolation boundary. Treat `LocalSandbox` like a `chroot` hint, not a security primitive — run the harness inside a container or a dedicated VM if you accept untrusted prompts.

Disclosure policy and the threat model live in [`SECURITY.md`](SECURITY.md). Please report vulnerabilities privately.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). The short version: open an issue first for non-trivial changes, run `pytest && ruff check . && mypy aegisflow` before opening a PR, and add a `CHANGELOG.md` entry under `[Unreleased]`.

## License

MIT — see [`LICENSE`](LICENSE). SPDX-License-Identifier: `MIT`.

## Acknowledgments

AegisFlow stands on the design ideas of three projects:
- **OMPA** — persistent markdown vault + temporal knowledge graph
- **SandFish** — security-first swarm orchestration
- **DeerFlow** — sub-agent sandbox execution model
- **GBrain** — signal-detector ambient capture (ported in `aegisflow/brain/signal_detector.py`)
