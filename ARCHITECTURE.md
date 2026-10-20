# Architecture — AegisFlow

This is the institutional-grade overview of how AegisFlow is wired. It supersedes
the short `ARCHITECTURE.md` at the repo root by adding concrete module references,
entry points, and data-flow traces.

## 1. Layered view

```
┌─────────────────────────────────────────────────────────────┐
│  Application / caller                                       │
│  (script, FastAPI handler, CLI `aegisflow ...`)             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Orchestration  ── aegisflow/orchestration/swarm.py         │
│    LeadOrchestrator                                         │
│       _decompose_with_llm   (LLM-driven, fallback to rule)  │
│       delegate_and_run      (sync, sequential)              │
│       delegate_and_run_async(asyncio.gather, 3–5× speedup)  │
│       run_research          (quick / standard / deep)       │
│    SubAgent                                                 │
│       execute / execute_async                               │
└─────────────────────────────────────────────────────────────┘
        │                 │                       │
        ▼                 ▼                       ▼
┌──────────────┐  ┌─────────────────┐   ┌─────────────────────┐
│ Memory       │  │ Executors       │   │ LLM                 │
│ memory/      │  │ sandbox/        │   │ llm/                │
│  ompa_*.py   │  │  Local (not     │   │  AgenticLLM         │
│  semantic.py │  │  isolated),     │   │  OpenAICompatible   │
│  KG (in mem) │  │  Namespace,     │   │  OpenClawSession    │
│              │  │  Docker         │   │                     │
└──────────────┘  └─────────────────┘   └─────────────────────┘
        ▲                                          ▲
        │                                          │
   ┌────┴──────────────────────┐         ┌─────────┴──────────┐
   │ Brain  aegisflow/brain/   │         │ Analytics          │
   │  SignalDetector           │         │  analytics/        │
   │  BrainFirstLookup         │         │   mtb (mean time   │
   │  Doctor (health check)    │         │      between …)    │
   └───────────────────────────┘         │   session, tool_   │
                                         │   categories       │
                                         └────────────────────┘
```

## 2. Component reference

| Package                       | Purpose                                              | Key types                                            |
|-------------------------------|------------------------------------------------------|------------------------------------------------------|
| `aegisflow.orchestration`     | Lead-orchestrator + sub-agent lifecycle              | `LeadOrchestrator`, `SubAgent`                       |
| `aegisflow.memory`            | OMPA-compatible vault (`retrieve` is a placeholder), in-memory triple list (not persisted), semantic search shim | `MemoryVault` (via `ompa_adapter`), `KnowledgeGraph`, `SemanticMemory` |
| `aegisflow.sandbox`           | Command executors: local (not isolated), namespace, Docker | `LocalSandbox`, `NamespaceSandbox`, `DockerSandbox`, `SandboxResult` |
| `aegisflow.llm`               | Provider abstraction                                 | `AgenticLLM`, `OpenAICompatibleLLM`, `OpenClawSession`, `AgenticResponse`, `SubAgentResult` |
| `aegisflow.brain`             | Ambient signal capture (GBrain port)                 | `SignalDetector`, `SignalCapture`, `SignalSummary`, `BrainFirstLookup`, `Doctor` |
| `aegisflow.analytics`         | Session telemetry, MTB analytics, tool categorisation | `session`, `mtb`, `tool_categories`                  |
| `aegisflow.benchmarks`        | LLM-integrated end-to-end harness                    | `run_all.main`                                       |

## 3. Entry points

| Where                                         | What it does                                          |
|-----------------------------------------------|-------------------------------------------------------|
| `aegisflow.__main__:main` (PyPI script `aegisflow`) | CLI entry — TODO at 0.3.0; reserved.            |
| `LeadOrchestrator.delegate_and_run`           | The canonical Python API.                             |
| `LeadOrchestrator.delegate_and_run_async`     | Async path — same contract, `asyncio.gather` internally. |
| `benchmarks/bench_core.py`                    | Control-plane microbenchmark.                         |
| `aegisflow/benchmarks/run_all.py`             | LLM-integrated end-to-end benchmark (needs Ollama).   |

## 4. Data flow — `delegate_and_run("Analyse X")`

1. `LeadOrchestrator` calls `_decompose_with_llm(task)`. The system prompt asks the LLM for 3–5 sub-tasks as a numbered list. On any failure (HTTP 4xx / 5xx, timeout, malformed parse), a rule-based fallback emits *Research → Analyse → Synthesise* and increments `self.fallback_count`.
2. For each sub-task (capped at `max_agents`), a `SubAgent` is constructed with `(task_id=session_id, prompt=sub_task, sandbox=sandbox, llm=self.llm)`.
3. `SubAgent.execute` runs the LLM (`AgenticLLM.chat`) on the sub-task and writes the response to `sandbox/workspace/<agent_id>_output.txt`.
4. `LeadOrchestrator` aggregates `[result["content"] for r in results]` into a synthesis prompt, calls the LLM once more, and stores `## Task / ## Synthesis / ## Sub-agent Results` to `vault.work/session_<id>.md` via `MemoryVault.store_verbatim`.
5. The return value is a dict containing `session_id`, `status`, `task`, `sub_tasks`, `sub_agents`, `synthesis`, `details`. The async path is identical except step 3 runs concurrently via `asyncio.gather`.

## 5. Cross-cutting concerns

- **Logging:** standard `logging.getLogger("aegisflow…")`. Level controlled by `AEGISFLOW_LOG_LEVEL`.
- **Errors:** Sub-agent errors are captured into the result dict (`status: "error"`, `error: <str>`) rather than raised; the lead orchestrator still produces a synthesis.
- **Determinism:** No internal RNG in the control plane; LLM determinism depends on backend (set `temperature=0` for synthesis-time reproducibility).
- **Concurrency model:** Sub-agents are independent by design. Sequential execution is the default; `delegate_and_run_async` is the recommended path for real LLMs (latency-bound).
- **Memory model:** `MemoryVault` is markdown-on-disk via the `ompa` package; `KnowledgeGraph` is an in-memory list only: it starts empty in every process and is not rebuilt from the vault (no persistence layer yet; `db_path` is unused).

## 6. Execution backends: what `LocalSandbox` is and is not

`LocalSandbox` is a **local executor, not isolated**. It enforces a *path scope*: every `write_file` / `read_file` path is resolved with `os.path.realpath` and must stay under `workspace_path` (`os.path.commonpath`), which rejects `..`, absolute paths, sibling-prefix directories and symlink escapes. `execute` runs an argv list (strings are split with `shlex.split`; no shell), in its own process session, and on timeout kills only that process group. It does **not**:
- isolate the command from the host (same user, same filesystem, same network)
- enforce a syscall filter (no seccomp / no AppArmor)
- restrict network access

`NamespaceSandbox` adds Linux user/PID/mount/network namespaces via `unshare` and raises `SandboxUnavailableError` if they cannot be created; it never silently falls back to host execution. `DockerSandbox` runs each command in a throwaway container.

For untrusted prompts, use one of the isolating backends and wrap AegisFlow itself in a container or a dedicated VM. See `SECURITY.md` for the threat model.
