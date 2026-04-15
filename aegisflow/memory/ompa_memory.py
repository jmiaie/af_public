"""
AegisFlow OMPA Memory — wraps OMPA v0.3+ for AegisFlow.

GBrain = knowledge base (people/companies/lookups — always authoritative)
OMPA  = session memory + classification + semantic search layer
AegisFlow bridges both into a unified memory system.

Usage:
    from aegisflow.memory import AegisFlowMemory
    mem = AegisFlowMemory(vault_path="/path/to/workspace")
    result = mem.session_start()
    # Brain-first: check GBrain first, then OMPA semantic for context
    hint = mem.get_routing_hint("let's try a new database")
    mem.post_tool("write", {"file_path": "work/active/deploy.md"})
    mem.stop()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aegisflow.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)


class AegisFlowMemory:
    """
    AegisFlow's unified memory layer — bridges GBrain and OMPA.

    Architecture:
    - GBrain pages  → authoritative knowledge base (people/companies/concepts)
    - OMPA vault    → session context, working notes, episodic memory
    - OMPA KG       → temporal triples from vault notes
    - OMPA semantic → embeddings-based search over vault
    - OMPA classif. → 15-type message routing

    BrainFirstLookup order:
      1. GBrain keyword search (if gbrain vault_path provided)
      2. OMPA semantic search
      3. OMPA keyword/vault search
      4. KG query
      5. Not found → external API call

    AegisFlow never calls ompa.session_start() in the main session loop
    (expensive, ~2K tokens). Use standup() once at session open instead.
    """

    def __init__(
        self,
        vault_path: str | Path = "./workspace",
        gbrain_vault_path: str | Path = None,
        enable_semantic: bool = True,
        agent_name: str = "aegisflow",
    ):
        self.vault_path = Path(vault_path)
        self.gbrain_vault_path = Path(gbrain_vault_path) if gbrain_vault_path else None
        self.agent_name = agent_name
        self._enable_semantic = enable_semantic
        self._ompa = None
        self._semantic_memory: Optional[SemanticMemory] = None
        self._gbrain_engine = None
        self._session_started = False

    # -------------------------------------------------------------------------
    # OMPA lazy-access
    # -------------------------------------------------------------------------

    @property
    def ompa(self):
        """Lazy-load OMPA on first access."""
        if self._ompa is None:
            try:
                from ompa import Ompa as _Ompa
            except ImportError:
                logger.warning("OMPA not installed. Run: pip install ompa")
                return None

            self._ompa = _Ompa(
                vault_path=str(self.vault_path),
                agent_name=self.agent_name,
                enable_semantic=self._enable_semantic,
            )
        return self._ompa

    @property
    def semantic_memory(self) -> Optional[SemanticMemory]:
        """AegisFlow's native SemanticMemory as fallback when OMPA unavailable."""
        if self._semantic_memory is None:
            self._semantic_memory = SemanticMemory(
                index_path=str(self.vault_path / ".semantic_index.json")
            )
        return self._semantic_memory

    # -------------------------------------------------------------------------
    # Lifecycle — match OMPA's hook interface
    # -------------------------------------------------------------------------

    def session_start(self):
        """Run session start: populate KG, build semantic index."""
        if self.ompa is None:
            return {"success": False, "error": "OMPA not available"}
        result = self.ompa.session_start()
        self._session_started = True
        return result

    def standup(self):
        """Alias for session_start()."""
        return self.session_start()

    def handle_message(self, message: str):
        """Classify message and return routing hints."""
        if self.ompa is None:
            return {"success": False, "error": "OMPA not available"}
        return self.ompa.handle_message(message)

    def post_tool(self, tool_name: str, tool_input: dict):
        """Run post-tool hook: validate writes, update KG + index."""
        if self.ompa is None:
            return {"success": False, "error": "OMPA not available"}
        return self.ompa.post_tool(tool_name, tool_input)

    def stop(self):
        """Run stop hook."""
        if self.ompa is None:
            return {"success": False, "error": "OMPA not available"}
        result = self.ompa.stop()
        self._session_started = False
        return result

    def wrap_up(self):
        """Alias for stop()."""
        return self.stop()

    # -------------------------------------------------------------------------
    # Routing
    # -------------------------------------------------------------------------

    def classify(self, message: str):
        """Classify a user message. Returns OMPA Classification."""
        if self.ompa is None:
            return None
        return self.ompa.classify(message)

    def get_routing_hint(self, message: str) -> str:
        """Get routing hint for a message."""
        if self.ompa is None:
            return "ompa_unavailable"
        return self.ompa.get_routing_hint(message)

    # -------------------------------------------------------------------------
    # Brain-First Lookup — GBrain → OMPA semantic → KG → not-found
    # -------------------------------------------------------------------------

    def brain_first(self, entity_name: str) -> dict:
        """
        Mandatory 5-step lookup before ANY external API call.

        Steps:
          1. GBrain keyword page search
          2. OMPA semantic hybrid search
          3. OMPA vault slug lookup
          4. KG entity query + backlinks
          5. Not found → external API

        Returns dict with keys: found, page_content, slug, context_summary,
                                backlinks, timeline, routing_hint
        """
        from aegisflow.brain.lookup import BrainFirstLookup

        lookup = BrainFirstLookup(
            memory_vault=self,
            semantic_memory=None,  # OMPA semantic handles this
            gbrain_vault_path=self.gbrain_vault_path,
        )
        return lookup.run(entity_name)

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search(self, query: str, limit: int = 5, hybrid: bool = True):
        """Search vault semantically via OMPA."""
        if self.ompa is None:
            # Fallback to native SemanticMemory
            return self.semantic_memory.retrieve(query, top_k=limit)
        return self.ompa.search(query, limit=limit, hybrid=hybrid)

    def qsearch(self, query: str, limit: int = 5):
        """QMD-style semantic search."""
        return self.search(query, limit=limit, hybrid=True)

    # -------------------------------------------------------------------------
    # KG shortcuts
    # -------------------------------------------------------------------------

    def kg_add(self, subject: str, predicate: str, obj: str, valid_from: str = None):
        """Add a triple to the knowledge graph."""
        if self.ompa is None:
            return
        self.ompa.kg_add(subject, predicate, obj, valid_from=valid_from)

    def kg_query(self, entity: str):
        """Query KG for an entity."""
        if self.ompa is None:
            return []
        return self.ompa.kg_query(entity)

    # -------------------------------------------------------------------------
    # Vault management
    # -------------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get vault statistics."""
        if self.ompa is None:
            return {}
        return self.ompa.get_stats()

    def update_brain(self, note_name: str, content: str, append: bool = False):
        """Update a brain note."""
        if self.ompa is None:
            return
        self.ompa.update_brain(note_name, content, append=append)

    def rebuild_index(self) -> int:
        """Rebuild semantic index."""
        if self.ompa is None:
            return 0
        return self.ompa.rebuild_index()

    def sync(self) -> dict:
        """Full sync: KG + palace + search index."""
        if self.ompa is None:
            return {}
        return self.ompa.sync()
