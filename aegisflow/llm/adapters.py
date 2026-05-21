"""
AegisFlow LLM Adapters.

Provides:
- OpenAICompatibleLLM: wraps any OpenAI-compatible API endpoint
- OpenClawSession: spawns a real OpenClaw sub-agent session as a SubAgent
- AgenticLLM: unified interface both can be swapped through
"""

import os
import uuid
import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from aegisflow.core.errors import (
    AegisFlowLLMError,
    LLMTimeoutError,
    LLMAuthError,
    LLMRateLimitError,
    LLMProviderError,
)

logger = logging.getLogger(__name__)


@dataclass
class AgenticResponse:
    """Structured response from any LLM call."""
    content: str
    raw: Any = None
    model: str = "unknown"
    tokens_used: int = 0
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
        }


@dataclass
class SubAgentResult:
    """Result from a spawned sub-agent session."""
    agent_id: str
    session_key: str
    status: str  # "success", "error", "timeout"
    response: Optional[AgenticResponse] = None
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "session_key": self.session_key,
            "status": self.status,
            "response": self.response.to_dict() if self.response else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class OpenAICompatibleLLM:
    """
    Wraps any OpenAI-compatible REST endpoint.
    For use with: vLLM, ollama (with --like openai flag), Gemini via OpenAI proxy,
    or any custom inference server.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 120,
    ):
        import urllib.request
        import urllib.parse

        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "dummy")
        self.default_model = default_model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        self._client = None  # Uses urllib directly

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> AgenticResponse:
        """Send a chat completion request."""
        import urllib.request
        import urllib.parse
        import json as _json

        model = model or self.default_model
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools

        body.update(kwargs)

        try:
            req = urllib.request.Request(
                url,
                data=_json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = _json.loads(resp.read())

            choice = data["choices"][0]
            return AgenticResponse(
                content=choice["message"]["content"] or "",
                raw=data,
                model=data.get("model", model),
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={"raw": data},
            )
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise LLMAuthError(
                    f"Authentication failed ({e.code})", cause=e
                ) from e
            elif e.code == 429:
                retry_after = float(e.headers.get("Retry-After", 5))
                raise LLMRateLimitError(
                    "Rate limit exceeded",
                    retry_after=retry_after,
                    cause=e,
                ) from e
            elif e.code >= 500:
                raise LLMProviderError(
                    f"Provider error ({e.code})", cause=e
                ) from e
            else:
                raise AegisFlowLLMError(
                    f"LLM HTTP error ({e.code})", cause=e
                ) from e
        except urllib.error.URLError as e:
            if "timed out" in str(e).lower():
                raise LLMTimeoutError(
                    f"LLM request timed out", cause=e
                ) from e
            raise AegisFlowLLMError(
                f"LLM call failed: {e}", cause=e
            ) from e
        except AegisFlowLLMError:
            raise  # Don't re-wrap our own errors
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise AegisFlowLLMError(
                f"LLM call failed: {e}", cause=e
            ) from e

    def complete(self, prompt: str, model: Optional[str] = None, **kwargs) -> AgenticResponse:
        """Simple single-shot completion (converts to chat format)."""
        return self.chat(messages=[{"role": "user", "content": prompt}], model=model, **kwargs)


class OpenClawSession:
    """
    Spawns a real OpenClaw sub-agent session as an isolated SubAgent.
    This is the key integration point — it hooks into the OpenClaw sessions
    API to run actual model-powered sub-agents with full tool access.

    Requires the OpenClaw Gateway URL and auth token from environment.
    """

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout_seconds: int = 180,
    ):
        self.gateway_url = gateway_url or os.environ.get(
            "OPENCLAW_GATEWAY_URL", "http://localhost:18789"
        )
        self.auth_token = auth_token or os.environ.get("OPENCLAW_AUTH_TOKEN", "")
        self.default_model = default_model or os.environ.get("OPENCLAW_MODEL", "myclaw/gemini-3-flash")
        self.timeout_seconds = timeout_seconds

        # Lazy import OpenClaw tools when available
        self._sessions_spawn = None
        self._sessions_send = None
        self._sessions_list = None

    def _get_openclaw_tools(self):
        """Lazily import OpenClaw's sessions tools."""
        if self._sessions_spawn is None:
            try:
                # Import the openclaw sessions tool functions if accessible
                import openclaw
                self._openclaw = openclaw
                logger.info("OpenClaw modules loaded successfully")
            except ImportError:
                logger.warning("OpenClaw modules not importable — running in simulation mode")
                self._openclaw = None

    def spawn_subagent(
        self,
        task: str,
        agent_id: Optional[str] = None,
        model: Optional[str] = None,
        run_timeout: int = 180,
    ) -> SubAgentResult:
        """
        Spawn a real OpenClaw sub-agent session for a task.
        Returns SubAgentResult with the agent's response.
        """
        import time
        self._get_openclaw_tools()

        agent_id = agent_id or f"aegisflow-sub-{uuid.uuid4().hex[:8]}"
        model = model or self.default_model

        start = time.time()

        if self._openclaw is None:
            # Simulation mode — return a mock result
            return SubAgentResult(
                agent_id=agent_id,
                session_key=f"mock-session-{uuid.uuid4().hex[:8]}",
                status="simulated",
                response=AgenticResponse(
                    content=f"[SIMULATED] Received task: {task[:100]}... (OpenClaw not importable in this environment)",
                    model=model,
                ),
                duration_ms=int((time.time() - start) * 1000),
            )

        try:
            # Use OpenClaw sessions_spawn to run the sub-agent
            # The sessions_spawn API runs an agent and waits for completion
            result = self._openclaw.sessions_spawn(
                label=agent_id,
                agentId=agent_id,
                mode="run",
                model=model,
                task=task,
                timeoutSeconds=run_timeout,
            )

            duration_ms = int((time.time() - start) * 1000)

            if result.get("status") == "completed" or result.get("status") == "ok":
                return SubAgentResult(
                    agent_id=agent_id,
                    session_key=result.get("sessionKey", "unknown"),
                    status="success",
                    response=AgenticResponse(
                        content=result.get("response", result.get("message", "")),
                        model=model,
                    ),
                    duration_ms=duration_ms,
                )
            else:
                return SubAgentResult(
                    agent_id=agent_id,
                    session_key=result.get("sessionKey", "unknown"),
                    status="error",
                    error=result.get("error", "Unknown error"),
                    duration_ms=duration_ms,
                )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"SubAgent spawn failed: {e}")
            return SubAgentResult(
                agent_id=agent_id,
                session_key="",
                status="error",
                error=str(e),
                duration_ms=duration_ms,
            )


class AgenticLLM:
    """
    Unified LLM interface. Can use either OpenAI-compatible API
    or OpenClaw session bridge. Switch implementations via strategy.

    Providers are registered in a class-level registry.  To add a new
    backend:
        AgenticLLM.register("my_backend", MyLLMClass)
    Then use:
        llm = AgenticLLM(backend="my_backend", config={...})
    """

    _REGISTRY: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, provider_cls: type) -> None:
        """Register a provider class under a backend name."""
        cls._REGISTRY[name] = provider_cls

    @classmethod
    def available_backends(cls) -> List[str]:
        """Return the list of registered backend names."""
        return list(cls._REGISTRY.keys())

    def __init__(
        self,
        backend: str = "openai",  # "openai" | "openclaw" | "gemini" | "ollama" | "nvidia" | …
        openai_config: Optional[Dict[str, Any]] = None,
        openclaw_config: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        # Legacy compat: honour explicit openai_config / openclaw_config kwargs
        if backend == "openclaw":
            self._impl = OpenClawSession(**(openclaw_config or config or {}))
        elif backend == "openai":
            self._impl = OpenAICompatibleLLM(**(openai_config or config or {}))
        elif backend in self._REGISTRY:
            self._impl = self._REGISTRY[backend](**(config or {}))
        else:
            raise ValueError(
                f"Unknown LLM backend '{backend}'. "
                f"Available: {self.available_backends()}"
            )

        self.backend = backend

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> AgenticResponse:
        return self._impl.chat(messages, **kwargs)

    def complete(self, prompt: str, **kwargs) -> AgenticResponse:
        return self._impl.complete(prompt, **kwargs)

    def spawn(self, task: str, **kwargs) -> SubAgentResult:
        """Only available on OpenClaw backend."""
        if not isinstance(self._impl, OpenClawSession):
            raise NotImplementedError("spawn() requires OpenClaw backend")
        return self._impl.spawn_subagent(task, **kwargs)


# ---------------------------------------------------------------------------
# Auto-register built-in providers on import
# ---------------------------------------------------------------------------
def _auto_register() -> None:
    """Register all built-in LLM providers.  Imports are lazy so missing
    optional deps don't break the package."""
    from aegisflow.llm.gemini import GeminiLLM, GeminiOpenAIProxy
    from aegisflow.llm.ollama import OllamaLLM, OllamaOpenAIProxy
    from aegisflow.llm.nvidia import NVIDIAllm, LocalNVIDIABridge

    AgenticLLM.register("gemini", GeminiLLM)
    AgenticLLM.register("gemini_proxy", GeminiOpenAIProxy)
    AgenticLLM.register("ollama", OllamaLLM)
    AgenticLLM.register("ollama_proxy", OllamaOpenAIProxy)
    AgenticLLM.register("nvidia", NVIDIAllm)
    AgenticLLM.register("nvidia_local", LocalNVIDIABridge)


_auto_register()