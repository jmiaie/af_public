# AegisFlow Performance Audit

**Version:** 0.1.x (post-GBrain/OMPA bridge)
**Benchmark suite:** `benchmarks/bench_core.py` (control plane, no LLM)
**Companion suite:** `aegisflow/benchmarks/run_all.py` (LLM-integrated, requires Ollama)
**Reproduce:** `python benchmarks/bench_core.py --output benchmarks/latest.json --markdown benchmarks/latest.md --profile`

All numbers in this document are **measured**, not estimated. Re-running the suite
overwrites `benchmarks/latest.json` and `benchmarks/latest.md` so results can be
diffed across commits.

---

## 1. Executive Summary

Three no-API-change optimizations (§5.1, §5.2, §5.3 below) have already
shipped. Headline deltas measured on the same Windows/OneDrive host:

| KPI | Baseline | Current | Delta |
|-----|---------:|--------:|------:|
| **Startup mean** | 6.87 ms | **4.07 ms** | **−40.8 %** |
| **Vault writes / sec** | 2,293 | **5,890** | **+156.9 %** (2.57×) |
| **Vault write p95** | 0.81 ms | **0.22 ms** | **−72.5 %** |
| **KG add / sec** | 821,639 | **1,206,870** | **+46.9 %** |
| **KG query mean (10k triples)** | 0.81 ms | **0.007 ms** | **−99.1 %** (113× faster) |
| **KG query p95** | 1.29 ms | **0.011 ms** | **−99.2 %** |
| **Sandbox I/O cycles / sec** | 308 | **721** | **+134.1 %** (2.34×) |
| **Sandbox I/O p95** | 5.83 ms | **1.99 ms** | **−65.8 %** |
| **Orchestration mean** | 7.11 ms | **1.25 ms** | **−82.4 %** (5.7× faster) |
| **Orchestration p95** | 25.7 ms | **1.59 ms** | **−93.8 %** (16× faster) |
| **Memory per vault** | 13.98 KB | 17.06 KB | +22 % (indices cost memory) |
| **Process RSS** | 40.5 MB | 40.6 MB | flat |

Baseline: `benchmarks/baseline.json`. Current: `benchmarks/latest.json`.

### Current KPIs

| KPI | Measured | Notes |
|-----|---------:|-------|
| Cold startup (vault+sandbox+orchestrator) | **4.07 ms mean / 28.5 ms p95** | Dir cache eliminates repeated makedirs |
| Vault write throughput | **5,890 ops/sec** (0.17 ms mean / 0.22 ms p95) | Open-only is the floor now |
| Knowledge graph add | **1,206,870 ops/sec** | In-memory list append + dict index insert |
| Knowledge graph query (10k triples) | **0.007 ms mean / 0.011 ms p95** | O(1 + k) dict lookup |
| Sandbox write+read cycle | **721 cycles/sec** (1.39 ms mean / 1.99 ms p95) | Windows/OneDrive; Linux expected ~3k/sec |
| Orchestration end-to-end (mock LLM, 3 sub-agents) | **1.25 ms mean / 1.59 ms p95** | Control-plane overhead only |
| Memory per MemoryVault | **17.06 KB** (tracemalloc) | +3 KB vs baseline for `_known_dirs` set |
| Process RSS (end of full suite) | **40.6 MB** | Cold Python + full package imported |

### Headline numbers for portfolio consumers

- **7 ms control-plane overhead** per orchestrated task (end-to-end, 3 sub-agents, excluding LLM latency)
- **~2,300 markdown writes/sec** into the OMPA-compatible vault on commodity Windows hardware with OneDrive sync in the path
- **~820,000 knowledge-graph triples/sec** ingestion (in-memory)
- **~41 MB RSS** for the fully-loaded library — suitable for serverless / edge deployment

---

## 2. Test Environment

| Field | Value |
|-------|-------|
| Python | 3.14.4 |
| Platform | Windows-11 (OneDrive-backed workspace) |
| Machine | AMD64 |
| Pytest | 9.0.3 |
| All tests | 6/6 passing (`tests/test_core.py`) |

The benchmark is cross-platform and requires no network access. Linux / Docker
runs are expected to be **materially faster on sandbox I/O** (~5–10×) because
there is no OneDrive sync intercepting every `open()`. When results land on a
reference Linux host those numbers will be published alongside these.

---

## 3. Detailed Results

Latest run: `benchmarks/latest.json` (full distribution incl. min/max/stdev).

### 3.1 Startup (20 iterations)

Construct `MemoryVault` → `LocalSandbox` → `LeadOrchestrator` → attach mock LLM.

| Stat | ms |
|------|---:|
| mean | 6.87 |
| median | 3.78 |
| p95 | 42.16 |
| p99 | 42.16 |
| min | 2.51 |
| max | 42.16 |
| stdev | 9.27 |

The p95/p99 tail is a single outlier (`42 ms`) attributable to the first
`makedirs` call warming the OneDrive sync path. After warm-up, steady-state
startup is ~3.8 ms.

### 3.2 Vault writes (2,000 iterations)

`MemoryVault.store_verbatim` — append-only markdown writes.

| Stat | ms |
|------|---:|
| mean | 0.44 |
| median | 0.35 |
| p95 | 0.81 |
| p99 | 1.15 |
| max | 2.40 |

→ **2,293 writes/sec** sustained.

### 3.3 Knowledge graph

**add_triple** (10,000 ops): `0.0012 ms` mean, `821,639 ops/sec`.

**query_entity** on a 10k-triple / 200-entity graph: `0.81 ms` mean,
`1.29 ms` p95. The query is a linear scan — see [§5.3](#53-knowledgegraph-query-is-on).

### 3.4 Sandbox I/O (1,000 write+read cycles)

| Stat | ms |
|------|---:|
| mean | 3.25 |
| median | 2.61 |
| p95 | 5.83 |
| p99 | 15.72 |
| max | 126.4 |

→ **308 cycles/sec**. The p99 tail and max are OneDrive-induced; on Linux
this is expected to improve to ~3,000 cycles/sec.

### 3.5 Orchestration (50 tasks, mock LLM, 3 sub-agents each)

| Stat | ms |
|------|---:|
| mean | 7.11 |
| median | 3.49 |
| p95 | 25.68 |
| p99 | 80.77 |

150 sub-agents spawned across 50 tasks. This is the **control plane only** — a
real LLM will dominate end-to-end latency (see `aegisflow/benchmarks/run_all.py`
and `benchmark_report.json` for the LLM-integrated numbers).

### 3.6 Memory footprint

| Component | Value |
|-----------|------:|
| 100 vaults allocated (tracemalloc) | 1.40 MB total |
| Per vault | 13.98 KB |
| 5,000 KG triples + 100 sandboxes + 100 vaults RSS | 40.5 MB |

---

## 4. Profile (cProfile, 100 orchestration tasks)

```
25,200 function calls in 0.615 s

ncalls   cumtime   function
   100     0.615   swarm.py:172(delegate_and_run)
   300     0.454   swarm.py:58(SubAgent.execute)          <-- 74% in sub-agents
   300     0.439   environment.py:47(LocalSandbox.write_file)
   400     0.216   builtin _io.open
   400     0.165   os.makedirs
   400     0.150   io file.__exit__
   100     0.123   ompa_adapter.py:28(store_verbatim)
   400     0.109   nt.mkdir
```

**Interpretation:** `SubAgent.execute` burns 74 % of wall time, and 97 % of *that*
is the `write_file` call that persists sub-agent output to the sandbox
(`open` + `makedirs` + close). That's where the next set of wins lives.

---

## 5. Optimization Opportunities

Ordered by estimated impact. Items flagged **[actionable]** can be done in a
focused PR; items flagged **[architectural]** require an API/contract change.

### 5.1 Cache `makedirs` calls per instance ✅ **SHIPPED**

`LocalSandbox.write_file` and `MemoryVault.store_verbatim` call
`os.makedirs(dir, exist_ok=True)` on every write. Each call stats every path
component. In the profile this costs `0.165 s` of `0.615 s` total (27 %).

Add a per-instance `self._known_dirs: set[str]` and skip `makedirs` if the
parent directory is already in the set. Expected win: **25–40 % on write-heavy
workloads on Windows**, smaller on Linux.

### 5.2 Remove the existence check in `store_verbatim` ✅ **SHIPPED**

```python
# aegisflow/memory/ompa_adapter.py:28
mode = "a" if os.path.exists(filepath) else "w"   # <-- unnecessary syscall
with open(filepath, mode) as f: ...
```

`"a"` mode already creates the file when it doesn't exist. Drop the
`os.path.exists` + conditional and always use `"a"`. Saves one stat per write.

### 5.3 KnowledgeGraph query is O(n) ✅ **SHIPPED**

`query_entity` does `[t for t in self.triples if t["subject"] == entity or t["object"] == entity]`.
At 10k triples this is 0.81 ms; at 1M it will be ~81 ms — unacceptable.

Add dict indices `self._by_subject: dict[str, list[dict]]` and
`self._by_object: dict[str, list[dict]]` populated on `add_triple`. Query
becomes O(1 + k) where k is the number of matching triples. Expected win:
**50–100× at large graph sizes**, no measurable cost at small sizes.

### 5.4 Sandbox I/O is OS-bound **[actionable — measurement only]**

The 3.25 ms/cycle figure is Windows + OneDrive + antivirus. Running the same
benchmark inside the Docker image (or on the Linux reference host) will
reproduce the difference. Publish both numbers so readers can see the delta.

**Action:** add a CI job that runs `bench_core.py` on a Linux runner and commits
`benchmarks/linux-latest.{json,md}` alongside the Windows numbers.

### 5.5 Parallelize sub-agent execution **[architectural, largest real-world win]**

`LeadOrchestrator.delegate_and_run` currently runs sub-agents **sequentially**:

```python
for st in sub_tasks[:max_agents]:
    agent = SubAgent(...)
    res = agent.execute()           # <-- blocks until LLM returns
```

With the mock LLM the overhead is ~2 ms per sub-agent, so sequential is fine.
With a real LLM at 500–2000 ms per call, this is a **3–5× end-to-end speedup**
opportunity. Port to `asyncio.gather` or `concurrent.futures.ThreadPoolExecutor`
— sub-agents are already independent by design.

### 5.6 Make sub-agent sandbox persistence opt-in **[architectural]**

Every `SubAgent.execute` writes the LLM result to sandbox **and** the lead
orchestrator writes the synthesis to vault. For throughput-focused callers the
sandbox write is dead weight. Add `SubAgent(..., persist_to_sandbox=True)` with
a default that can be flipped at the orchestrator level. Expected win: ~2 ms
per sub-agent in the current profile, more on slow filesystems.

### 5.7 Observability: record LLM fallback rate **[actionable]**

`_decompose_with_llm` silently falls back to rule-based decomposition when the
LLM call fails (401, timeout, etc.). Today this is invisible. Emit a metric
(counter) and surface it on the session summary so operators can tell when
they're running in degraded mode.

### 5.8 Batch vault writes **[architectural]**

Each sub-agent result and session summary triggers its own `open`/`close`.
For bulk workflows (hundreds of sessions/minute) a `vault.flush()` batch mode
would amortize the per-call syscall cost. Lower priority — only matters at
throughput regimes we don't currently target.

---

## 6. Recommended Roadmap

### v0.1.z (patch — zero API change)
1. ✅ §5.1 `_known_dirs` cache in `LocalSandbox` and `MemoryVault` — shipped
2. ✅ §5.2 Drop `os.path.exists` from `store_verbatim` — shipped
3. ✅ §5.3 Dict indices for `KnowledgeGraph` — shipped
4. §5.7 Fallback-rate counter on `LeadOrchestrator` — open

Combined wins from 1–3: orchestration mean **−82.4 %**, KG query **−99.1 %**,
vault throughput **+156.9 %**, sandbox throughput **+134.1 %**. See §1.

### v0.2 (minor — API additions)
5. §5.5 `asyncio.gather` sub-agent execution (keep sync path as fallback)
6. §5.6 Opt-in sandbox persistence

### v0.3 (minor — infra)
7. §5.4 Linux CI benchmark job with committed reference numbers
8. §5.8 Vault batch mode

---

## 7. What this audit deliberately does **not** claim

- It does **not** compare AegisFlow to other frameworks. All numbers are
  AegisFlow vs. itself.
- It does **not** include LLM inference timing — that belongs in
  `aegisflow/benchmarks/run_all.py`, which requires Ollama on localhost.
- It does **not** project scaling behavior beyond what was measured. Graph
  query at 10k triples was measured; 1M is extrapolation and called out as
  such.
- The Windows numbers are not cherry-picked "best case" — they include
  OneDrive sync in the critical path, which is a **worst-case** filesystem
  scenario for this workload. Treat them as a floor.

---

*Run the suite yourself:*
```bash
python benchmarks/bench_core.py --output benchmarks/latest.json --markdown benchmarks/latest.md --profile
```
