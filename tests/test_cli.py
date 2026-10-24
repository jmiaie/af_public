"""
Tests for the ``aegisflow`` CLI commands (doctor, bench, run, main dispatch).

The orchestrator and the benchmark subprocess are replaced with fakes so the
tests stay offline and fast.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Dict, List

import pytest

import aegisflow.orchestration.swarm as swarm_mod
from aegisflow.__main__ import build_parser, cmd_bench, cmd_doctor, cmd_run, main


def _args(*argv: str):
    return build_parser().parse_args(list(argv))


# ── doctor ───────────────────────────────────────────────────────────────────


class TestDoctor:
    def test_json_output(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            cmd_doctor(_args("doctor", "--skills-dir", str(tmp_path / "skills"), "--json"))
        data = json.loads(capsys.readouterr().out)
        assert 0 <= data["health_score"] <= 100
        assert data["checks"] and {"name", "status", "message", "issues"} <= set(data["checks"][0])
        failed = any(c["status"] == "fail" for c in data["checks"])
        assert exc.value.code == (1 if failed else 0)

    def test_text_output(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            cmd_doctor(_args("doctor", "--skills-dir", str(tmp_path), "--vault", str(tmp_path)))
        assert "Brain Health Check" in capsys.readouterr().out


# ── bench ────────────────────────────────────────────────────────────────────


class TestBench:
    def test_missing_bench_script(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            cmd_bench(_args("bench"))
        assert exc.value.code == 1
        assert "bench_core.py not found" in capsys.readouterr().out

    def test_runs_bench_core_with_args(self, tmp_path, monkeypatch):
        (tmp_path / "benchmarks").mkdir()
        (tmp_path / "benchmarks" / "bench_core.py").write_text("")
        monkeypatch.chdir(tmp_path)
        seen: List[List[str]] = []

        def fake_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 3)

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SystemExit) as exc:
            cmd_bench(_args("bench", "--output", "o.json", "--markdown", "o.md", "--profile"))
        assert exc.value.code == 3
        assert seen == [
            [
                sys.executable,
                "benchmarks/bench_core.py",
                "--output",
                "o.json",
                "--markdown",
                "o.md",
                "--profile",
            ]
        ]


# ── run ──────────────────────────────────────────────────────────────────────


class _FakeLead:
    instances: List["_FakeLead"] = []

    def __init__(self, memory: Any, sandbox: Any, llm_backend: str) -> None:
        self.memory = memory
        self.sandbox = sandbox
        self.llm_backend = llm_backend
        self.fallback_count = 0
        _FakeLead.instances.append(self)

    def delegate_and_run(self, task: str, max_agents: int = 5) -> Dict[str, Any]:
        self.max_agents = max_agents
        return {
            "task": task,
            "status": "completed",
            "sub_tasks": ["a", "b"],
            "sub_agents": [{"id": 1}],
            "synthesis": "all good",
        }


@pytest.fixture
def fake_lead(monkeypatch):
    _FakeLead.instances = []
    monkeypatch.setattr(swarm_mod, "LeadOrchestrator", _FakeLead)
    return _FakeLead


class TestRun:
    def test_json(self, tmp_path, fake_lead, capsys):
        cmd_run(
            _args(
                "run",
                "do it",
                "--agents",
                "2",
                "--backend",
                "ollama",
                "--vault",
                str(tmp_path / "v"),
                "--sandbox",
                str(tmp_path / "s"),
                "--json",
            )
        )
        data = json.loads(capsys.readouterr().out)
        assert data["task"] == "do it" and data["status"] == "completed"
        assert "elapsed_s" in data
        lead = fake_lead.instances[0]
        assert lead.llm_backend == "ollama" and lead.max_agents == 2
        assert (tmp_path / "s" / "workspace").is_dir()

    def test_text(self, tmp_path, fake_lead, capsys):
        cmd_run(
            _args("run", "task", "--vault", str(tmp_path / "v"), "--sandbox", str(tmp_path / "s"))
        )
        out = capsys.readouterr().out
        assert "Status:    completed" in out
        assert "Sub-tasks: 2" in out
        assert "## Synthesis\nall good" in out


# ── main dispatch ────────────────────────────────────────────────────────────


class TestMain:
    def test_dispatches_version(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["aegisflow", "version"])
        main()
        assert "AegisFlow v" in capsys.readouterr().out

    def test_no_command_prints_help(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["aegisflow"])
        main()
        assert "usage: aegisflow" in capsys.readouterr().out
