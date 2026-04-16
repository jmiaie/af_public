"""
Core smoke tests for the AegisFlow public API.

These exercise the deterministic control-plane only — they do not hit any
real LLM endpoint. The orchestrator test injects a fake LLM so the suite
is runnable offline and in CI without network access.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from aegisflow.memory import KnowledgeGraph, MemoryVault, PalaceNavigation
from aegisflow.orchestration import LeadOrchestrator
from aegisflow.sandbox import LocalSandbox


def test_memory_vault_creation(tmp_path):
    MemoryVault(path=str(tmp_path))
    for folder in ("brain", "work", "org", "perf"):
        assert os.path.exists(tmp_path / folder)


def test_knowledge_graph_addition():
    kg = KnowledgeGraph()
    kg.add_triple("Agent", "solves", "Task")
    assert len(kg.triples) == 1
    hit = kg.query_entity("Agent")
    assert hit and hit[0]["predicate"] == "solves"


def test_palace_navigation_context(tmp_path):
    vault = MemoryVault(path=str(tmp_path))
    palace = PalaceNavigation(vault=vault)
    palace.create_wing("research", "semantic")
    assert "1 wings" in palace.get_context()


def test_sandbox_path_traversal_prevention(tmp_path):
    sandbox = LocalSandbox(workspace_path=str(tmp_path))
    with pytest.raises(PermissionError):
        sandbox.read_file("../../../../etc/passwd")


def test_sandbox_write_read_roundtrip(tmp_path):
    sandbox = LocalSandbox(workspace_path=str(tmp_path))
    sandbox.write_file("workspace/hello.txt", "hi")
    assert sandbox.read_file("workspace/hello.txt") == "hi"


class _FakeLLM:
    """Deterministic offline stand-in for aegisflow.llm.AgenticLLM."""

    backend = "fake"

    def chat(self, messages, **kwargs):
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        if "Decompose" in user_msg:
            content = "1. Analyze the input\n2. Execute actions\n3. Verify results"
        elif "Synthesize" in user_msg:
            content = "Synthesis complete."
        else:
            content = "Mocked result."
        return SimpleNamespace(content=content, tokens_used=0)

    def complete(self, prompt, **kwargs):
        return self.chat([{"role": "user", "content": prompt}])


def test_orchestrator_delegation(tmp_path):
    memory = MemoryVault(path=str(tmp_path / "vault"))
    sandbox = LocalSandbox(workspace_path=str(tmp_path / "sandbox"))

    lead = LeadOrchestrator(memory=memory, sandbox=sandbox)
    lead.llm = _FakeLLM()  # swap LLM before any call is issued

    result = lead.delegate_and_run("Build a secure multi-agent system.")

    assert result["status"] == "success"
    assert lead.sub_agents, "expected at least one sub-agent to be spawned"
    assert len(result["sub_tasks"]) >= 2
