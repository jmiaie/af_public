"""
Tests for aegisflow.core — protocols and error taxonomy.
"""
from __future__ import annotations

import pytest

from aegisflow.core.errors import (
    AegisFlowError,
    AegisFlowLLMError,
    AegisFlowMemoryError,
    AegisFlowSandboxError,
    LLMAuthError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    SandboxPermissionError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from aegisflow.core.protocols import LLMProvider, MemoryProvider, SandboxProvider
from aegisflow.llm.adapters import OpenAICompatibleLLM
from aegisflow.memory.ompa_adapter import MemoryVault
from aegisflow.sandbox.environment import DockerSandbox, LocalSandbox, NamespaceSandbox

# ── Error Hierarchy ──────────────────────────────────────────────────────────


class TestErrorHierarchy:
    def test_base_is_exception(self):
        assert issubclass(AegisFlowError, Exception)

    def test_llm_errors_chain(self):
        assert issubclass(LLMTimeoutError, AegisFlowLLMError)
        assert issubclass(LLMAuthError, AegisFlowLLMError)
        assert issubclass(LLMRateLimitError, AegisFlowLLMError)
        assert issubclass(LLMProviderError, AegisFlowLLMError)
        assert issubclass(AegisFlowLLMError, AegisFlowError)

    def test_sandbox_errors_chain(self):
        assert issubclass(SandboxPermissionError, AegisFlowSandboxError)
        assert issubclass(SandboxTimeoutError, AegisFlowSandboxError)
        assert issubclass(SandboxUnavailableError, AegisFlowSandboxError)

    def test_memory_errors_chain(self):
        assert issubclass(AegisFlowMemoryError, AegisFlowError)

    def test_retryable_flags(self):
        assert LLMTimeoutError("x").retryable is True
        assert LLMAuthError("x").retryable is False
        assert LLMRateLimitError("x").retryable is True
        assert SandboxPermissionError("x").retryable is False
        assert SandboxTimeoutError("x").retryable is True

    def test_error_codes(self):
        assert LLMTimeoutError("x").code == "llm_timeout"
        assert LLMAuthError("x").code == "llm_auth"
        assert SandboxPermissionError("x").code == "sandbox_permission"

    def test_retry_after(self):
        e = LLMRateLimitError("rate limited", retry_after=10.0)
        assert e.retry_after == 10.0

    def test_cause_chaining(self):
        original = ValueError("root")
        e = AegisFlowLLMError("wrapped", cause=original)
        assert e.__cause__ is original

    def test_catchable_as_base(self):
        with pytest.raises(AegisFlowError):
            raise LLMTimeoutError("timeout")


# ── Protocol Conformance ─────────────────────────────────────────────────────


class TestProtocolConformance:
    def test_local_sandbox_satisfies_protocol(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        assert isinstance(sb, SandboxProvider)

    def test_namespace_sandbox_satisfies_protocol(self, tmp_path):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        assert isinstance(sb, SandboxProvider)

    def test_docker_sandbox_satisfies_protocol(self, tmp_path):
        sb = DockerSandbox(workspace_path=str(tmp_path))
        assert isinstance(sb, SandboxProvider)

    def test_memory_vault_satisfies_protocol(self, tmp_path):
        mv = MemoryVault(path=str(tmp_path))
        assert isinstance(mv, MemoryProvider)

    def test_openai_llm_satisfies_protocol(self):
        llm = OpenAICompatibleLLM()
        assert isinstance(llm, LLMProvider)


# ── Sandbox Structured Errors ────────────────────────────────────────────────


class TestSandboxStructuredErrors:
    def test_traversal_raises_sandbox_permission_error(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.read_file("../../../../etc/passwd")

    def test_traversal_is_aegisflow_error(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        with pytest.raises(AegisFlowError):
            sb.read_file("../../../../etc/passwd")

    def test_namespace_traversal_structured(self, tmp_path):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.write_file("../../../../tmp/evil.txt", "bad")

    def test_docker_traversal_structured(self, tmp_path):
        sb = DockerSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.read_file("../../../../etc/passwd")


# ── CLI ──────────────────────────────────────────────────────────────────────


class TestCLI:
    def test_version_command(self, capsys):
        import argparse

        from aegisflow.__main__ import cmd_version
        cmd_version(argparse.Namespace())
        out = capsys.readouterr().out
        assert "AegisFlow" in out
        assert "0.3.0" in out

    def test_parser_builds(self):
        from aegisflow.__main__ import build_parser
        parser = build_parser()
        args = parser.parse_args(["version"])
        assert args.command == "version"

    def test_doctor_parser(self):
        from aegisflow.__main__ import build_parser
        parser = build_parser()
        args = parser.parse_args(["doctor", "--skills-dir", "/tmp/skills", "--json"])
        assert args.command == "doctor"
        assert args.json is True

    def test_run_parser(self):
        from aegisflow.__main__ import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "Analyze logs", "--agents", "5", "--json"])
        assert args.command == "run"
        assert args.task == "Analyze logs"
        assert args.agents == 5
