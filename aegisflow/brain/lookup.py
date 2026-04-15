"""
Brain-First Lookup Protocol — wired to GBrain (knowledge base) + OMPA (memory layer).

The 5-step lookup that MUST run before ANY external API call:
web search, enrichment service, social lookup, etc.

The brain almost always has something. External APIs fill gaps, not start from scratch.

Authority order:
  1. GBrain keyword page search   → authoritative knowledge base
  2. OMPA semantic hybrid search  → session/working memory
  3. OMPA vault slug lookup       → episodic context
  4. KG entity query              → temporal relationships
  5. Not found                    → call external API
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from aegisflow.memory.ompa_memory import AegisFlowMemory

logger = logging.getLogger(__name__)


@dataclass
class BrainLookupResult:
    found: bool
    page_content: Optional[str] = None
    slug: Optional[str] = None
    source: str = "none"  # gbrain | ompa_semantic | ompa_vault | kg | none
    backlinks: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    context_summary: Optional[str] = None


class BrainFirstLookup:
    """
    The mandatory 5-step lookup protocol.

    GBrain is the authoritative knowledge base (people/companies/concepts).
    OMPA is the session/working memory layer.
    BrainFirstLookup chains them in order of authority.

    Usage:
        lookup = BrainFirstLookup(memory=mem, gbrain_vault_path="/path/to/gbrain")
        result = lookup.run("Jordan Chen")
        if result.found:
            print(f"[{result.source}] {result.page_content[:200]}")
        else:
            # Only NOW call external API
            data = web_search("Jordan Chen")
    """

    def __init__(
        self,
        memory: "AegisFlowMemory" = None,
        gbrain_vault_path: str | Path = None,
        semantic_memory=None,  # deprecated, use memory.ompa.semantic
    ):
        """
        Args:
            memory: AegisFlowMemory instance (provides OMPA + semantic access)
            gbrain_vault_path: Path to GBrain vault (people/companies/concepts folders)
            semantic_memory: Deprecated, ignored
        """
        self.memory = memory
        self.gbrain_vault_path = Path(gbrain_vault_path) if gbrain_vault_path else None
        self._gbrain_engine = None

    # -------------------------------------------------------------------------
    # 5-step lookup
    # -------------------------------------------------------------------------

    def run(self, entity_name: str) -> BrainLookupResult:
        """
        Run all 5 steps. Returns as soon as any step finds something.
        """
        slug = self._slugify(entity_name)

        # Step 1: GBrain keyword search (authoritative KB)
        result = self._step1_gbrain_search(entity_name, slug)
        if result.found:
            return result

        # Step 2: OMPA semantic hybrid search (session memory)
        if self.memory:
            result = self._step2_ompa_semantic(entity_name)
            if result.found:
                return result

        # Step 3: OMPA vault slug lookup (episodic context)
        if self.memory:
            result = self._step3_ompa_vault(slug)
            if result.found:
                return result

        # Step 4: KG entity query (temporal relationships)
        if self.memory:
            result = self._step4_kg_query(entity_name)
            if result.found:
                return result

        # Step 5: Not found — external API call required
        return BrainLookupResult(found=False)

    def run_async(self, entity_name: str) -> BrainLookupResult:
        """Sync version — same implementation."""
        return self.run(entity_name)

    # -------------------------------------------------------------------------
    # Step implementations
    # -------------------------------------------------------------------------

    def _step1_gbrain_search(self, name: str, slug: str) -> BrainLookupResult:
        """
        Step 1: Search GBrain vault for the entity.
        GBrain vault structure: people/<slug>.md, companies/<slug>.md, concepts/<slug>.md
        """
        if not self.gbrain_vault_path:
            return BrainLookupResult(found=False)

        # Try standard GBrain folders
        for folder in ["people", "companies", "concepts", "originals", "ideas"]:
            try:
                path = self.gbrain_vault_path / folder / f"{slug}.md"
                if path.exists():
                    content = path.read_text()
                    return BrainLookupResult(
                        found=True,
                        page_content=content,
                        slug=f"{folder}/{slug}",
                        source="gbrain",
                        backlinks=self._gbrain_backlinks(slug),
                        timeline=self._gbrain_timeline(folder, slug),
                        context_summary=self._summarize(content),
                    )
            except Exception as e:
                logger.debug("GBrain lookup failed for %s/%s: %s", folder, slug, e)
                continue

        return BrainLookupResult(found=False)

    def _step2_ompa_semantic(self, query: str) -> BrainLookupResult:
        """Step 2: OMPA semantic hybrid search across vault."""
        try:
            ompa = self.memory.ompa
            if ompa is None:
                return BrainLookupResult(found=False)

            results = ompa.search(f"who is {query}", limit=3, hybrid=True)
            if results:
                content = "\n".join(
                    f"[{r.path}] {r.content_excerpt}" for r in results
                )
                return BrainLookupResult(
                    found=True,
                    page_content=content[:500],
                    source="ompa_semantic",
                    context_summary=f"OMPA semantic: {len(results)} hits",
                    backlinks=[],
                    timeline=[],
                )
        except Exception as e:
            logger.debug("OMPA semantic search failed: %s", e)

        return BrainLookupResult(found=False)

    def _step3_ompa_vault(self, slug: str) -> BrainLookupResult:
        """Step 3: Direct OMPA vault slug lookup."""
        try:
            ompa = self.memory.ompa
            if ompa is None:
                return BrainLookupResult(found=False)

            # Try standard OMPA folders
            for folder in ["brain", "work", "org", "people", "companies"]:
                try:
                    note = ompa.vault.get_brain_note(f"{folder}/{slug}")
                    if note:
                        return BrainLookupResult(
                            found=True,
                            page_content=note.content,
                            slug=f"{folder}/{slug}",
                            source="ompa_vault",
                            backlinks=self._step4_kg_query(slug).backlinks,
                            timeline=[],
                            context_summary=self._summarize(note.content),
                        )
                except Exception:
                    continue
        except Exception as e:
            logger.debug("OMPA vault lookup failed: %s", e)

        return BrainLookupResult(found=False)

    def _step4_kg_query(self, entity: str) -> BrainLookupResult:
        """Step 4: KG entity query for temporal relationships."""
        try:
            ompa = self.memory.ompa
            if ompa is None:
                return BrainLookupResult(found=False)

            triples = ompa.kg_query(entity)
            if triples:
                content = "\n".join(
                    f"{t['subject']} —{t['predicate']}→ {t['object']}"
                    for t in triples[:10]
                )
                return BrainLookupResult(
                    found=True,
                    page_content=content,
                    source="kg",
                    context_summary=f"KG: {len(triples)} triples for {entity}",
                    backlinks=[],
                    timeline=[],
                )
        except Exception as e:
            logger.debug("KG query failed: %s", e)

        return BrainLookupResult(found=False)

    def _gbrain_backlinks(self, slug: str) -> list[str]:
        """Check GBrain for pages that reference this entity."""
        if not self.gbrain_vault_path:
            return []
        try:
            results = []
            for folder in ["people", "companies", "concepts", "work"]:
                folder_path = self.gbrain_vault_path / folder
                if not folder_path.exists():
                    continue
                for md_file in folder_path.glob("*.md"):
                    try:
                        content = md_file.read_text()
                        if slug in content.lower():
                            results.append(str(md_file.relative_to(self.gbrain_vault_path)))
                    except Exception:
                        continue
            return results[:10]
        except Exception:
            return []

    def _gbrain_timeline(self, folder: str, slug: str) -> list[dict]:
        """Get timeline.md for this entity if it exists."""
        if not self.gbrain_vault_path:
            return []
        try:
            tl_path = self.gbrain_vault_path / folder / slug / "timeline.md"
            if tl_path.exists():
                content = tl_path.read_text()
                return self._parse_timeline(content)
        except Exception:
            pass
        return []

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def _slugify(name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9\s-]", "", name)
        name = re.sub(r"[\s_]+", "-", name)
        return name[:80]

    @staticmethod
    def _summarize(content: str, max_chars: int = 300) -> str:
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + "..."

    @staticmethod
    def _parse_timeline(content: str) -> list[dict]:
        entries = []
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 2:
                    entries.append({
                        "date": parts[0].strip(),
                        "entry": parts[1].strip(),
                    })
        return entries


# Convenience function
def brain_first(entity_name: str, memory=None, gbrain_vault_path=None) -> BrainLookupResult:
    """
    Convenience function for the mandatory 5-step lookup.

    Usage before ANY external API call:
        result = brain_first("Jordan Chen", memory=mem, gbrain_vault_path="/data/gbrain")
        if not result.found:
            # Only now call external API
            data = web_search("Jordan Chen")
    """
    lookup = BrainFirstLookup(memory=memory, gbrain_vault_path=gbrain_vault_path)
    return lookup.run(entity_name)
