"""
Pricing engine ported from cc-lens (Arindam200/cc-lens).
Provides Claude model cost estimation using Anthropic's official pricing.
"""

from dataclasses import dataclass

# ─── Pricing tables ────────────────────────────────────────────────────────────

@dataclass
class ModelPricing:
    input: float       # per million tokens
    output: float      # per million tokens
    cache_write: float # per million tokens
    cache_read: float  # per million tokens


PRICING: dict[str, ModelPricing] = {
    # Claude Opus 4
    "claude-opus-4-6": ModelPricing(15.00, 75.00, 18.75, 1.50),
    "claude-opus-4-5-20251101": ModelPricing(15.00, 75.00, 18.75, 1.50),
    # Claude Sonnet 4
    "claude-sonnet-4-6": ModelPricing(3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-4-5-20250620": ModelPricing(3.00, 15.00, 3.75, 0.30),
    # Claude Haiku 4
    "claude-haiku-4-5": ModelPricing(0.80, 4.00, 1.00, 0.08),
    "claude-haiku-4-6": ModelPricing(0.80, 4.00, 1.00, 0.08),
}

# Fallback for unknown models (conservative Opus pricing)
_DEFAULT = ModelPricing(15.00, 75.00, 18.75, 1.50)


def get_pricing(model: str) -> ModelPricing:
    if model in PRICING:
        return PRICING[model]
    # Fuzzy prefix match
    parts = model.split("-")[:3]
    prefix = "-".join(parts)
    for key in PRICING:
        if key.startswith(prefix) or prefix.startswith(key.rsplit("-", 2)[0]):
            return PRICING[key]
    return _DEFAULT


@dataclass
class TurnUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


def estimate_cost(model: str, usage: TurnUsage) -> float:
    p = get_pricing(model)
    return (
        usage.input_tokens * p.input / 1_000_000
        + usage.output_tokens * p.output / 1_000_000
        + usage.cache_creation_input_tokens * p.cache_write / 1_000_000
        + usage.cache_read_input_tokens * p.cache_read / 1_000_000
    )


def estimate_cost_from_dict(model: str, usage: dict) -> float:
    return estimate_cost(
        model,
        TurnUsage(
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0)),
            cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0)),
        ),
    )
