"""
AegisFlow LLM Adapters — NVIDIA NIM Provider.

Provides integration with NVIDIA NIM endpoints (nvidia/**/*.nvidia.com)
and the OpenClaw NVIDIA plugin which routes to NVIDIA's hosted models.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional

from aegisflow.llm.adapters import AgenticResponse

logger = logging.getLogger(__name__)


class NVIDIAllm:
    """
    NVIDIA NIM (NVIDIA Inference Microservice) client.
    Works with hosted NVIDIA models via api.nvidia.com.

    Also supports OpenClaw's NVIDIA plugin routing via the local gateway.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/llama-3.1-nemotron-70b-instruct",
        timeout: int = 120,
    ):
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self.timeout = timeout

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> AgenticResponse:
        """Send chat request to NVIDIA NIM endpoint."""
        import urllib.request

        model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
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
            logger.error(f"NVIDIA NIM call failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs) -> AgenticResponse:
        return self.chat(messages=[{"role": "user", "content": prompt}], **kwargs)


class LocalNVIDIABridge:
    """
    Routes NVIDIA LLM calls through the OpenClaw NVIDIA plugin
    running on the local gateway. No API key needed — uses the
    plugin's built-in routing.

    This is the preferred path when running AegisFlow on a node
    that has the OpenClaw NVIDIA plugin enabled.
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:18789",
        auth_token: Optional[str] = None,
        model: str = "nvidia/meta/llama-3.1-70b-instruct",
        timeout: int = 180,
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.auth_token = auth_token or os.environ.get("OPENCLAW_AUTH_TOKEN", "")
        self.default_model = model
        self.timeout = timeout

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> AgenticResponse:
        """Route through OpenClaw gateway's NVIDIA plugin."""
        import urllib.request

        model = model or self.default_model
        url = f"{self.gateway_url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
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
            logger.error(f"Local NVIDIA bridge failed: {e}")
            raise

    def complete(self, prompt: str, **kwargs) -> AgenticResponse:
        return self.chat(messages=[{"role": "user", "content": prompt}], **kwargs)