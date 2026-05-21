"""
AegisFlow Benchmark Suite
Run: python3 -m aegisflow.benchmarks.run_all
"""

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict

import psutil

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aegisflow.llm import OllamaLLM
from aegisflow.memory import KnowledgeGraph, MemoryVault
from aegisflow.orchestration import LeadOrchestrator
from aegisflow.sandbox import LocalSandbox


class Bench:
    def __init__(self, ws="/tmp/af_bench"):
        self.ws = Path(ws)
        self._proc = psutil.Process(os.getpid())

    def mem_mb(self): return self._proc.memory_info().rss / 1024 / 1024

    def run_all(self, iters=5) -> Dict[str, Any]:
        r = {}
        r["system"] = self.bench_system()
        print(f"\n[1] Ollama complete ({iters} runs)")
        r["ollama_complete"] = self.bench_llm(iters)
        print(f"\n[2] Ollama chat ({iters} runs)")
        r["ollama_chat"] = self.bench_chat(iters)
        print("\n[3] Vault write (1000)")
        r["vault_write"] = self.bench_vault_write(1000)
        print("\n[4] KnowledgeGraph (1000 triples)")
        r["knowledge_graph"] = self.bench_kg(1000)
        print("\n[5] Sandbox write (500)")
        r["sandbox_write"] = self.bench_sandbox_write(500)
        print("\n[6] Sandbox exec (20)")
        r["sandbox_exec"] = self.bench_sandbox_exec(20)
        print("\n[7] Orchestrator (3 runs)")
        r["orchestrator"] = self.bench_orch(3)
        print("\n[8] Full swarm (1 run)")
        r["full_swarm"] = self.bench_full_swarm()
        return r

    def bench_system(self):
        vm = psutil.virtual_memory()
        return {
            "python": platform.python_version(),
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "ram_total_gb": round(vm.total / 1024**3, 1),
            "ram_avail_gb": round(vm.available / 1024**3, 1),
        }

    def bench_llm(self, iters=5):
        llm = OllamaLLM(model="tinyllama:latest")
        times, tokens = [], 0
        for i in range(iters):
            t0 = time.perf_counter()
            resp = llm.complete("What is the capital of France? Answer in one sentence.")
            times.append(time.perf_counter() - t0)
            tokens += resp.tokens_used
            print(f"  run {i+1}: {times[-1]:.3f}s | {resp.tokens_used}t | {resp.content[:50]}")
        return {"mean_s": round(sum(times)/len(times),3), "min_s": round(min(times),3),
                "max_s": round(max(times),3), "total_tokens": tokens, "runs": iters}

    def bench_chat(self, iters=5):
        llm = OllamaLLM(model="tinyllama:latest")
        msgs = [{"role":"system","content":"You are helpful."},{"role":"user","content":"What is 2+2?"}]
        times, tokens = [], 0
        for i in range(iters):
            t0 = time.perf_counter()
            resp = llm.chat(msgs)
            times.append(time.perf_counter() - t0)
            tokens += resp.tokens_used
            print(f"  run {i+1}: {times[-1]:.3f}s | {resp.tokens_used}t")
        return {"mean_s": round(sum(times)/len(times),3), "min_s": round(min(times),3),
                "max_s": round(max(times),3), "total_tokens": tokens, "runs": iters}

    def bench_vault_write(self, n=1000):
        vault = MemoryVault(path=str(self.ws / "bv"))
        times = []
        for i in range(n):
            t0 = time.perf_counter()
            vault.store_verbatim(content=f"Bench {i}", category="bench", filename=f"n{i}.md")
            times.append(time.perf_counter() - t0)
        total = sum(times)
        return {"total_s": round(total,3), f"{n}_writes_per_sec": round(n/total,0),
                "mean_ms": round(sum(times)/len(times)*1000,3)}

    def bench_kg(self, n=1000):
        kg = KnowledgeGraph(db_path=str(self.ws / "kg.db"))
        t0 = time.perf_counter()
        for i in range(n):
            kg.add_triple(f"e{i%100}", "rel", f"e{(i+1)%100}")
        add_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        for i in range(100):
            kg.query_entity(f"e{i}")
        q_s = time.perf_counter() - t0
        return {"1000_add_s": round(add_s,4), "100_queries_s": round(q_s,4),
                "adds_per_sec": round(n/add_s,0)}

    def bench_sandbox_write(self, n=500):
        sb = LocalSandbox(workspace_path=str(self.ws / "sb"))
        times = []
        for i in range(n):
            t0 = time.perf_counter()
            sb.write_file(f"f{i}.txt", "x" * 100)
            times.append(time.perf_counter() - t0)
        total = sum(times)
        return {"total_s": round(total,3), f"{n}_writes_per_sec": round(n/total,0),
                "mean_ms": round(sum(times)/len(times)*1000,3)}

    def bench_sandbox_exec(self, n=20):
        sb = LocalSandbox(workspace_path=str(self.ws / "sb2"))
        times = []
        for i in range(n):
            t0 = time.perf_counter()
            sb.execute("python3 -c 'sum(range(10000))'")
            times.append(time.perf_counter() - t0)
        total = sum(times)
        return {"total_s": round(total,3), f"{n}_execs_per_sec": round(n/total,1),
                "mean_ms": round(sum(times)/len(times)*1000,1)}

    def bench_orch(self, iters=3):
        vault = MemoryVault(path=str(self.ws / "ov"))
        sb = LocalSandbox(workspace_path=str(self.ws / "os"))
        task = "Analyze APN 167-22-045-A for real estate investment"
        results = []
        for i in range(iters):
            orch = LeadOrchestrator(vault, sb, llm_backend="openai",
                llm_config={"base_url":"http://localhost:11434/v1","api_key":"ollama",
                           "default_model":"tinyllama:latest"})
            t0 = time.perf_counter()
            res = orch.delegate_and_run(task)
            elapsed = time.perf_counter() - t0
            results.append({"time_s": round(elapsed,2), "subtasks": len(res["sub_tasks"]),
                            "agents": len(res["sub_agents"]), "status": res["status"]})
            print(f"  run {i+1}: {elapsed:.1f}s | {len(res['sub_tasks'])} sub-tasks | {res['status']}")
        return {"runs": results}

    def bench_full_swarm(self):
        vault = MemoryVault(path=str(self.ws / "fv"))
        sb = LocalSandbox(workspace_path=str(self.ws / "fs"))
        task = "Research Arizona real estate investment opportunities"
        orch = LeadOrchestrator(vault, sb, llm_backend="openai",
            llm_config={"base_url":"http://localhost:11434/v1","api_key":"ollama",
                       "default_model":"tinyllama:latest"})
        timings = {}
        t0 = time.perf_counter()
        st = orch._decompose_with_llm(task)
        timings["decompose"] = round(time.perf_counter()-t0, 3)
        t0 = time.perf_counter()
        agents = []
        for s in st:
            a = orch.SubAgent(task_id=orch.session_id, prompt=s, sandbox=sb,
                              llm=orch.llm, backend="openai")
            agents.append(a.execute())
        timings["subagents"] = round(time.perf_counter()-t0, 3)
        t0 = time.perf_counter()
        sp = "\n".join(f"[{i+1}] {r.get('result',r.get('error',''))[:100]}" for i,r in enumerate(agents))
        synth = orch.llm.chat([{"role":"user","content":f"Summarize:\n{sp}"}])
        timings["synthesis"] = round(time.perf_counter()-t0, 3)
        timings["total"] = round(sum(timings.values()), 3)
        print(f"  decompose: {timings['decompose']}s | subagents: {timings['subagents']}s | "
              f"synthesis: {timings['synthesis']}s | total: {timings['total']}s")
        return {"task": task, "subtasks": len(st), "timings": timings,
                "synth_preview": synth.content[:150] if synth.content else "N/A",
                "synth_tokens": synth.tokens_used}


def main():
    print("=" * 60)
    print("AegisFlow Benchmark Suite")
    print("=" * 60)
    b = Bench("/tmp/af_bench")
    results = b.run_all(iters=5)

    report_path = Path("/home/ubuntu/.openclaw/workspace/sandfish/benchmark_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    sys_info = results["system"]
    print(f"\nSystem: {sys_info['python']} | {sys_info['cpu_logical']} vCPU | "
          f"{sys_info['ram_avail_gb']}GB RAM avail")

    llm = results["ollama_complete"]
    print("\nLLM (TinyLlama 1B @ Ollama):")
    print(f"  Completion: {llm['mean_s']}s mean | {llm['min_s']}-{llm['max_s']}s range | "
          f"{llm['total_tokens']} tokens total")

    vw = results["vault_write"]
    print("\nMemoryVault:")
    print(f"  Write: {vw[f'{1000}_writes_per_sec']} writes/sec | {vw['mean_ms']}ms/write")

    kg = results["knowledge_graph"]
    print(f"  KnowledgeGraph: {kg['adds_per_sec']} triples/sec add | "
          f"{kg['100_queries_s']}s for 100 queries")

    sw = results["sandbox_write"]
    print("\nSandbox:")
    print(f"  File write: {sw[f'{500}_writes_per_sec']} writes/sec | {sw['mean_ms']}ms/write")

    se = results["sandbox_exec"]
    print(f"  Shell exec: {se[f'{20}_execs_per_sec']} execs/sec")

    orch = results["orchestrator"]
    avg_time = sum(r["time_s"] for r in orch["runs"]) / len(orch["runs"])
    print("\nOrchestrator:")
    print(f"  Avg task: {avg_time:.1f}s | {orch['runs'][0]['subtasks']} sub-tasks decomposed")

    fs = results["full_swarm"]
    print("\nFull Swarm (end-to-end):")
    print(f"  Total: {fs['timings']['total']}s | decompose:{fs['timings']['decompose']}s "
          f"| subagents:{fs['timings']['subagents']}s | synthesis:{fs['timings']['synthesis']}s")

    print(f"\nReport saved: {report_path}")
    return results


if __name__ == "__main__":
    main()
