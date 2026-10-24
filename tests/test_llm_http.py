"""
Tests for the LLM HTTP layer: the URL-scheme guard and every provider's
request/response handling, with ``urllib.request.urlopen`` mocked (no network).
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

import pytest

from aegisflow.core.errors import (
    AegisFlowLLMError,
    LLMAuthError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from aegisflow.llm.adapters import AgenticLLM, OpenAICompatibleLLM
from aegisflow.llm.gemini import GeminiConfig, GeminiLLM, GeminiOpenAIProxy
from aegisflow.llm.http import require_http_url
from aegisflow.llm.nvidia import LocalNVIDIABridge, NVIDIAllm
from aegisflow.llm.ollama import OllamaLLM, OllamaOpenAIProxy

# ── helpers ──────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: Any, status: int = 200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


@pytest.fixture
def fake_urlopen(monkeypatch):
    """Replace urlopen; records each request and returns the queued payload."""
    calls: List[Dict[str, Any]] = []
    state: Dict[str, Any] = {"payload": {}, "status": 200, "error": None}

    def _fake(req, timeout=None):
        body = json.loads(req.data) if getattr(req, "data", None) else None
        calls.append({"url": req.full_url, "body": body, "timeout": timeout, "req": req})
        if state["error"] is not None:
            raise state["error"]
        return _FakeResponse(state["payload"], state["status"])

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    state["calls"] = calls
    return state


def _openai_payload(content: str = "hi", model: str = "m") -> Dict[str, Any]:
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 7},
    }


def _http_error(code: int, headers: Dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://x", code, "err", headers or {}, io.BytesIO(b"error body")  # type: ignore[arg-type]
    )


# ── require_http_url ─────────────────────────────────────────────────────────


class TestRequireHttpUrl:
    @pytest.mark.parametrize("url", ["http://localhost:11434/api", "https://a.b/v1", "HTTPS://X"])
    def test_accepts_http_and_https(self, url):
        assert require_http_url(url) == url

    def test_accepts_request_object(self):
        req = urllib.request.Request("https://example.invalid/x")
        assert require_http_url(req) == "https://example.invalid/x"

    @pytest.mark.parametrize(
        "url",
        ["file:///etc/passwd", "ftp://host/x", "data:text/plain,hi", "gopher://h", "/no/scheme"],
    )
    def test_rejects_other_schemes(self, url):
        with pytest.raises(ValueError, match="only http and https"):
            require_http_url(url)

    def test_error_does_not_leak_url(self):
        with pytest.raises(ValueError) as exc:
            require_http_url("file:///secret?key=APIKEY123")
        assert "APIKEY123" not in str(exc.value)
        assert "'file'" in str(exc.value)

    def test_rejected_url_never_reaches_urlopen(self, fake_urlopen):
        llm = NVIDIAllm(api_key="k", base_url="file:///etc")
        with pytest.raises(ValueError):
            llm.chat([{"role": "user", "content": "x"}])
        assert fake_urlopen["calls"] == []


# ── OpenAICompatibleLLM ──────────────────────────────────────────────────────


class TestOpenAICompatibleLLM:
    def test_chat_success(self, fake_urlopen):
        fake_urlopen["payload"] = _openai_payload("hello", "gpt-x")
        llm = OpenAICompatibleLLM(base_url="http://h/v1/", api_key="k", default_model="d")
        r = llm.chat([{"role": "user", "content": "q"}], tools=[{"type": "function"}], seed=1)
        call = fake_urlopen["calls"][0]
        assert call["url"] == "http://h/v1/chat/completions"
        assert call["body"]["tools"] == [{"type": "function"}]
        assert call["body"]["seed"] == 1
        assert call["req"].get_header("Authorization") == "Bearer k"
        assert r.content == "hello" and r.model == "gpt-x" and r.tokens_used == 7

    def test_complete(self, fake_urlopen):
        fake_urlopen["payload"] = _openai_payload("done")
        r = OpenAICompatibleLLM(base_url="https://h").complete("p")
        assert r.content == "done"
        assert fake_urlopen["calls"][0]["body"]["messages"] == [{"role": "user", "content": "p"}]

    def test_rejects_file_scheme(self, fake_urlopen):
        with pytest.raises(ValueError):
            OpenAICompatibleLLM(base_url="file:///tmp").complete("p")
        assert fake_urlopen["calls"] == []

    @pytest.mark.parametrize(
        "code,exc",
        [
            (401, LLMAuthError),
            (403, LLMAuthError),
            (429, LLMRateLimitError),
            (503, LLMProviderError),
            (404, AegisFlowLLMError),
        ],
    )
    def test_http_errors_map_to_typed_errors(self, fake_urlopen, code, exc):
        fake_urlopen["error"] = _http_error(code, {"Retry-After": "3"})
        with pytest.raises(exc) as info:
            OpenAICompatibleLLM(base_url="http://h").complete("p")
        if code == 429:
            assert info.value.retry_after == 3.0

    def test_timeout(self, fake_urlopen):
        fake_urlopen["error"] = urllib.error.URLError("timed out")
        with pytest.raises(LLMTimeoutError):
            OpenAICompatibleLLM(base_url="http://h").complete("p")

    def test_url_error(self, fake_urlopen):
        fake_urlopen["error"] = urllib.error.URLError("connection refused")
        with pytest.raises(AegisFlowLLMError):
            OpenAICompatibleLLM(base_url="http://h").complete("p")

    def test_malformed_response(self, fake_urlopen):
        fake_urlopen["payload"] = {"nope": True}
        with pytest.raises(AegisFlowLLMError):
            OpenAICompatibleLLM(base_url="http://h").complete("p")

    def test_agentic_llm_openai_backend(self, fake_urlopen):
        fake_urlopen["payload"] = _openai_payload("via wrapper")
        llm = AgenticLLM(backend="openai", config={"base_url": "http://h"})
        assert llm.complete("p").content == "via wrapper"
        assert llm.chat([{"role": "user", "content": "p"}]).content == "via wrapper"


# ── Gemini ───────────────────────────────────────────────────────────────────


_GEMINI_PAYLOAD = {
    "candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
}


class TestGemini:
    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-x")
        monkeypatch.setenv("GEMINI_TIMEOUT", "9")
        cfg = GeminiConfig.from_env()
        assert (cfg.api_key, cfg.model, cfg.timeout) == ("env-key", "gemini-x", 9)

    def test_kwargs_build_config(self):
        llm = GeminiLLM(api_key="k", model="m")
        assert llm.config.api_key == "k" and llm.model == "m"

    def test_messages_to_gemini(self):
        llm = GeminiLLM(GeminiConfig(api_key="k"))
        out = llm._messages_to_gemini(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": [{"type": "text", "text": "t"}, {"type": "image"}]},
                {"role": "user", "content": [{"type": "image"}]},
            ]
        )
        assert out == [
            {"role": "user", "parts": [{"text": "q"}]},
            {"role": "model", "parts": [{"text": "a"}]},
            {"role": "user", "parts": [{"text": "t"}]},
        ]

    def test_chat_success_with_tools(self, fake_urlopen):
        fake_urlopen["payload"] = _GEMINI_PAYLOAD
        llm = GeminiLLM(GeminiConfig(api_key="KEY", model="models/x", base_url="https://g/v1"))
        tool = {"function": {"name": "f", "description": "d", "parameters": {"type": "object"}}}
        r = llm.chat(
            [{"role": "user", "content": "q"}],
            tools=[tool],
            temperature=0.1,
            max_tokens=5,
            safety_settings=[{"category": "c"}],
        )
        call = fake_urlopen["calls"][0]
        assert call["url"] == "https://g/v1/models/models%2Fx:generateContent?key=KEY"
        assert call["body"]["generationConfig"]["temperature"] == 0.1
        assert call["body"]["generationConfig"]["maxOutputTokens"] == 5
        assert call["body"]["tools"][0]["functionDeclarations"][0]["name"] == "f"
        assert call["body"]["safetySettings"] == [{"category": "c"}]
        assert r.content == "ab" and r.tokens_used == 7
        assert r.metadata == {"prompt_tokens": 3, "completion_tokens": 4}

    def test_complete(self, fake_urlopen):
        fake_urlopen["payload"] = _GEMINI_PAYLOAD
        r = GeminiLLM(GeminiConfig(api_key="k")).complete("p")
        assert r.content == "ab"

    def test_http_error(self, fake_urlopen):
        fake_urlopen["error"] = _http_error(400)
        with pytest.raises(Exception, match="Gemini API error 400"):
            GeminiLLM(GeminiConfig(api_key="k")).complete("p")

    def test_other_error_reraised(self, fake_urlopen):
        fake_urlopen["error"] = OSError("boom")
        with pytest.raises(OSError):
            GeminiLLM(GeminiConfig(api_key="k")).complete("p")

    def test_rejects_file_scheme(self, fake_urlopen):
        llm = GeminiLLM(GeminiConfig(api_key="k", base_url="file:///etc"))
        with pytest.raises(ValueError):
            llm.complete("p")
        with pytest.raises(ValueError):
            llm.list_models()
        assert fake_urlopen["calls"] == []

    def test_list_models(self, fake_urlopen):
        fake_urlopen["payload"] = {"models": [{"name": "a"}, {"name": "b"}]}
        models = GeminiLLM(GeminiConfig(api_key="k", base_url="https://g")).list_models()
        assert [m["name"] for m in models] == ["a", "b"]
        assert fake_urlopen["calls"][0]["url"] == "https://g/models?key=k"

    def test_openai_proxy(self, fake_urlopen):
        fake_urlopen["payload"] = _openai_payload("proxied")
        proxy = GeminiOpenAIProxy(base_url="https://p/v1/", api_key="k")
        r = proxy.complete("p", tools=[{"t": 1}])
        call = fake_urlopen["calls"][0]
        assert call["url"] == "https://p/v1/chat/completions"
        assert call["body"]["tools"] == [{"t": 1}]
        assert r.content == "proxied" and r.tokens_used == 7

    def test_openai_proxy_error(self, fake_urlopen):
        fake_urlopen["error"] = OSError("down")
        with pytest.raises(OSError):
            GeminiOpenAIProxy(base_url="https://p").complete("p")


# ── NVIDIA ───────────────────────────────────────────────────────────────────


class TestNVIDIA:
    @pytest.mark.parametrize("cls", [NVIDIAllm, LocalNVIDIABridge])
    def test_chat_success(self, fake_urlopen, cls):
        fake_urlopen["payload"] = _openai_payload("nv", "nv-model")
        llm = cls(api_key="k") if cls is NVIDIAllm else cls(auth_token="t")
        r = llm.complete("p", tools=[{"t": 1}], extra=2)
        call = fake_urlopen["calls"][0]
        assert call["url"].endswith("/chat/completions")
        assert call["body"]["tools"] == [{"t": 1}] and call["body"]["extra"] == 2
        assert r.content == "nv" and r.model == "nv-model" and r.tokens_used == 7

    def test_local_bridge_url(self, fake_urlopen):
        fake_urlopen["payload"] = _openai_payload()
        LocalNVIDIABridge(gateway_url="http://gw:1/").complete("p")
        assert fake_urlopen["calls"][0]["url"] == "http://gw:1/v1/chat/completions"

    @pytest.mark.parametrize("cls", [NVIDIAllm, LocalNVIDIABridge])
    def test_errors_reraised(self, fake_urlopen, cls):
        fake_urlopen["error"] = OSError("down")
        with pytest.raises(OSError):
            cls().complete("p")

    def test_bridge_rejects_file_scheme(self, fake_urlopen):
        with pytest.raises(ValueError):
            LocalNVIDIABridge(gateway_url="file://gw").complete("p")
        assert fake_urlopen["calls"] == []


# ── Ollama ───────────────────────────────────────────────────────────────────


class TestOllama:
    def test_chat_success(self, fake_urlopen):
        fake_urlopen["payload"] = {
            "message": {"content": "llama"},
            "eval_count": 5,
            "prompt_count": 2,
        }
        llm = OllamaLLM(base_url="http://o:11434/", model="tiny")
        r = llm.complete("p", top_k=3)
        call = fake_urlopen["calls"][0]
        assert call["url"] == "http://o:11434/api/chat"
        assert call["body"]["options"]["top_k"] == 3
        assert call["body"]["options"]["num_predict"] == 512
        assert r.content == "llama" and r.tokens_used == 7
        assert r.metadata["completion_tokens"] == 5

    def test_chat_error_reraised(self, fake_urlopen):
        fake_urlopen["error"] = OSError("down")
        with pytest.raises(OSError):
            OllamaLLM().chat([{"role": "user", "content": "x"}])

    def test_list_models(self, fake_urlopen):
        fake_urlopen["payload"] = {"models": [{"name": "tiny"}]}
        assert OllamaLLM().list_models() == [{"name": "tiny"}]
        assert fake_urlopen["calls"][0]["url"] == "http://localhost:11434/api/tags"

    def test_list_models_error_returns_empty(self, fake_urlopen):
        fake_urlopen["error"] = OSError("down")
        assert OllamaLLM().list_models() == []

    def test_is_available(self, fake_urlopen):
        assert OllamaLLM().is_available() is True
        fake_urlopen["status"] = 500
        assert OllamaLLM().is_available() is False
        fake_urlopen["error"] = OSError("down")
        assert OllamaLLM().is_available() is False

    def test_file_scheme_rejected_everywhere(self, fake_urlopen):
        llm = OllamaLLM(base_url="file:///srv")
        with pytest.raises(ValueError):
            llm.complete("p")
        assert llm.list_models() == []
        assert llm.is_available() is False
        assert fake_urlopen["calls"] == []

    def test_openai_proxy(self, fake_urlopen):
        fake_urlopen["payload"] = _openai_payload("prox")
        proxy = OllamaOpenAIProxy(model="tiny")
        assert proxy.chat([{"role": "user", "content": "x"}]).content == "prox"
        assert fake_urlopen["calls"][0]["body"]["model"] == "tiny"
        assert proxy.complete("p").content == "prox"
        assert fake_urlopen["calls"][0]["url"] == "http://localhost:11434/v1/chat/completions"
