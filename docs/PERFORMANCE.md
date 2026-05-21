# Performance Engineering — AegisFlow

This is the policy and process around the numbers in [`../BENCHMARKS.md`](../BENCHMARKS.md).

## What we measure

| Layer            | What                                  | Why                                                                    |
|------------------|---------------------------------------|------------------------------------------------------------------------|
| Cold path        | Startup latency (vault+sandbox+orch)  | Cold-start matters for serverless and CLI invocations.                 |
| Memory layer     | Vault write throughput, KG add/query  | Vault is on the hot path of every sub-agent return.                    |
| Sandbox          | Write+read cycle ops/sec              | Sub-agent results are persisted via the sandbox — bottleneck candidate.|
| Orchestration    | End-to-end with mock LLM              | Isolates control-plane cost from LLM latency.                          |
| LLM-integrated   | Decompose / sub-agent / synthesise    | Real-world wall-clock at production-ish settings.                      |
| Memory footprint | Tracemalloc per vault, process RSS    | Important for embedding inside a long-running service.                 |

## Why we measure it

- **Comparability over time.** Every commit can be measured against `benchmarks/baseline.json`. Without this, "we made it faster" claims are unfalsifiable.
- **No surprise regressions.** A p95 regression of 20 %+ should fail CI, not show up in production.
- **Honest claims.** Every number in marketing / README must trace back to a JSON file in `benchmarks/`.
- **Capacity planning.** Operators can size hardware from `BENCHMARKS.md` §2 + §4 without trial and error.

## How we measure

- One harness, two profiles: `benchmarks/bench_core.py` (control plane, deterministic) and `aegisflow/benchmarks/run_all.py` (LLM-integrated, Ollama-backed).
- Always emit JSON and Markdown side-by-side so PRs can diff both human-readable and machine-readable forms.
- Always record `_meta` (Python version, OS, machine, CPU/RAM) inside the JSON so downstream comparisons can sanity-check the environment.
- p50/p95/p99 over enough samples that p99 is meaningful (≥ 100 for fast ops, ≥ 20 for slow).

## What we explicitly do **not** claim

(Mirrored from `docs/PERFORMANCE_AUDIT.md` §7 — kept in sync.)

- We do not compare AegisFlow to other frameworks today. All numbers are AegisFlow vs itself.
- We do not include LLM inference timing in `bench_core.py`. That belongs in `run_all.py`.
- We do not extrapolate beyond what was measured. 10k triples was measured; 1M is extrapolation and must be labelled as such.
- Windows + OneDrive numbers are **not** cherry-picked best-case — treat them as a floor.

## CI gate (planned)

`benchmarks/regress.py` will:
1. Run `bench_core.py` and produce `benchmarks/pr.json`.
2. Compare every `p95_ms` against `benchmarks/baseline.json`.
3. Fail the build if any metric regresses > 20 % (configurable via `--tolerance`).
4. Post a Markdown diff to the PR.

A second job runs the same harness on a Linux runner and commits `benchmarks/linux-latest.{json,md}` so the Windows/Linux delta is visible at every commit (audit §5.4).

## When to add a new metric

Add a metric to the harness when:
- The component is on the hot path (the profile in audit §4 shows it taking > 5 % of wall time).
- A bug or regression in it would not be caught by an existing metric.
- It has a clear, measurable definition with a stable name.

Avoid:
- Metrics that depend on external services (those go in `run_all.py`, not `bench_core.py`).
- Composite scores that hide which sub-component changed.
