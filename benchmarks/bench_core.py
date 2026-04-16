"""
AegisFlow Control-Plane Benchmark Suite
=======================================

Measures the deterministic (no-LLM) hot paths of the AegisFlow public API:
MemoryVault, KnowledgeGraph, LocalSandbox, and LeadOrchestrator with a
mocked LLM. Cross-platform, no network required, no Ollama required.

Run:
    python benchmarks/bench_core.py
    python benchmarks/bench_core.py --output report.json --profile

For LLM-integrated benchmarks (requires Ollama on localhost:11434),
see aegisflow/benchmarks/run_all.py instead.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import logging
import pstats
import statistics
import sys
import tempfile
import time
import tracemalloc
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Silence the orchestrator's "LLM call failed" warnings — our mock never fails,
# but any real integration would spam stderr otherwise.
logging.getLogger("aegisflow").setLevel(logging.ERROR)

from aegisflow.memory import KnowledgeGraph, MemoryVault  # noqa: E402
from aegisflow.orchestration import LeadOrchestrator  # noqa: E402
from aegisflow.sandbox import LocalSandbox  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_ms(fn: Callable[[], Any]) -> float:
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000.0


def _stats(samples_ms: List[float]) -> Dict[str, float]:
    samples_sorted = sorted(samples_ms)
    n = len(samples_sorted)
    return {
        "samples": n,
        "mean_ms": round(statistics.fmean(samples_sorted), 4),
        "median_ms": round(statistics.median(samples_sorted), 4),
        "p95_ms": round(samples_sorted[min(n - 1, int(n * 0.95))], 4),
        "p99_ms": round(samples_sorted[min(n - 1, int(n * 0.99))], 4),
        "min_ms": round(min(samples_sorted), 4),
        "max_ms": round(max(samples_sorted), 4),
        "stdev_ms": round(statistics.pstdev(samples_sorted) if n > 1 else 0.0, 4),
    }


class FakeLLM:
    """Deterministic stand-in for AgenticLLM (no network, constant latency)."""

    backend = "fake"

    def chat(self, messages, **kwargs):
        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        if "Decompose" in user:
            content = "1. Analyze\n2. Execute\n3. Verify"
        elif "Synthesize" in user:
            content = "Synthesis complete."
        else:
            content = "ok"
        return SimpleNamespace(content=content, tokens_used=0)

    def complete(self, prompt, **kwargs):
        return self.chat([{"role": "user", "content": prompt}])


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

class BenchmarkSuite:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.results: Dict[str, Any] = {}

    # ---- system info --------------------------------------------------------

    def bench_system(self) -> Dict[str, Any]:
        import platform
        info = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        }
        try:
            import os as _os

            import psutil  # type: ignore[import-not-found]
            vm = psutil.virtual_memory()
            info.update({
                "cpu_logical": psutil.cpu_count(logical=True),
                "cpu_physical": psutil.cpu_count(logical=False),
                "ram_total_gb": round(vm.total / 1024**3, 1),
                "ram_avail_gb": round(vm.available / 1024**3, 1),
            })
        except ImportError:
            pass
        return info

    # ---- startup ------------------------------------------------------------

    def bench_startup(self, iters: int = 20) -> Dict[str, float]:
        """Time to construct MemoryVault + LocalSandbox + LeadOrchestrator."""
        print(f"[1/6] Startup x{iters}")
        samples = []
        for i in range(iters):
            vault = self.workspace / f"startup-v-{i}"
            sandbox = self.workspace / f"startup-s-{i}"

            def build():
                m = MemoryVault(path=str(vault))
                s = LocalSandbox(workspace_path=str(sandbox))
                o = LeadOrchestrator(memory=m, sandbox=s)
                o.llm = FakeLLM()

            samples.append(_time_ms(build))
        return _stats(samples)

    # ---- vault --------------------------------------------------------------

    def bench_vault_writes(self, n: int = 2000) -> Dict[str, Any]:
        print(f"[2/6] Vault writes x{n}")
        vault = MemoryVault(path=str(self.workspace / "v-writes"))
        payload = "x" * 256
        samples = []
        for i in range(n):
            samples.append(_time_ms(lambda i=i: vault.store_verbatim(
                content=payload, category="work", filename=f"n{i % 20}.md")))
        total_s = sum(samples) / 1000.0
        return {
            "operations": n,
            "total_seconds": round(total_s, 3),
            "ops_per_sec": round(n / total_s if total_s else 0, 0),
            **_stats(samples),
        }

    # ---- knowledge graph ----------------------------------------------------

    def bench_knowledge_graph(self, n: int = 10000) -> Dict[str, Any]:
        print(f"[3/6] Knowledge graph x{n} adds + 500 queries")
        kg = KnowledgeGraph()
        add_samples = []
        for i in range(n):
            add_samples.append(_time_ms(lambda i=i: kg.add_triple(
                f"E{i % 200}", "rel", f"E{(i + 1) % 200}")))
        query_samples = [
            _time_ms(lambda i=i: kg.query_entity(f"E{i % 200}")) for i in range(500)
        ]
        add_total = sum(add_samples) / 1000.0
        return {
            "add": {
                "operations": n,
                "total_seconds": round(add_total, 3),
                "ops_per_sec": round(n / add_total if add_total else 0, 0),
                **_stats(add_samples),
            },
            "query": {
                "operations": len(query_samples),
                "entities_in_graph": 200,
                "triples_in_graph": n,
                **_stats(query_samples),
            },
        }

    # ---- sandbox ------------------------------------------------------------

    def bench_sandbox_io(self, n: int = 1000) -> Dict[str, Any]:
        print(f"[4/6] Sandbox I/O x{n} write+read cycles")
        sb = LocalSandbox(workspace_path=str(self.workspace / "sb-io"))
        payload = "y" * 256
        samples = []
        for i in range(n):
            rel = f"workspace/b{i}.txt"
            samples.append(_time_ms(lambda rel=rel: (
                sb.write_file(rel, payload),
                sb.read_file(rel),
            )))
        total_s = sum(samples) / 1000.0
        return {
            "cycles": n,
            "total_seconds": round(total_s, 3),
            "cycles_per_sec": round(n / total_s if total_s else 0, 0),
            **_stats(samples),
        }

    # ---- orchestration ------------------------------------------------------

    def bench_orchestration(self, n: int = 50) -> Dict[str, Any]:
        print(f"[5/6] Orchestration (mock LLM) x{n}")
        memory = MemoryVault(path=str(self.workspace / "orch-v"))
        sandbox = LocalSandbox(workspace_path=str(self.workspace / "orch-s"))
        lead = LeadOrchestrator(memory=memory, sandbox=sandbox)
        lead.llm = FakeLLM()

        samples = [
            _time_ms(lambda i=i: lead.delegate_and_run(f"Benchmark task {i}"))
            for i in range(n)
        ]
        return {
            "tasks": n,
            "total_sub_agents": len(lead.sub_agents),
            "avg_sub_agents_per_task": round(len(lead.sub_agents) / n, 2),
            **_stats(samples),
        }

    # ---- memory footprint ---------------------------------------------------

    def bench_memory_footprint(self) -> Dict[str, Any]:
        print("[6/6] Memory footprint (tracemalloc + optional psutil RSS)")
        tracemalloc.start()

        baseline_snap = tracemalloc.take_snapshot()

        vaults = [MemoryVault(path=str(self.workspace / f"mem-v-{i}")) for i in range(100)]
        kg = KnowledgeGraph()
        for i in range(5000):
            kg.add_triple(f"E{i % 200}", "rel", f"E{(i + 1) % 200}")
        sandboxes = [LocalSandbox(workspace_path=str(self.workspace / f"mem-s-{i}")) for i in range(100)]

        after_snap = tracemalloc.take_snapshot()
        diff = after_snap.compare_to(baseline_snap, "lineno")
        total_bytes = sum(stat.size_diff for stat in diff)

        result: Dict[str, Any] = {
            "vaults_constructed": 100,
            "kg_triples": 5000,
            "sandboxes_constructed": 100,
            "tracemalloc_total_mb": round(total_bytes / 1024 / 1024, 3),
            "tracemalloc_per_vault_kb": round(total_bytes / 100 / 1024, 2),
        }

        try:
            import os as _os

            import psutil  # type: ignore[import-not-found]
            proc = psutil.Process(_os.getpid())
            result["process_rss_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
        except ImportError:
            result["process_rss_mb"] = None

        tracemalloc.stop()
        # keep refs until after we've measured
        _ = (vaults, sandboxes, kg)
        return result

    # ---- driver -------------------------------------------------------------

    def run_all(self) -> Dict[str, Any]:
        self.results["_meta"] = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "system": self.bench_system(),
            "suite": "aegisflow.benchmarks.bench_core",
        }
        self.results["startup"] = self.bench_startup()
        self.results["vault_writes"] = self.bench_vault_writes()
        self.results["knowledge_graph"] = self.bench_knowledge_graph()
        self.results["sandbox_io"] = self.bench_sandbox_io()
        self.results["orchestration"] = self.bench_orchestration()
        self.results["memory_footprint"] = self.bench_memory_footprint()
        return self.results

    # ---- reporting ----------------------------------------------------------

    def generate_markdown(self) -> str:
        r = self.results
        sys_info = r["_meta"]["system"]
        lines = [
            "# AegisFlow Control-Plane Benchmark Report",
            "",
            f"**Generated:** {r['_meta']['generated_at']}  ",
            f"**Python:** {sys_info.get('python')}  ",
            f"**Platform:** {sys_info.get('platform')}  ",
        ]
        if "cpu_logical" in sys_info:
            lines.append(
                f"**Hardware:** {sys_info['cpu_logical']} vCPU "
                f"({sys_info.get('cpu_physical')} physical), "
                f"{sys_info.get('ram_total_gb')}GB RAM  "
            )
        lines += ["", "## Executive Summary", "", "| KPI | Value |", "|-----|-------|"]

        s, v, k, sb, o, m = (
            r["startup"], r["vault_writes"], r["knowledge_graph"],
            r["sandbox_io"], r["orchestration"], r["memory_footprint"],
        )
        lines += [
            f"| Startup (mean) | {s['mean_ms']:.2f} ms |",
            f"| Startup (p95) | {s['p95_ms']:.2f} ms |",
            f"| Vault writes | {v['ops_per_sec']:,.0f} ops/sec (p95 {v['p95_ms']:.3f} ms) |",
            f"| KG add_triple | {k['add']['ops_per_sec']:,.0f} ops/sec (p95 {k['add']['p95_ms']:.4f} ms) |",
            f"| KG query_entity | mean {k['query']['mean_ms']:.3f} ms / p95 {k['query']['p95_ms']:.3f} ms |",
            f"| Sandbox I/O | {sb['cycles_per_sec']:,.0f} cycles/sec (p95 {sb['p95_ms']:.3f} ms) |",
            f"| Orchestration (mock LLM) | {o['mean_ms']:.2f} ms/task, {o['avg_sub_agents_per_task']} agents/task |",
            f"| Memory per vault | {m['tracemalloc_per_vault_kb']:.2f} KB (tracemalloc) |",
        ]
        if m.get("process_rss_mb") is not None:
            lines.append(f"| Process RSS (end of suite) | {m['process_rss_mb']:.1f} MB |")

        lines += ["", "## Raw JSON", "", "```json", json.dumps(r, indent=2), "```"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run_profile(output: Path, workspace: Path) -> None:
    """Profile the orchestration hot path with cProfile."""
    memory = MemoryVault(path=str(workspace / "prof-v"))
    sandbox = LocalSandbox(workspace_path=str(workspace / "prof-s"))
    lead = LeadOrchestrator(memory=memory, sandbox=sandbox)
    lead.llm = FakeLLM()

    pr = cProfile.Profile()
    pr.enable()
    for i in range(100):
        lead.delegate_and_run(f"profiled task {i}")
    pr.disable()

    output.parent.mkdir(parents=True, exist_ok=True)
    pr.dump_stats(str(output))

    buf = StringIO()
    stats = pstats.Stats(pr, stream=buf).strip_dirs().sort_stats("cumulative")
    stats.print_stats(25)
    print("\n--- cProfile (top 25 cumulative) ---")
    print(buf.getvalue())
    print(f"Profile written to {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AegisFlow control-plane benchmarks.")
    parser.add_argument("--output", type=Path, help="Write JSON results to this path.")
    parser.add_argument("--markdown", type=Path, help="Write markdown report to this path.")
    parser.add_argument("--profile", action="store_true",
                        help="Also run cProfile on the orchestration hot path.")
    parser.add_argument("--profile-out", type=Path, default=Path("benchmarks/profile.stats"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="af-bench-") as tmp:
        workspace = Path(tmp)
        suite = BenchmarkSuite(workspace=workspace)

        print("=" * 60)
        print("AegisFlow Control-Plane Benchmark Suite")
        print("=" * 60)

        suite.run_all()

        print("\n" + "=" * 60)
        report = suite.generate_markdown()
        print(report)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(suite.results, indent=2))
            print(f"\nJSON results -> {args.output}")

        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(report)
            print(f"Markdown report -> {args.markdown}")

        if args.profile:
            print("\n" + "=" * 60)
            print("Profiling orchestration hot path...")
            run_profile(args.profile_out, workspace)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
