"""
AegisFlow Core — protocols and error taxonomy.
"""

from aegisflow.core.errors import (
    AegisFlowError,
    AegisFlowLLMError,
    AegisFlowMemoryError,
    AegisFlowOrchestrationError,
    AegisFlowSandboxError,
    DecompositionError,
    KGQueryError,
    LLMAuthError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    SandboxPermissionError,
    SandboxTimeoutError,
    SandboxUnavailableError,
    SynthesisError,
    VaultCorruptionError,
)
from aegisflow.core.protocols import (
    LLMProvider,
    MemoryProvider,
    SandboxProvider,
    StreamingLLMProvider,
    Tool,
)

__all__ = [
    # Errors
    "AegisFlowError",
    "AegisFlowLLMError",
    "LLMTimeoutError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMProviderError",
    "AegisFlowSandboxError",
    "SandboxPermissionError",
    "SandboxTimeoutError",
    "SandboxUnavailableError",
    "AegisFlowMemoryError",
    "VaultCorruptionError",
    "KGQueryError",
    "AegisFlowOrchestrationError",
    "DecompositionError",
    "SynthesisError",
    # Protocols
    "LLMProvider",
    "StreamingLLMProvider",
    "SandboxProvider",
    "MemoryProvider",
    "Tool",
]
