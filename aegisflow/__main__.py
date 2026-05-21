"""
AegisFlow CLI — ``python -m aegisflow`` or ``aegisflow`` (via pyproject.toml script entry).

Commands:
    aegisflow doctor   — Run brain health checks
    aegisflow bench    — Run the control-plane benchmark suite
    aegisflow run      — Execute a task via the swarm orchestrator
    aegisflow version  — Print version info
"""

from __future__ import annotations

import argparse
import json
import sys
import time


def cmd_version(args: argparse.Namespace) -> None:
    """Print version and system info."""
    from aegisflow import __version__
    print(f"AegisFlow v{__version__}")
    print(f"Python {sys.version}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run BrainDoctor health checks."""
    from aegisflow.brain.doctor import BrainDoctor

    doctor = BrainDoctor(
        skills_dir=args.skills_dir,
        vault_path=args.vault or None,
    )
    report = doctor.run()

    if args.json:
        data = {
            "health_score": report.health_score,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "issues": [
                        {"type": i.type, "skill": i.skill, "action": i.action}
                        for i in c.issues
                    ],
                }
                for c in report.checks
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(report.render())

    sys.exit(1 if report.has_failures() else 0)


def cmd_bench(args: argparse.Namespace) -> None:
    """Run the control-plane benchmark suite."""
    # Import here so the rest of the CLI stays light.
    from pathlib import Path
    if not Path("benchmarks/bench_core.py").exists():
        print("Error: benchmarks/bench_core.py not found in the current directory.")
        print("Run from the AegisFlow repo root.")
        sys.exit(1)

    bench_args = ["--output", args.output]
    if args.markdown:
        bench_args.extend(["--markdown", args.markdown])
    if args.profile:
        bench_args.append("--profile")

    # bench_core.main() uses argparse internally; call it via subprocess
    import subprocess
    cmd = [sys.executable, "benchmarks/bench_core.py"] + bench_args
    result = subprocess.run(cmd, cwd=".")
    sys.exit(result.returncode)


def cmd_run(args: argparse.Namespace) -> None:
    """Execute a task via the swarm orchestrator (offline / mock LLM)."""
    from aegisflow.memory import MemoryVault
    from aegisflow.orchestration.swarm import LeadOrchestrator
    from aegisflow.sandbox import LocalSandbox

    memory = MemoryVault(path=args.vault or "./vault")
    sandbox = LocalSandbox(workspace_path=args.sandbox or "./sandbox_workspace")

    lead = LeadOrchestrator(
        memory=memory,
        sandbox=sandbox,
        llm_backend=args.backend,
    )

    start = time.time()
    result = lead.delegate_and_run(args.task, max_agents=args.agents)
    elapsed = time.time() - start

    if args.json:
        result["elapsed_s"] = round(elapsed, 3)
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"  Task:      {result['task'][:80]}")
        print(f"  Status:    {result['status']}")
        print(f"  Sub-tasks: {len(result['sub_tasks'])}")
        print(f"  Agents:    {len(result['sub_agents'])}")
        print(f"  Elapsed:   {elapsed:.2f}s")
        print(f"  Fallbacks: {lead.fallback_count}")
        print(f"{'='*60}")
        print(f"\n## Synthesis\n{result['synthesis'][:500]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegisflow",
        description="AegisFlow — Universal, Security-First Multi-Agent Hybrid System",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # version
    sub.add_parser("version", help="Print version info")

    # doctor
    p_doc = sub.add_parser("doctor", help="Run brain health checks")
    p_doc.add_argument("--skills-dir", default="./skills", help="Path to skills directory")
    p_doc.add_argument("--vault", default=None, help="Path to vault directory")
    p_doc.add_argument("--json", action="store_true", help="Output as JSON")

    # bench
    p_bench = sub.add_parser("bench", help="Run control-plane benchmarks")
    p_bench.add_argument("--output", default="benchmarks/latest.json", help="Output JSON path")
    p_bench.add_argument("--markdown", default=None, help="Output markdown path")
    p_bench.add_argument("--profile", action="store_true", help="Enable cProfile")

    # run
    p_run = sub.add_parser("run", help="Execute a task via the swarm orchestrator")
    p_run.add_argument("task", help="The task to execute")
    p_run.add_argument("--agents", type=int, default=3, help="Max sub-agents")
    p_run.add_argument("--backend", default="openai", help="LLM backend")
    p_run.add_argument("--vault", default=None, help="Vault path")
    p_run.add_argument("--sandbox", default=None, help="Sandbox workspace path")
    p_run.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "version": cmd_version,
        "doctor": cmd_doctor,
        "bench": cmd_bench,
        "run": cmd_run,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
