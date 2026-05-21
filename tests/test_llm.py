"""
Tests for aegisflow.llm — AgenticLLM registry, provider pattern, data classes.

All offline — no real API calls.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aegisflow.llm.adapters import (
    AgenticLLM,
    AgenticResponse,
    SubAgentResult,
    OpenAICompatibleLLM,
    OpenClawSession,
)


# ── AgenticResponse ──────────────────────────────────────────────────────────


class TestAgenticResponse:
    def test_to_dict(self):
        r = AgenticResponse(content="hello", model="test", tokens_used=42)
        d = r.to_dict()
        assert d["content"] == "hello"
        assert d["model"] == "test"
        assert d["tokens_used"] == 42

    def test_defaults(self):
        r = AgenticResponse(content="x")
        assert r.model == "unknown"
        assert r.tokens_used == 0
        assert r.finish_reason == "stop"
        assert r.metadata == {}


# ── SubAgentResult ───────────────────────────────────────────────────────────


class TestSubAgentResult:
    def test_to_dict_with_response(self):
        resp = AgenticResponse(content="result", model="m")
        r = SubAgentResult(
            agent_id="a1", session_key="sk", status="success", response=resp
        )
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["response"]["content"] == "result"

    def test_to_dict_without_response(self):
        r = SubAgentResult(
            agent_id="a1", session_key="sk", status="error", error="boom"
        )
        d = r.to_dict()
        assert d["response"] is None
        assert d["error"] == "boom"


# ── AgenticLLM Registry ─────────────────────────────────────────────────────


class _MockProvider:
    """Minimal LLM provider for testing."""

    def __init__(self, greeting="hello", **kwargs):
        self.greeting = greeting

    def chat(self, messages, **kwargs):
        return AgenticResponse(content=f"{self.greeting} world")

    def complete(self, prompt, **kwargs):
        return self.chat([{"role": "user", "content": prompt}])


class TestAgenticLLMRegistry:
    def test_register_and_use(self):
        AgenticLLM.register("mock_test", _MockProvider)
        llm = AgenticLLM(backend="mock_test")
        result = llm.chat([{"role": "user", "content": "hi"}])
        assert result.content == "hello world"

    def test_register_with_config(self):
        AgenticLLM.register("mock_test2", _MockProvider)
        llm = AgenticLLM(backend="mock_test2", config={"greeting": "howdy"})
        result = llm.chat([{"role": "user", "content": "hi"}])
        assert result.content == "howdy world"

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            AgenticLLM(backend="nonexistent_xyzzy")

    def test_available_backends(self):
        backends = AgenticLLM.available_backends()
        assert "gemini" in backends
        assert "ollama" in backends
        assert "nvidia" in backends

    def test_openai_default(self):
        llm = AgenticLLM(backend="openai")
        assert isinstance(llm._impl, OpenAICompatibleLLM)

    def test_openclaw_backend(self):
        llm = AgenticLLM(backend="openclaw")
        assert isinstance(llm._impl, OpenClawSession)

    def test_spawn_on_non_openclaw_raises(self):
        llm = AgenticLLM(backend="openai")
        with pytest.raises(NotImplementedError):
            llm.spawn("do something")


# ── OpenClawSession simulation mode ──────────────────────────────────────────


class TestOpenClawSimulation:
    def test_spawn_without_openclaw_returns_simulated(self):
        session = OpenClawSession()
        result = session.spawn_subagent(task="test task")
        assert result.status == "simulated"
        assert "SIMULATED" in result.response.content
