"""
MTB — Model Tracking Board for AegisFlow.

Tracks real-time token usage and cost against ZTB protocol model budget,
inspired by cc-lens analytics dashboard.

ZTB v2.5 Model Stack:
1. NVIDIA NIM (Primary)
2. Gemini 2.5 Flash-Lite (Secondary A - No-Think)
3. Gemini 2.0 Flash (Secondary B - Conciseness Backup)
4. GitHub Copilot (Tertiary)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ModelTier(str, Enum):
    PRIMARY = "nvidia"       # NVIDIA NIM
    SECONDARY_A = "gemini-flash-lite"  # Gemini 2.5 Flash-Lite
    SECONDARY_B = "gemini-flash"       # Gemini 2.0 Flash
    TERTIARY = "copilot"     # GitHub Copilot


# Map model string prefixes → tier
MODEL_TIER_MAP: dict[str, ModelTier] = {
    "nvidia/": ModelTier.PRIMARY,
    "meta/llama": ModelTier.PRIMARY,
    "mistral": ModelTier.PRIMARY,
    "gemma": ModelTier.SECONDARY_A,
    "gemini-2.0-flash": ModelTier.SECONDARY_A,
    "gemini-1.5-flash": ModelTier.SECONDARY_A,
    "gemini-2.5-flash": ModelTier.SECONDARY_A,
    "claude": ModelTier.SECONDARY_B,
    "gpt": ModelTier.SECONDARY_B,
    "copilot": ModelTier.TERTIARY,
}


@dataclass
class ModelUsageRecord:
    model: str
    tier: ModelTier
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    estimated_cost: float = 0.0
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DailyCostRecord:
    date: str  # YYYY-MM-DD
    by_tier: dict[ModelTier, float] = field(default_factory=dict)
    total: float = 0.0
    sessions: int = 0


class MTB:
    """
    Model Tracking Board — real-time token/cost tracker for ZTB protocol.

    Usage:
        mtb = MTB()
        mtb.record(model="nvidia/meta/llama-3.1-70b-instruct", input_tokens=512, output_tokens=128)
        mtb.record(model="gemini-2.0-flash", input_tokens=200, output_tokens=50)
        print(mtb.summary())
    """

    def __init__(self):
        self._records: list[ModelUsageRecord] = []
        self._daily: dict[str, DailyCostRecord] = {}

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        estimated_cost: float = 0.0,
        session_id: Optional[str] = None,
    ) -> ModelUsageRecord:
        tier = self._resolve_tier(model)
        record = ModelUsageRecord(
            model=model,
            tier=tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            estimated_cost=estimated_cost,
            session_id=session_id,
        )
        self._records.append(record)
        self._upsert_daily(record)
        return record

    def _resolve_tier(self, model: str) -> ModelTier:
        for prefix, tier in MODEL_TIER_MAP.items():
            if model.lower().startswith(prefix):
                return tier
        # Default: secondary B (Gemini Flash as common fallback)
        return ModelTier.SECONDARY_B

    def _upsert_daily(self, record: ModelUsageRecord) -> None:
        date_str = record.timestamp.date().isoformat()
        if date_str not in self._daily:
            self._daily[date_str] = DailyCostRecord(date=date_str)
        d = self._daily[date_str]
        d.total += record.estimated_cost
        d.by_tier[record.tier] = d.by_tier.get(record.tier, 0.0) + record.estimated_cost
        d.sessions += 1

    def total_cost(self) -> float:
        return sum(r.estimated_cost for r in self._records)

    def total_tokens(self) -> tuple[int, int]:
        inp = sum(r.input_tokens for r in self._records)
        out = sum(r.output_tokens for r in self._records)
        return inp, out

    def by_tier(self) -> dict[ModelTier, float]:
        result: dict[ModelTier, float] = {}
        for r in self._records:
            result[r.tier] = result.get(r.tier, 0.0) + r.estimated_cost
        return result

    def daily_summary(self) -> list[DailyCostRecord]:
        return sorted(self._daily.values(), key=lambda d: d.date)

    def summary(self) -> str:
        inp, out = self.total_tokens()
        by_t = self.by_tier()
        lines = [
            "# MTB — Model Tracking Board",
            f"**Total cost**: ${self.total_cost():.4f}",
            f"**Total tokens**: {inp:,} in / {out:,} out",
            f"**Sessions tracked**: {len(set(r.session_id for r in self._records if r.session_id))}",
            "",
            "## Cost by ZTB Tier",
        ]
        for tier in ModelTier:
            cost = by_t.get(tier, 0.0)
            lines.append(f"- {tier.value}: ${cost:.4f}")
        lines.append("")
        lines.append("## Daily")
        for d in self.daily_summary():
            lines.append(f"- {d.date}: ${d.total:.4f} ({d.sessions} sessions)")
        return "\n".join(lines)

    def clear(self) -> None:
        self._records.clear()
        self._daily.clear()
