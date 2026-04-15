"""
AegisFlow LLM Adapters — Ollama Provider.

Provides integration with local Ollama instances.
No API key needed — runs entirely locally.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional

from aegisflow.llm.adapters import AgenticResponse

logger = logging.getLogger(__name__)


class OllamaLLM:
    """
    Ollama local inference client.
    Requires a running `ollama serve` instance.

    Default endpoint: http://localhost:11434
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "tinyllama:latest",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self.timeout = timeout
        self._api = f"{self.base_url}/api"

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> AgenticResponse:
        """Send chat request to Ollama."""
        import urllib.request

        model = model or self.default_model
        url = f"{self._api}/chat"

        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        body = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_k": kwargs.get("top_k", 40),
                "top_p": kwargs.get("top_p", 0.95),
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())

            content = data.get("message", {}).get("content", "")
            eval_count = data.get("eval_count", 0)
            prompt_count = data.get("prompt_count", 0)

            return AgenticResponse(
                content=content,
                raw=data,
                model=model,
                tokens_used=eval_count + prompt_count,
                finish_reason="stop",
                metadata={
                    "prompt_tokens": prompt_count,
                    "completion_tokens": eval_count,
                    "model": model,
                },
            )
        except Exception as e:
            logger.error(f"Ollama chat failed: {e}")
            raise

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs,
    ) -> AgenticResponse:
        """Single-shot completion."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model or self.default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def list_models(self) -> List[Dict[str, Any]]:
        """List models available in Ollama."""
        import urllib.request

        try:
            req = urllib.request.Request(
                f"{self._api}/tags",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return data.get("models", [])
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.base_url}/", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False


class OllamaOpenAIProxy:
    """
    Wraps Ollama as an OpenAI-compatible endpoint.
    Use this as a drop-in replacement for OpenAICompatibleLLM.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "tinyllama:latest",
        api_key: str = "ollama",  # Ollama doesn't need a key
        timeout: int = 120,
    ):
        from aegisflow.llm.adapters import OpenAICompatibleLLM
        self._impl = OpenAICompatibleLLM(
            base_url=base_url,
            api_key=api_key,
            default_model=model,
            timeout=timeout,
        )
        self.model = model

    def chat(self, messages: List[Dict[str, str]], **kwargs):
        # Ollama v1 API uses /v1/chat/completions
        kwargs.setdefault("model", self.model)
        return self._impl.chat(messages, **kwargs)

    def complete(self, prompt: str, **kwargs):
        return self._impl.complete(prompt, **kwargs)