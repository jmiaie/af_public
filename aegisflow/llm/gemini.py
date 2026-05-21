"""
AegisFlow LLM Adapters — Gemini Provider.

Provides direct integration with Google Gemini API via REST.
Supports Gemini 2.0 Flash (free tier), Gemini 2.5 Flash, and Pro models.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

from aegisflow.llm.adapters import AgenticResponse

logger = logging.getLogger(__name__)


@dataclass
class GeminiConfig:
    """Configuration for Gemini API."""
    api_key: str
    model: str = "gemini-2.0-flash"
    project_id: Optional[str] = None  # For Vertex AI
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout: int = 120
    temperature: float = 0.7
    max_tokens: int = 2048

    @classmethod
    def from_env(cls, prefix: str = "GEMINI_") -> "GeminiConfig":
        """Load config from environment variables."""
        return cls(
            api_key=os.environ.get(f"{prefix}API_KEY", ""),
            model=os.environ.get(f"{prefix}MODEL", "gemini-2.0-flash"),
            base_url=os.environ.get(f"{prefix}BASE_URL", cls.base_url),
            timeout=int(os.environ.get(f"{prefix}TIMEOUT", "120")),
        )


class GeminiLLM:
    """
    Direct Gemini API client using REST interface.
    Works with:
    - Google AI Studio (generativelanguage.googleapis.com)
    - Vertex AI (via project_id and regional endpoint)
    """

    def __init__(self, config: Optional[GeminiConfig] = None, **kwargs: Any):
        if config is None:
            config = GeminiConfig(**kwargs)
        self.config = config
        self.model = config.model

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the Gemini API."""
        import urllib.parse
        import urllib.request

        model_path = self.model.replace("/", "%2F")
        url = (
            f"{self.config.base_url}/models/{model_path}:generateContent"
            f"?key={self.config.api_key}"
        )

        headers = {"Content-Type": "application/json"}
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url, data=body, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return cast(Dict[str, Any], json.loads(resp.read()))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Gemini HTTP {e.code}: {error_body[:500]}")
            raise Exception(f"Gemini API error {e.code}: {error_body[:300]}")
        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            raise

    def _messages_to_gemini(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style messages to Gemini format."""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            # Gemini uses 'model' for assistant, 'user' for human
            gemini_role = "model" if role == "assistant" else "user"
            content = msg.get("content", "")
            if isinstance(content, str):
                contents.append({"role": gemini_role, "parts": [{"text": content}]})
            else:
                # Could be multi-modal content
                parts = []
                for part in content:
                    if part.get("type") == "text":
                        parts.append({"text": part["text"]})
                if parts:
                    contents.append({"role": gemini_role, "parts": parts})
        return contents

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AgenticResponse:
        """
        Send a chat-style request to Gemini.

        Args:
            messages: [{role: "user"|"assistant", content: str}, ...]
            model: Override model (defaults to config.model)
            temperature: Override temperature
            max_tokens: Override max output tokens
            tools: Function tools (Gemini uses 'tools' not 'functions')
        """
        model = model or self.model
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens or self.config.max_tokens

        # Build payload
        contents = self._messages_to_gemini(messages)

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temp,
                "maxOutputTokens": tokens,
                "topP": kwargs.get("top_p", 0.95),
                "topK": kwargs.get("top_k", 40),
            },
        }

        # Add tools if provided (Gemini native tool use)
        if tools:
            # Convert OpenAI-style functions to Gemini tools format
            gemini_tools = []
            for tool in tools:
                func = tool.get("function", {})
                gemini_tools.append({
                    "functionDeclarations": [
                        {
                            "name": func.get("name"),
                            "description": func.get("description", ""),
                            "parameters": func.get("parameters", {}),
                        }
                    ]
                })
            payload["tools"] = gemini_tools

        # Add safety settings if provided
        if "safety_settings" in kwargs:
            payload["safetySettings"] = kwargs["safety_settings"]

        try:
            data = self._make_request(payload)

            # Extract response
            candidate = data.get("candidates", [{}])[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

            # Count token usage
            usage = data.get("usageMetadata", {})
            tokens_used = (
                usage.get("promptTokenCount", 0)
                + usage.get("candidatesTokenCount", 0)
            )

            finish_reason = candidate.get("finishReason", "STOP")

            return AgenticResponse(
                content=text,
                raw=data,
                model=model,
                tokens_used=tokens_used,
                finish_reason=finish_reason,
                metadata={"prompt_tokens": usage.get("promptTokenCount", 0),
                           "completion_tokens": usage.get("candidatesTokenCount", 0)},
            )

        except Exception as e:
            logger.error(f"Gemini chat failed: {e}")
            raise

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AgenticResponse:
        """Single-shot completion (converted to chat format)."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def list_models(self) -> List[Dict[str, Any]]:
        """List available Gemini models."""
        import urllib.request

        url = f"{self.config.base_url}/models?key={self.config.api_key}"
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        models = data.get("models", [])
        logger.info(f"Found {len(models)} Gemini models")
        return cast(List[Dict[str, Any]], models)


class GeminiOpenAIProxy:
    """
    Wraps Gemini as an OpenAI-compatible endpoint.
    Use this to make Gemini drop-in compatible with OpenAI-compatible LLM code.

    Endpoint: https://api.myclaw.ai/v1/chat/completions
    (Routes Gemini through OpenClaw's MyClaw gateway)
    """

    def __init__(
        self,
        base_url: str = "https://api.myclaw.ai/v1",
        api_key: Optional[str] = None,
        model: str = "gemini-3-flash",
        timeout: int = 120,
    ):
        import urllib.request

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("MYCLAW_API_KEY", "openclaw")
        self.default_model = model
        self.timeout = timeout
        self._urllib = urllib.request

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AgenticResponse:
        """Send chat to MyClaw gateway (which routes to Gemini)."""
        import urllib.parse
        import urllib.request

        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

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

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())

            choice = data["choices"][0]
            return AgenticResponse(
                content=choice["message"]["content"] or "",
                raw=data,
                model=data.get("model", model),
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={},
            )
        except Exception as e:
            logger.error(f"MyClaw gateway call failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs: Any) -> AgenticResponse:
        return self.chat(messages=[{"role": "user", "content": prompt}], **kwargs)
