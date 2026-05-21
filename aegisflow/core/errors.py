"""
AegisFlow Error Taxonomy.

Structured exception hierarchy that replaces generic ``Exception`` catches
throughout the codebase.  Each error carries machine-readable fields
(``code``, ``retryable``) so orchestration can make deterministic
retry / circuit-breaker decisions.

Usage:
    from aegisflow.core.errors import AegisFlowLLMError

    try:
        response = llm.chat(messages)
    except AegisFlowLLMError as e:
        if e.retryable:
            time.sleep(e.retry_after or 1)
            response = llm.chat(messages)
"""

from __future__ import annotations

from typing import Optional

# ── Base ─────────────────────────────────────────────────────────────────────


class AegisFlowError(Exception):
    """Root of the AegisFlow exception hierarchy."""

    code: str = "aegisflow_error"
    retryable: bool = False
    retry_after: Optional[float] = None

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        retryable: Optional[bool] = None,
        retry_after: Optional[float] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        if retry_after is not None:
            self.retry_after = retry_after
        self.__cause__ = cause


# ── LLM Errors ───────────────────────────────────────────────────────────────


class AegisFlowLLMError(AegisFlowError):
    """Base for all LLM-related failures."""

    code = "llm_error"


class LLMTimeoutError(AegisFlowLLMError):
    """LLM request exceeded the configured timeout."""

    code = "llm_timeout"
    retryable = True
    retry_after = 2.0


class LLMAuthError(AegisFlowLLMError):
    """Authentication / authorization failure (401/403)."""

    code = "llm_auth"
    retryable = False


class LLMRateLimitError(AegisFlowLLMError):
    """Rate limit hit (429).  ``retry_after`` is set from the header if available."""

    code = "llm_rate_limit"
    retryable = True
    retry_after = 5.0


class LLMProviderError(AegisFlowLLMError):
    """Provider returned a 5xx or malformed response."""

    code = "llm_provider"
    retryable = True
    retry_after = 3.0


# ── Sandbox Errors ───────────────────────────────────────────────────────────


class AegisFlowSandboxError(AegisFlowError):
    """Base for all sandbox-related failures."""

    code = "sandbox_error"


class SandboxPermissionError(AegisFlowSandboxError):
    """Path-traversal or filesystem permission violation."""

    code = "sandbox_permission"
    retryable = False


class SandboxTimeoutError(AegisFlowSandboxError):
    """Command execution exceeded timeout."""

    code = "sandbox_timeout"
    retryable = True
    retry_after = 1.0


class SandboxUnavailableError(AegisFlowSandboxError):
    """Sandbox backend (Docker, unshare) is not available."""

    code = "sandbox_unavailable"
    retryable = False


# ── Memory Errors ────────────────────────────────────────────────────────────


class AegisFlowMemoryError(AegisFlowError):
    """Base for all memory-related failures."""

    code = "memory_error"


class VaultCorruptionError(AegisFlowMemoryError):
    """Vault index or structure is corrupted."""

    code = "vault_corruption"
    retryable = False


class KGQueryError(AegisFlowMemoryError):
    """Knowledge-graph query failed."""

    code = "kg_query"
    retryable = True
    retry_after = 0.5


# ── Orchestration Errors ─────────────────────────────────────────────────────


class AegisFlowOrchestrationError(AegisFlowError):
    """Base for orchestration-level failures."""

    code = "orchestration_error"


class DecompositionError(AegisFlowOrchestrationError):
    """Task decomposition failed (both LLM and rule-based fallback)."""

    code = "decomposition"
    retryable = True
    retry_after = 2.0


class SynthesisError(AegisFlowOrchestrationError):
    """Result synthesis failed after sub-agents completed."""

    code = "synthesis"
    retryable = True
    retry_after = 2.0
