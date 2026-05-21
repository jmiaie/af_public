"""
AegisFlow Core — protocols and error taxonomy.
"""

from aegisflow.core.errors import (
    AegisFlowError,
    AegisFlowLLMError,
    LLMTimeoutError,
    LLMAuthError,
    LLMRateLimitError,
    LLMProviderError,
    AegisFlowSandboxError,
    SandboxPermissionError,
    SandboxTimeoutError,
    SandboxUnavailableError,
    AegisFlowMemoryError,
    VaultCorruptionError,
    KGQueryError,
    AegisFlowOrchestrationError,
    DecompositionError,
    SynthesisError,
)
from aegisflow.core.protocols import (
    LLMProvider,
    StreamingLLMProvider,
    SandboxProvider,
    MemoryProvider,
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
