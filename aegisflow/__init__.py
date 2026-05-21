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

from aegisflow.orchestration.swarm import LeadOrchestrator, SubAgent
from aegisflow.memory import MemoryVault, KnowledgeGraph, PalaceNavigation
from aegisflow.sandbox.environment import LocalSandbox, DockerSandbox, Sandbox as SandboxAlias
from aegisflow.llm import (
    OpenAICompatibleLLM,
    OpenClawSession,
    AgenticLLM,
    AgenticResponse,
    SubAgentResult,
)
from aegisflow.analytics import (
    ToolCategory,
    categorize_tool,
    SessionAnalyzer,
    render_analytics_summary,
)
from aegisflow.brain import (
    BrainFirstLookup,
    BrainLookupResult,
    brain_first,
    SignalDetector,
    SignalSummary,
    BrainDoctor,
    BrainHealthReport,
    run_doctor,
)
from aegisflow.core import (
    # Protocols
    LLMProvider,
    SandboxProvider,
    MemoryProvider,
    Tool,
    # Errors
    AegisFlowError,
    AegisFlowLLMError,
    AegisFlowSandboxError,
    AegisFlowMemoryError,
    AegisFlowOrchestrationError,
)

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