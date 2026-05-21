"""
AegisFlow Protocol Contracts.

Formal typing.Protocol definitions that every LLM provider, sandbox, and
memory backend must satisfy.  These enable static type checking (mypy) and
make the contracts explicit — no more duck-typing surprises.

Usage:
    from aegisflow.core.protocols import LLMProvider, SandboxProvider

    def run_agent(llm: LLMProvider, sandbox: SandboxProvider) -> str:
        ...
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from aegisflow.llm.adapters import AgenticResponse
    from aegisflow.sandbox.environment import SandboxResult


# ── LLM ──────────────────────────────────────────────────────────────────────


@runtime_checkable
class LLMProvider(Protocol):
    """Contract that every LLM adapter must implement.

    Runtime-checkable so you can do ``isinstance(obj, LLMProvider)``.
    """

    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> AgenticResponse:
        """Send a multi-turn chat completion request."""
        ...

    def complete(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> AgenticResponse:
        """Single-shot text completion (convenience wrapper over chat)."""
        ...


@runtime_checkable
class StreamingLLMProvider(LLMProvider, Protocol):
    """Extended contract for providers that support streaming responses."""

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> Any:
        """Yield response chunks as an iterator / async iterator."""
        ...


# ── Sandbox ──────────────────────────────────────────────────────────────────


@runtime_checkable
class SandboxProvider(Protocol):
    """Contract for all sandbox implementations."""

    workspace: str
    isolation_level: str

    def write_file(self, relative_path: str, content: str) -> str:
        """Write content to a sandboxed file.  Returns absolute path."""
        ...

    def read_file(self, relative_path: str) -> str:
        """Read a file from the sandbox."""
        ...

    def execute(self, command: str, **kwargs: Any) -> SandboxResult:
        """Execute a shell command inside the sandbox."""
        ...

    def cleanup(self) -> None:
        """Clean up the sandbox workspace."""
        ...


# ── Memory ───────────────────────────────────────────────────────────────────


@runtime_checkable
class MemoryProvider(Protocol):
    """Contract for memory vault implementations."""

    def store_verbatim(
        self,
        content: str,
        category: str = "work",
        filename: str = "notes.md",
    ) -> None:
        """Store unsummarized content to the vault."""
        ...

    def retrieve(self, query: str) -> List[str]:
        """Retrieve matching content from the vault."""
        ...


# ── Tool ─────────────────────────────────────────────────────────────────────


@runtime_checkable
class Tool(Protocol):
    """Contract for tools that can be injected into sub-agent contexts."""

    name: str
    description: str

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Run the tool and return structured results."""
        ...
