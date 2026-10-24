"""
Smoke tests for the offline parts of ``aegisflow.benchmarks.run_all``.

The LLM benchmarks use a fake Ollama client; the orchestrator and full-swarm
benchmarks need a live model and are not exercised here.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from aegisflow.benchmarks import run_all
from aegisflow.llm.adapters import AgenticResponse


class _FakeOllama:
    def __init__(self, **kwargs: Any) -> None:
        pass

    def complete(self, prompt: str) -> AgenticResponse:
        return AgenticResponse(content="Paris.", tokens_used=3)

    def chat(self, messages: Any) -> AgenticResponse:
        return AgenticResponse(content="4", tokens_used=2)


class TestBench:
    def test_default_workspace_is_private_tempdir(self):
        b = run_all.Bench()
        try:
            assert b.ws.is_dir()
            assert b.ws.name.startswith("af_bench_")
            assert Path(tempfile.gettempdir()) in b.ws.parents
            if os.name == "posix":
                assert (b.ws.stat().st_mode & 0o777) == 0o700
        finally:
            b.ws.rmdir()

    def test_explicit_workspace(self, tmp_path):
        assert run_all.Bench(str(tmp_path)).ws == tmp_path

    def test_llm_benches_with_fake_client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_all, "OllamaLLM", _FakeOllama)
        b = run_all.Bench(str(tmp_path))
        llm = b.bench_llm(iters=2)
        assert llm["runs"] == 2 and llm["total_tokens"] == 6
        assert llm["min_s"] <= llm["mean_s"] <= llm["max_s"]
        chat = b.bench_chat(iters=3)
        assert chat["runs"] == 3 and chat["total_tokens"] == 6

    def test_vault_kg_and_sandbox_benches(self, tmp_path):
        b = run_all.Bench(str(tmp_path))
        vw = b.bench_vault_write(n=5)
        assert "5_writes_per_sec" in vw and vw["mean_ms"] >= 0
        kg = b.bench_kg(n=5)
        assert kg["adds_per_sec"] > 0
        sw = b.bench_sandbox_write(n=5)
        assert "5_writes_per_sec" in sw
        assert (tmp_path / "sb" / "f4.txt").read_text() == "x" * 100

    def test_system_info_needs_psutil(self, tmp_path):
        pytest.importorskip("psutil")
        info = run_all.Bench(str(tmp_path)).bench_system()
        assert info["cpu_logical"] >= 1
