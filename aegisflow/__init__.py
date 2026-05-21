"""
AegisFlow — Universal, Security-First Multi-Agent Hybrid System.

Core exports:
- Orchestration: LeadOrchestrator, SubAgent, AgenticLLM
- Memory: MemoryVault, KnowledgeGraph, PalaceNavigation
- Sandbox: LocalSandbox, DockerSandbox, SandboxResult
- LLM: OpenAICompatibleLLM, OpenClawSession, AgenticResponse, SubAgentResult
- Core: Protocols (LLMProvider, SandboxProvider, MemoryProvider, Tool)
- Core: Errors (AegisFlowError hierarchy)
"""

from aegisflow.analytics import (
    SessionAnalyzer,
    ToolCategory,
    categorize_tool,
    render_analytics_summary,
)
from aegisflow.brain import (
    BrainDoctor,
    BrainFirstLookup,
    BrainHealthReport,
    BrainLookupResult,
    SignalDetector,
    SignalSummary,
    brain_first,
    run_doctor,
)
from aegisflow.core import (
    # Errors
    AegisFlowError,
    AegisFlowLLMError,
    AegisFlowMemoryError,
    AegisFlowOrchestrationError,
    AegisFlowSandboxError,
    # Protocols
    LLMProvider,
    MemoryProvider,
    SandboxProvider,
    Tool,
)
from aegisflow.llm import (
    AgenticLLM,
    AgenticResponse,
    OpenAICompatibleLLM,
    OpenClawSession,
    SubAgentResult,
)
from aegisflow.memory import KnowledgeGraph, MemoryVault, PalaceNavigation
from aegisflow.orchestration.swarm import LeadOrchestrator, SubAgent
from aegisflow.sandbox.environment import DockerSandbox, LocalSandbox
from aegisflow.sandbox.environment import Sandbox as SandboxAlias

__version__ = "0.3.0"

__all__ = [
    # Orchestration
    "LeadOrchestrator",
    "SubAgent",
    "AgenticLLM",
    # Memory
    "MemoryVault",
    "KnowledgeGraph",
    "PalaceNavigation",
    # Sandbox
    "LocalSandbox",
    "DockerSandbox",
    "SandboxAlias",
    # LLM
    "OpenAICompatibleLLM",
    "OpenClawSession",
    "AgenticResponse",
    "SubAgentResult",
    # Analytics
    "ToolCategory",
    "categorize_tool",
    "SessionAnalyzer",
    "render_analytics_summary",
    # Brain (GBrain port)
    "BrainFirstLookup",
    "BrainLookupResult",
    "brain_first",
    "SignalDetector",
    "SignalSummary",
    "BrainDoctor",
    "BrainHealthReport",
    "run_doctor",
    # Protocols
    "LLMProvider",
    "SandboxProvider",
    "MemoryProvider",
    "Tool",
    # Errors
    "AegisFlowError",
    "AegisFlowLLMError",
    "AegisFlowSandboxError",
    "AegisFlowMemoryError",
    "AegisFlowOrchestrationError",
]
