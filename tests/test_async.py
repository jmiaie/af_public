"""
Tests for async orchestration and fallback counter.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aegisflow.memory import MemoryVault
from aegisflow.orchestration import LeadOrchestrator
from aegisflow.sandbox import LocalSandbox


class _FakeLLM:
    backend = "fake"
    def chat(self, messages, **kwargs):
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        if "Decompose" in user_msg:
            content = "1. Step A\n2. Step B\n3. Step C"
        elif "Synthesize" in user_msg:
            content = "Synthesis done."
        else:
            content = "Mocked."
        return SimpleNamespace(content=content, tokens_used=0)
    def complete(self, prompt, **kwargs):
        return self.chat([{"role": "user", "content": prompt}])


class _FailingLLM:
    backend = "fail"
    def chat(self, messages, **kwargs):
        raise RuntimeError("LLM offline")
    def complete(self, prompt, **kwargs):
        raise RuntimeError("LLM offline")


def test_async_delegation(tmp_path):
    memory = MemoryVault(path=str(tmp_path / "vault"))
    sandbox = LocalSandbox(workspace_path=str(tmp_path / "sandbox"))
    lead = LeadOrchestrator(memory=memory, sandbox=sandbox)
    lead.llm = _FakeLLM()
    result = asyncio.run(lead.delegate_and_run_async("Test async."))
    assert result["status"] == "success"
    assert len(result["sub_tasks"]) >= 2


def test_fallback_counter(tmp_path):
    memory = MemoryVault(path=str(tmp_path / "vault"))
    sandbox = LocalSandbox(workspace_path=str(tmp_path / "sandbox"))
    lead = LeadOrchestrator(memory=memory, sandbox=sandbox)
    lead.llm = _FailingLLM()
    # decompose will fail -> fallback, but execute will also fail
    # so we just check the counter incremented
    assert lead.fallback_count == 0
    try:
        lead.delegate_and_run("X")
    except Exception:
        pass
    assert lead.fallback_count == 1
