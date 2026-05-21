"""
AegisFlow LLM Layer.

Providers:
- OpenAICompatibleLLM: Any OpenAI-API-compatible endpoint
- GeminiLLM / GeminiOpenAIProxy: Google Gemini (direct REST or via MyClaw)
- OllamaLLM / OllamaOpenAIProxy: Local Ollama (free, no API key)
- NVIDIA NIM / LocalNVIDIABridge: NVIDIA hosted models
- OpenClawSession: Real OpenClaw sub-agent sessions
"""

from aegisflow.llm.adapters import (
    AgenticLLM,
    AgenticResponse,
    OpenAICompatibleLLM,
    OpenClawSession,
    SubAgentResult,
)
from aegisflow.llm.gemini import (
    GeminiConfig,
    GeminiLLM,
    GeminiOpenAIProxy,
)
from aegisflow.llm.nvidia import (
    LocalNVIDIABridge,
    NVIDIAllm,
)
from aegisflow.llm.ollama import (
    OllamaLLM,
    OllamaOpenAIProxy,
)

__all__ = [
    # Core
    "AgenticLLM",
    "AgenticResponse",
    "OpenAICompatibleLLM",
    "OpenClawSession",
    "SubAgentResult",
    # Gemini
    "GeminiLLM",
    "GeminiConfig",
    "GeminiOpenAIProxy",
    # Ollama
    "OllamaLLM",
    "OllamaOpenAIProxy",
    # NVIDIA
    "NVIDIAllm",
    "LocalNVIDIABridge",
]
