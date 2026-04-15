"""
Brain-First Lookup Protocol — ported from gbrain (garrytan/gbrain).

The 5-step lookup that MUST run before ANY external API call:
web search, enrichment service, social lookup, etc.

The brain almost always has something. External APIs fill gaps, not start from scratch.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class BrainLookupResult:
    found: bool
    page_content: Optional[str] = None
    slug: Optional[str] = None
    backlinks: list[str] = None
    timeline: list[dict] = None
    context_summary: Optional[str] = None


class BrainFirstLookup:
    """
    The mandatory 5-step lookup protocol.

    Usage:
        lookup = BrainFirstLookup(vault, semantic_mem)
        result = lookup.run("Jordan Chen")
        if result.found:
            print(result.page_content)
        # THEN call external API only if result.context_still_missing
    """

    def __init__(self, memory_vault, semantic_memory=None):
        """
        memory_vault: aegisflow MemoryVault instance
        semantic_memory: aegisflow SemanticMemory instance (optional, for query step)
        """
        self.vault = memory_vault
        self.semantic = semantic_memory

    def run(self, entity_name: str) -> BrainLookupResult:
        """
        Run all 5 steps. Returns result with .found = True if brain has anything.
        """
        # Step 1: Keyword search via MemoryVault
        page_content, slug = self._step1_keyword_search(entity_name)
        if page_content:
            return BrainLookupResult(
                found=True,
                page_content=page_content,
                slug=slug,
                backlinks=self._step4_backlinks(slug) if slug else [],
                timeline=self._step5_timeline(slug) if slug else [],
                context_summary=self._summarize(page_content),
            )

        # Step 2: Hybrid search via SemanticMemory
        if self.semantic:
            results = self.semantic.retrieve(f"who is {entity_name}", top_k=3, min_score=0.3)
            if results:
                content = "\n".join(r["content"] for r in results)
                return BrainLookupResult(
                    found=True,
                    page_content=content,
                    context_summary=f"Hybrid search: {len(results)} hits",
                    backlinks=[],
                    timeline=[],
                )

        # Step 3: Try slug-based lookup
        slug = self._slugify(entity_name)
        page_content = self._step3_slug_lookup(slug)
        if page_content:
            return BrainLookupResult(
                found=True,
                page_content=page_content,
                slug=slug,
                backlinks=self._step4_backlinks(slug),
                timeline=self._step5_timeline(slug),
            )

        # Not found
        return BrainLookupResult(found=False)

    def run_async(self, entity_name: str) -> BrainLookupResult:
        """Sync version — same implementation."""
        return self.run(entity_name)

    def _step1_keyword_search(self, name: str) -> tuple[Optional[str], Optional[str]]:
        """Search vault directories for entity name."""
        # Try all categories
        for cat in ["people", "companies", "work", "brain"]:
            try:
                content = self.vault.read_file(f"{cat}/{self._slugify(name)}.md")
                if content:
                    return content, f"{cat}/{self._slugify(name)}"
            except Exception:
                continue
        return None, None

    def _step2_hybrid_search(self, query: str) -> list[dict]:
        """Semantic search if available."""
        if not self.semantic:
            return []
        return self.semantic.retrieve(query, top_k=3, min_score=0.3)

    def _step3_slug_lookup(self, slug: str) -> Optional[str]:
        """Direct slug path lookup."""
        for cat in ["people", "companies", "concepts", "originals", "ideas", "work"]:
            try:
                content = self.vault.read_file(f"{cat}/{slug}.md")
                if content:
                    return content
            except Exception:
                continue
        return None

    def _step4_backlinks(self, slug: str) -> list[str]:
        """Check who references this entity."""
        try:
            backlinks = self.vault.search(f"referenced in.{slug}")
            return backlinks[:10]
        except Exception:
            return []

    def _step5_timeline(self, slug: str) -> list[dict]:
        """Get timeline entries for this entity."""
        try:
            timeline_path = f"people/{slug}/timeline.md"
            content = self.vault.read_file(timeline_path)
            return self._parse_timeline(content)
        except Exception:
            return []

    def _slugify(self, name: str) -> str:
        import re
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9\s-]", "", name)
        name = re.sub(r"[\s_]+", "-", name)
        return name[:80]

    def _summarize(self, content: str, max_chars: int = 300) -> str:
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + "..."

    def _parse_timeline(self, content: str) -> list[dict]:
        """Parse timeline.md entries into structured dicts."""
        entries = []
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 2:
                    entries.append({"date": parts[0].strip(), "entry": parts[1].strip()})
        return entries


def brain_first(entity_name: str, vault, semantic=None) -> BrainLookupResult:
    """
    Convenience function for the mandatory 5-step lookup.

    Usage before ANY external API call:
        result = brain_first("Jordan Chen", vault, sem)
        if not result.found:
            # Only now call external API
            data = web_search("Jordan Chen")
    """
    lookup = BrainFirstLookup(vault, semantic)
    return lookup.run(entity_name)