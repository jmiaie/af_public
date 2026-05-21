# BENCHMARKS — AegisFlow

This document is the **single source of truth** for performance claims about AegisFlow.
Everything below is reproducible from `benchmarks/bench_core.py` plus
`aegisflow/benchmarks/run_all.py` (LLM-integrated). Project type: **software library / SDK**,
so the required dimensions are microbenchmarks vs. nearest competitor, reliability, API
stability, build matrix, and footprint.

---

## 1. Methodology

- **Harness:** `benchmarks/bench_core.py` (no LLM, deterministic) + `aegisflow/benchmarks/run_all.py` (LLM-integrated, requires Ollama on localhost).
- **Iterations:** Startup 20, vault writes 2,000, KG add 10,000, KG query 500, sandbox cycles 1,000, orchestration 50 tasks × 3 sub-agents = 150 sub-agents.
- **Statistics:** mean, median, p95, p99, min, max, stdev — every measurement carries its full distribution in `benchmarks/latest.json`.
- **Hardware (reference):** Windows 11, AMD64, 16 logical / 8 physical cores, 31.7 GB RAM. The Windows + OneDrive path is the **worst-case floor**; Linux numbers are expected ~5–10× better on sandbox I/O.
- **Comparison policy:** AegisFlow vs. AegisFlow only, baseline vs. current — there is no shipping comparison vs. `langgraph` / `crewai` / `autogen` yet (see §6 — Open work).
- **Reproduce:** `python benchmarks/bench_core.py --output benchmarks/latest.json --markdown benchmarks/latest.md --profile`

---

## 2. Microbenchmarks (current, v0.3.0)

| Metric                                          | mean    | p95     | p99     | ops/sec   |
|-------------------------------------------------|--------:|--------:|--------:|----------:|
| Startup (`MemoryVault + LocalSandbox + Lead`)   | 2.77 ms | 24.4 ms | 24.4 ms | —         |
| Vault `store_verbatim` (markdown append)        | 0.186 ms| 0.276 ms| 0.374 ms| **5,376** |
| KG `add_triple`                                 | 0.0008 ms | 0.0016 ms | 0.0026 ms | **1,198,265** |
| KG `query_entity` (10k triples, 200 entities)   | 0.011 ms | 0.021 ms | 0.032 ms | — |
| Sandbox write+read cycle (Windows / OneDrive)   | 1.47 ms | 2.47 ms | 3.00 ms | **678**   |
| Orchestration end-to-end (mock LLM, 3 agents)   | 2.07 ms | 3.84 ms | 5.21 ms | — |

Memory: **17.06 KB per `MemoryVault`** (tracemalloc, post-index), **39.7 MB process RSS** for the full suite after 100 vaults + 100 sandboxes + 5,000 KG triples.

---

## 3. Baseline → current deltas

From `docs/PERFORMANCE_AUDIT.md` §1 (verified against `benchmarks/baseline.json` and `benchmarks/latest.json`):

| KPI                          | Baseline | Current | Delta              |
|------------------------------|---------:|--------:|--------------------|
| Startup mean                 | 6.87 ms  | 4.07 ms | **−40.8 %**        |
| Vault writes / sec           | 2,293    | 5,890   | **+156.9 %** (2.57×) |
| Vault write p95              | 0.81 ms  | 0.22 ms | **−72.5 %**        |
| KG add / sec                 | 821,639  | 1,206,870 | **+46.9 %**      |
| KG query mean (10k triples)  | 0.81 ms  | 0.007 ms | **−99.1 %** (113× faster) |
| KG query p95                 | 1.29 ms  | 0.011 ms | **−99.2 %**       |
| Sandbox cycles / sec         | 308      | 721     | **+134.1 %** (2.34×) |
| Orchestration mean           | 7.11 ms  | 1.25 ms | **−82.4 %** (5.7× faster) |
| Orchestration p95            | 25.7 ms  | 1.59 ms | **−93.8 %** (16× faster) |

Wins came from three no-API-change optimizations (see audit §5.1 / §5.2 / §5.3):
1. Per-instance `_known_dirs` cache eliminating repeated `os.makedirs`.
2. Dropping the redundant `os.path.exists` stat in `store_verbatim`.
3. Dict indices on `KnowledgeGraph` turning `query_entity` from O(n) into O(1 + k).

---

## 4. LLM-integrated end-to-end (from `benchmark_report.json`)

Run on Python 3.12 / Ollama / 4 vCPU 8 GB:

| Stage                                 | Time    |
|---------------------------------------|--------:|
| `_decompose_with_llm` (1 LLM call)    | 5.37 s  |
| 3 sub-agents (sequential, before async) | 29.81 s |
| `synthesis` LLM call                  | 3.80 s  |
| **Total end-to-end**                  | **38.98 s** |
| Single LLM completion (10 tokens)     | 0.67 s  |

The **async** path (`delegate_and_run_async`, shipped in 0.3 per audit §5.5) is the
expected 3–5× wall-clock speedup against this baseline on real LLM workloads. The
LLM benchmark is **not** locked to this hardware — see §6.

---

## 5. Reliability & build matrix

| Dimension                  | Today                                                                |
|----------------------------|----------------------------------------------------------------------|
| Unit tests                 | 7 modules (`brain`, `analytics`, `llm`, `async`, `core`, `core_v2`, `sandbox`) |
| Coverage                   | Not yet measured in CI; target ≥ 80 % at v0.4.                       |
| Mutation testing           | Not configured.                                                      |
| Fuzz hours                 | 0 (planned: Hypothesis on `signal_detector._extract_*`).             |
| OS × runtime               | Linux/macOS/Windows × Python 3.10–3.14 (currently only Windows 3.14 exercised). |
| Binary / install size      | Wheel `sandfish-0.1.0-py3-none-any.whl` ≈ pure-Python, transitive deps dominated by `fastapi + uvicorn + pydantic`. |
| Cold-start time            | 2.77 ms mean (see §2).                                               |

---

## 6. Open work — what we should be measuring but aren't

1. **Linux reference numbers.** Audit §5.4 calls this out — currently every benchmark in this doc is Windows + OneDrive. Linux is expected materially faster on sandbox I/O.
2. **Vs. competitors.** A microbenchmark suite comparing `LeadOrchestrator` to `langgraph` + `crewai` + `autogen` on identical workloads (mock LLM, fixed seed) would let consumers price the AegisFlow choice.
3. **Memory under load.** Tracemalloc snapshots only at construction; we should record RSS at 1 / 10 / 100 / 1000 concurrent sessions.
4. **Capacity model.** "How many sessions/sec can one process sustain at p95 < 500 ms" — currently unknown.
5. **Regression CI.** `benchmarks/regress.py` (planned, item 5 in `upgrade_plan.md`) should fail PRs that regress any p95 > 20 %.

---

## 7. Reproducibility checklist

- [x] Random seed: deterministic — no RNG in the control-plane benchmark.
- [x] Hardware / OS / Python recorded in `_meta` of every JSON output.
- [x] Markdown report regenerated alongside JSON every run.
- [x] Baseline preserved (`benchmarks/baseline.json`) for delta calculation.
- [ ] Pinned dependency lockfile (`uv.lock`) — planned, item 8 in upgrade plan.
- [ ] Docker image with frozen environment — Dockerfile exists, no published tag yet.
