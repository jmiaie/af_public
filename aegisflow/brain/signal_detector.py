"""
Signal Detector — ported from gbrain (garrytan/gbrain).

Always-on ambient capture skill. Fires on every inbound message to capture:
1. Original thinking — user's ideas, observations, theses, frameworks
2. Entity mentions — people, companies, media references

IMPORTANT: Runs in parallel. NEVER blocks the main response.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from collections.abc import Callable


@dataclass
class SignalSummary:
    """One-line summary of what was captured this cycle."""
    ideas: int = 0
    entities: int = 0
    facts: int = 0
    skipped: bool = False
    idea_paths: list[str] = field(default_factory=list)
    entity_paths: list[str] = field(default_factory=list)


@dataclass
class SignalCapture:
    """Raw capture from one signal detection cycle."""
    # Original thinking
    original_thinking: list[str] = field(default_factory=list)
    # Entity mentions
    people: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    # New facts about existing entities
    facts: list[dict] = field(default_factory=list)


class SignalDetector:
    """
    Ambient signal capture that fires on every inbound message.

    Runs in PARALLEL (sub-agent or thread). Never blocks main response.
    Stores captured signals for later processing by brain-ops.

    Usage:
        detector = SignalDetector(vault, semantic_mem, brain_first_lookup)

        # In main loop — spawn as parallel task
        signals = detector.detect(
            user_message="I think we should approach Jordan from MiCap about the Phoenix deal",
            is_operational=False
        )

        # Or: process async in background
        await detector.detect_async(...)
    """

    # Operational patterns — skip signal detection for purely operational messages
    OPERATIONAL_PATTERNS = [
        "ok", "thanks", "thank you", "got it", "sure", "yes",
        "no", "nope", "do it", "go ahead", "👍", "✅",
        "nevermind", "never mind", "cancel", "never mind",
    ]

    def __init__(
        self,
        vault,
        semantic_memory=None,
        brain_first_lookup=None,
        model_name: str = "tinyllama:latest",
        spawn_fn: Optional[Callable] = None,
    ):
        """
        vault: MemoryVault instance
        semantic_memory: SemanticMemory instance (optional)
        brain_first_lookup: BrainFirstLookup instance (optional)
        model_name: LLM for idea detection (default: local tinyllama)
        spawn_fn: async function to spawn parallel sub-agent
        """
        self.vault = vault
        self.semantic = semantic_memory
        self.brain_lookup = brain_first_lookup
        self.model_name = model_name
        self.spawn_fn = spawn_fn  # e.g. sessions_spawn

    def detect(
        self,
        user_message: str,
        is_operational: bool = False,
        context: Optional[dict] = None,
    ) -> SignalSummary:
        """
        Synchronous detect. Returns summary immediately.
        For parallel execution, use detect_async().
        """
        # Skip if operational
        msg_lower = user_message.lower().strip()
        if is_operational or self._is_operational(msg_lower):
            return SignalSummary(skipped=True)

        capture = SignalCapture()

        # Phase 1: Original thinking detection
        capture.original_thinking = self._extract_original_thinking(user_message)

        # Phase 2: Entity detection
        capture.people = self._extract_people(user_message)
        capture.companies = self._extract_companies(user_message)
        capture.concepts = self._extract_concepts(user_message)

        # Phase 3: Write to brain
        summary = self._write_to_brain(capture, context or {})

        return summary

    async def detect_async(
        self,
        user_message: str,
        is_operational: bool = False,
        context: Optional[dict] = None,
    ) -> SignalSummary:
        """Async version — use spawn_fn for true parallelism."""
        if self.spawn_fn:
            # Spawn as parallel sub-agent
            return await self.spawn_fn(
                task=f"Signal detect: {user_message[:200]}",
                background=True,
            )
        return self.detect(user_message, is_operational, context)

    def _is_operational(self, msg: str) -> bool:
        return msg in self.OPERATIONAL_PATTERNS or len(msg) < 3

    def _extract_original_thinking(self, message: str) -> list[str]:
        """
        Extract original ideas/opinions/theses from user message.
        Uses heuristics + optional LLM classification.
        """
        ideas = []

        # Heuristic triggers for original thinking
        thinking_triggers = [
            "i think", "i believe", "my thesis", "my theory",
            "my observation", "i suspect", "it seems to me",
            "i've been wondering", "i wonder if", "what if",
            "my hunch", "i feel like", "i'd argue",
            "the pattern i'm seeing", "it occurs to me",
        ]

        msg_lower = message.lower()
        for trigger in thinking_triggers:
            if trigger in msg_lower:
                idx = msg_lower.find(trigger)
                # Extract sentence containing trigger
                snippet = message[idx:idx+200].split(". ")[0][:200]
                if snippet and len(snippet) > 10:
                    ideas.append(snippet.strip())

        return ideas

    def _extract_people(self, message: str) -> list[str]:
        """Extract person names. Placeholder — wire to NER/LLM for production."""
        # Simple regex-based extraction (names are capitalized words)
        import re
        # Look for title + name patterns
        patterns = [
            r'\b(Mr|Mrs|Ms|Dr|Prof)\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+',
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',
        ]
        names = []
        for pattern in patterns:
            matches = re.findall(pattern, message)
            names.extend(matches)
        return list(set(names))[:5]  # Dedupe, cap at 5

    def _extract_companies(self, message: str) -> list[str]:
        """Extract company names. Uses INC/LLC/Ltd/corp suffixes + known patterns."""
        import re
        # Company suffixes
        pattern = r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:Inc|LLC|Ltd|Corp|Corporation|Holdings|Partners|Group|Ventures|Capital)\b'
        matches = re.findall(pattern, message)
        # Also known tech companies
        tech = ["Apple", "Google", "Microsoft", "Meta", "Amazon", "Tesla", "OpenAI", "Anthropic",
                "NVIDIA", "Stripe", "Shopify", "Notion", "Figma", "Linear", "Vercel"]
        for co in tech:
            if co in message and co not in matches:
                matches.append(co)
        return list(set(matches))[:5]

    def _extract_concepts(self, message: str) -> list[str]:
        """Extract concept/framework mentions."""
        concepts = []
        concept_triggers = [
            "the concept of", "the idea that", "pattern", "framework",
            "model", "theory", "thesis", "strategy", "principle",
        ]
        msg_lower = message.lower()
        for trigger in concept_triggers:
            if trigger in msg_lower:
                idx = msg_lower.find(trigger)
                snippet = message[idx:idx+100].split(".")[0][:100].strip()
                if snippet:
                    concepts.append(snippet)
        return concepts[:3]

    def _write_to_brain(self, capture: SignalCapture, context: dict) -> SignalSummary:
        """Write captured signals to MemoryVault with citations."""
        summary = SignalSummary()
        today = datetime.now(timezone.utc).date().isoformat()

        # Write original thinking to originals/ or concepts/
        for idea in capture.original_thinking:
            slug = self._slugify(idea[:60])
            path = f"originals/{slug}.md"
            content = f"""# Original: {idea[:80]}

{idea}

**Captured**: {today}
**Source**: [Source: User, direct statement, {today}]

## Related
"""
            try:
                self.vault.store_verbatim(content, category="originals", filename=f"{slug}.md")
                summary.ideas += 1
                summary.idea_paths.append(path)
            except Exception:
                pass

        # Write entity mentions
        for person in capture.people:
            slug = self._slugify(person)
            path = f"people/{slug}.md"
            content = f"""# {person}

**First seen**: {today}
**Source**: [Source: User, mentioned in conversation, {today}]

## Notes
"""
            try:
                self.vault.store_verbatim(content, category="people", filename=f"{slug}.md")
                summary.entities += 1
                summary.entity_paths.append(path)
            except Exception:
                pass

        for company in capture.companies:
            slug = self._slugify(company)
            path = f"companies/{slug}.md"
            content = f"""# {company}

**First seen**: {today}
**Source**: [Source: User, mentioned in conversation, {today}]

## Notes
"""
            try:
                self.vault.store_verbatim(content, category="companies", filename=f"{slug}.md")
                summary.entities += 1
                summary.entity_paths.append(path)
            except Exception:
                pass

        return summary

    def _slugify(self, text: str) -> str:
        import re
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        return text[:80]

    def log_summary(self, summary: SignalSummary) -> str:
        """Generate the one-line log string for signal detection."""
        if summary.skipped:
            return f"Signals: 0 ideas, 0 entities, 0 facts (skipped: operational)"
        paths = []
        if summary.idea_paths:
            paths.append(f"ideas: {', '.join(summary.idea_paths[:2])}")
        if summary.entity_paths:
            paths.append(f"entities: {', '.join(summary.entity_paths[:2])}")
        return (
            f"Signals: {summary.ideas} ideas, {summary.entities} entities, "
            f"{summary.facts} facts"
            + (f" ({', '.join(paths)})" if paths else "")
        )
