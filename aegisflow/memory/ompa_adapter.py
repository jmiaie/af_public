"""
AegisFlow Universal Memory Layer.

This module provides an agnostic interface to OMPA-like memory structures,
ensuring that agents can maintain persistent context across sessions.
"""

import os
from typing import Any, Dict, List, Optional


class MemoryVault:
    """
    A persistent, human-navigable memory vault.
    Stores episodic and semantic memory in an organized markdown structure.
    """

    def __init__(self, path: str = "./vault"):
        self.path = path
        # Perf §5.1: cache directories we've already ensured to skip repeat
        # makedirs syscalls on the write hot path.
        self._known_dirs: set[str] = set()
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        """Ensure the basic vault structure exists."""
        folders = ["brain", "work", "org", "perf"]
        for folder in folders:
            d = os.path.join(self.path, folder)
            os.makedirs(d, exist_ok=True)
            self._known_dirs.add(d)

    def store_verbatim(self, content: str, category: str = "work", filename: str = "notes.md") -> None:
        """Stores unsummarized, verbatim context into the vault."""
        # Perf §5.1: only call makedirs when the target dir is new to this instance.
        cat_path = os.path.join(self.path, category)
        if cat_path not in self._known_dirs:
            os.makedirs(cat_path, exist_ok=True)
            self._known_dirs.add(cat_path)
        filepath = os.path.join(cat_path, filename)
        # Perf §5.2: "a" mode creates the file if missing — no need to stat first.
        with open(filepath, "a") as f:
            f.write(f"\n---\n{content}\n")

    def retrieve(self, query: str) -> List[str]:
        """Placeholder for semantic search across the vault."""
        return [f"Mock retrieval result for: {query}"]


class KnowledgeGraph:
    """
    Temporal Knowledge Graph for tracking entity relationships over time.
    """

    def __init__(self, db_path: str = "./vault/kg.sqlite"):
        self.db_path = db_path
        self.triples: List[Dict[str, str]] = []
        # Perf §5.3: dict indices turn query_entity from O(n) to O(1 + k).
        self._by_subject: Dict[str, List[Dict[str, str]]] = {}
        self._by_object: Dict[str, List[Dict[str, str]]] = {}

    def add_triple(self, subject: str, predicate: str, object_val: str,
                   valid_from: Optional[str] = None) -> None:
        """Add a temporal fact to the graph."""
        triple = {
            "subject": subject,
            "predicate": predicate,
            "object": object_val,
            "valid_from": valid_from or "now",
        }
        self.triples.append(triple)
        self._by_subject.setdefault(subject, []).append(triple)
        self._by_object.setdefault(object_val, []).append(triple)

    def query_entity(self, entity: str) -> List[Dict[str, str]]:
        """Query the graph for relationships involving an entity.

        Returns triples where `entity` is either the subject or the object.
        Deduplicates the case where subject == object.
        """
        subj_hits = self._by_subject.get(entity, [])
        obj_hits = self._by_object.get(entity, [])
        if not obj_hits:
            return list(subj_hits)
        if not subj_hits:
            return list(obj_hits)
        # Merge and deduplicate (preserves insertion order).
        seen_ids = {id(t) for t in subj_hits}
        return subj_hits + [t for t in obj_hits if id(t) not in seen_ids]


class PalaceNavigation:
    """
    Agent-accessible spatial navigation system (Wings -> Rooms -> Drawers).
    """

    def __init__(self, vault: MemoryVault):
        self.vault = vault
        self.wings: Dict[str, Any] = {}

    def create_wing(self, name: str, wing_type: str) -> None:
        self.wings[name] = {"type": wing_type, "rooms": {}}

    def get_context(self) -> str:
        """Returns the structural context for the agent to navigate."""
        return f"Palace has {len(self.wings)} wings available for navigation."
