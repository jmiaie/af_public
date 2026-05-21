"""
Session analytics for AegisFlow — computes token cost, tool usage, and efficiency
metrics for agent sessions, compatible with cc-lens session format.

Integrates with:
- MemoryVault: stores analytics reports alongside work/memory files
- ZTB pricing: ModelPricing from analytics/pricing.py
- OMPA: enriches session context with cost/trend data
- Sandfish/AegisFlow: surfaces efficiency insights during orchestration
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from aegisflow.analytics.tool_categories import ToolCategory, categorize_tool
from aegisflow.llm.pricing import estimate_cost_from_dict


@dataclass
class ToolCallRecord:
    name: str
    category: ToolCategory
    is_error: bool = False


@dataclass
class TurnRecord:
    type: str  # "user" | "assistant"
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    estimated_cost: float = 0.0
    turn_duration_ms: float = 0.0


@dataclass
class SessionAnalytics:
    session_id: str
    start_time: datetime
    turns: list[TurnRecord] = field(default_factory=list)
    tool_counts: dict[str, int] = field(default_factory=dict)
    tool_categories: dict[ToolCategory, int] = field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cache_read_tokens: int = 0
    estimated_cost: float = 0.0
    cache_savings: float = 0.0
    cache_hit_rate: float = 0.0
    error_count: int = 0
    uses_task_agent: bool = False
    uses_mcp: bool = False
    uses_web_search: bool = False
    uses_web_fetch: bool = False
    estimated_cost_without_cache: float = 0.0
    end_time: Optional[datetime] = None

    @property
    def duration_minutes(self) -> float:
        if not self.end_time:
            return 0.0
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 60.0


class SessionAnalyzer:
    """
    Analyzes raw session turn data and produces SessionAnalytics.

    Accepts dicts in cc-lens ReplayTurn format (or AegisFlow SubAgentResult format).
    Works with any JSONL session log stored in MemoryVault.
    """

    def analyze(self, session_id: str, turns: list[dict]) -> SessionAnalytics:
        start_time = datetime.now(timezone.utc)
        analytics = SessionAnalytics(session_id=session_id, start_time=start_time)

        for turn in turns:
            t = self._parse_turn(turn)
            if t:
                analytics.turns.append(t)
                self._update_totals(analytics, t)
                start_time = self._earliest(turn, start_time)

        # Derive end_time from last turn
        if turns:
            last_ts = turns[-1].get("timestamp")
            if last_ts:
                analytics.end_time = datetime.fromisoformat(
                    last_ts.replace("Z", "+00:00")
                )

        # Finalize cache stats
        total = analytics.total_input_tokens + analytics.total_cache_read_tokens
        if total > 0:
            analytics.cache_hit_rate = analytics.total_cache_read_tokens / total

        cost_without_cache = (
            analytics.total_input_tokens * 15.0 / 1_000_000
            + analytics.total_output_tokens * 75.0 / 1_000_000
        )
        analytics.estimated_cost_without_cache = cost_without_cache
        analytics.cache_savings = cost_without_cache - analytics.estimated_cost

        return analytics

    def _parse_turn(self, turn: dict) -> Optional[TurnRecord]:
        t_type = turn.get("type")
        if t_type not in ("user", "assistant"):
            return None

        model = turn.get("model")
        usage = turn.get("usage", {})

        t = TurnRecord(type=t_type, model=model)

        if usage and isinstance(usage, dict):
            t.input_tokens = usage.get("input_tokens", 0)
            t.output_tokens = usage.get("output_tokens", 0)
            t.cache_creation_input_tokens = usage.get("cache_creation_input_tokens", 0)
            t.cache_read_input_tokens = usage.get("cache_read_input_tokens", 0)
            if model:
                t.estimated_cost = estimate_cost_from_dict(model, usage)

        t.turn_duration_ms = turn.get("turn_duration_ms", 0.0)

        # Parse tool calls for assistant turns
        if t_type == "assistant":
            for tc in turn.get("tool_calls", []):
                name = tc.get("name", "unknown")
                t.tool_calls.append(
                    ToolCallRecord(name=name, category=categorize_tool(name))
                )

        return t

    def _update_totals(self, a: SessionAnalytics, t: TurnRecord) -> None:
        a.total_input_tokens += t.input_tokens
        a.total_output_tokens += t.output_tokens
        a.total_cache_write_tokens += t.cache_creation_input_tokens
        a.total_cache_read_tokens += t.cache_read_input_tokens
        a.estimated_cost += t.estimated_cost

        for tc in t.tool_calls:
            a.tool_counts[tc.name] = a.tool_counts.get(tc.name, 0) + 1
            a.tool_categories[tc.category] = (
                a.tool_categories.get(tc.category, 0) + 1
            )
            if tc.is_error:
                a.error_count += 1
            if tc.category == ToolCategory.AGENT:
                a.uses_task_agent = True
            if tc.category == ToolCategory.MCP:
                a.uses_mcp = True
            if tc.category == ToolCategory.WEB:
                a.uses_web_search = True

    def _earliest(self, turn: dict, fallback: datetime) -> datetime:
        ts = turn.get("timestamp")
        if not ts:
            return fallback
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return fallback


def render_analytics_summary(a: SessionAnalytics) -> str:
    """Render a human-readable analytics summary for MemoryVault storage."""
    lines = [
        f"# Session Analytics — {a.session_id}",
        f"**Date**: {a.start_time.date()} | **Duration**: {a.duration_minutes:.1f} min",
        "",
        "## Cost",
        f"- **Estimated**: ${a.estimated_cost:.4f}",
        f"- **Without cache**: ${a.estimated_cost_without_cache:.4f}",
        f"- **Cache savings**: ${a.cache_savings:.4f}",
        f"- **Cache hit rate**: {a.cache_hit_rate * 100:.1f}%",
        "",
        "## Tokens",
        f"- Input: {a.total_input_tokens:,} | Output: {a.total_output_tokens:,}",
        f"- Cache write: {a.total_cache_write_tokens:,} | Cache read: {a.total_cache_read_tokens:,}",
        "",
        f"## Tool Usage ({sum(a.tool_counts.values())} total calls)",
    ]

    # Top tools
    sorted_tools = sorted(a.tool_counts.items(), key=lambda x: -x[1])[:8]
    for name, count in sorted_tools:
        cat = categorize_tool(name)
        lines.append(f"- `{name}` ({cat.value}): {count}")

    # Category breakdown
    lines.append("")
    lines.append("## Category Breakdown")
    for cat, count in sorted(a.tool_categories.items(), key=lambda x: -x[1]):
        lines.append(f"- {cat.value}: {count}")

    # Flags
    lines.append("")
    lines.append("## Flags")
    for flag, on in [
        ("Task/Agent tools", a.uses_task_agent),
        ("MCP tools", a.uses_mcp),
        ("Web search", a.uses_web_search),
    ]:
        lines.append(f"- {flag}: {'✅' if on else '❌'}")

    return "\n".join(lines)
