"""
AegisFlow Memory Layer.

Exports:
- AegisFlowMemory: unified memory bridge (GBrain + OMPA wired together)
- MemoryVault: backward-compatible alias for AegisFlow vault wrapper
- KnowledgeGraph: backward-compatible alias for OMPA KG
- SemanticMemory: AegisFlow's native semantic search (fallback when OMPA unavailable)

Architecture:
  GBrain     → authoritative knowledge base (people/companies/concepts)
  OMPA       → session memory + classification + KG + semantic layer
  SemanticMemory → native AegisFlow embeddings (fallback only)
"""

from aegisflow.memory.ompa_memory import AegisFlowMemory
from aegisflow.memory.ompa_adapter import MemoryVault, KnowledgeGraph, PalaceNavigation
from aegisflow.memory.semantic import SemanticMemory

__all__ = [
    "AegisFlowMemory",  # primary interface — wires GBrain + OMPA
    "MemoryVault",      # backward compat
    "KnowledgeGraph",  # backward compat
    "PalaceNavigation", # backward compat
    "SemanticMemory",   # native semantic fallback
]
