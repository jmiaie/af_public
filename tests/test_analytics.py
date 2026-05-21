"""
Tests for aegisflow.analytics — SessionAnalyzer, MTB, tool categories, pricing.

All deterministic, no network/LLM required.
"""

from __future__ import annotations

import pytest

from aegisflow.analytics.mtb import MTB, ModelTier
from aegisflow.analytics.session import (
    SessionAnalytics,
    SessionAnalyzer,
    render_analytics_summary,
)
from aegisflow.analytics.tool_categories import (
    ToolCategory,
    categorize_tool,
    parse_mcp_tool,
    tool_display_name,
)
from aegisflow.llm.pricing import (
    TurnUsage,
    estimate_cost,
    estimate_cost_from_dict,
    get_pricing,
)

# ── Tool Categories ──────────────────────────────────────────────────────────


class TestToolCategories:
    def test_known_tool(self):
        assert categorize_tool("Read") == ToolCategory.FILE_IO
        assert categorize_tool("Bash") == ToolCategory.SHELL
        assert categorize_tool("Task") == ToolCategory.AGENT
        assert categorize_tool("WebSearch") == ToolCategory.WEB

    def test_mcp_tool(self):
        assert categorize_tool("mcp__memory__store") == ToolCategory.MCP

    def test_unknown_tool(self):
        assert categorize_tool("CustomTool") == ToolCategory.OTHER

    def test_parse_mcp_tool(self):
        result = parse_mcp_tool("mcp__server__tool")
        assert result == ("server", "tool")

    def test_parse_mcp_tool_invalid(self):
        assert parse_mcp_tool("Read") is None

    def test_display_name_mcp(self):
        assert tool_display_name("mcp__server__tool") == "server · tool"

    def test_display_name_regular(self):
        assert tool_display_name("Read") == "Read"


# ── Pricing ──────────────────────────────────────────────────────────────────


class TestPricing:
    def test_known_model(self):
        p = get_pricing("claude-opus-4-6")
        assert p.input == 15.00
        assert p.output == 75.00

    def test_unknown_model_returns_default(self):
        p = get_pricing("totally-unknown-model")
        assert p.input == 15.00  # default = Opus pricing

    def test_estimate_cost(self):
        usage = TurnUsage(input_tokens=1_000_000, output_tokens=0)
        cost = estimate_cost("claude-opus-4-6", usage)
        assert cost == pytest.approx(15.00)

    def test_estimate_cost_from_dict(self):
        cost = estimate_cost_from_dict(
            "claude-sonnet-4-6",
            {"input_tokens": 1_000_000, "output_tokens": 0}
        )
        assert cost == pytest.approx(3.00)


# ── Session Analyzer ─────────────────────────────────────────────────────────


class TestSessionAnalyzer:
    def _make_turn(self, type_="assistant", model="claude-sonnet-4-6",
                   input_tokens=100, output_tokens=50, tool_calls=None):
        turn = {
            "type": type_,
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            "tool_calls": tool_calls or [],
        }
        return turn

    def test_basic_analysis(self):
        analyzer = SessionAnalyzer()
        turns = [
            self._make_turn(type_="user"),
            self._make_turn(type_="assistant", tool_calls=[{"name": "Read"}]),
        ]
        result = analyzer.analyze("test-session", turns)
        assert isinstance(result, SessionAnalytics)
        assert result.total_input_tokens > 0
        assert result.total_output_tokens > 0

    def test_tool_counting(self):
        analyzer = SessionAnalyzer()
        turns = [
            self._make_turn(tool_calls=[
                {"name": "Read"},
                {"name": "Read"},
                {"name": "Bash"},
            ]),
        ]
        result = analyzer.analyze("test", turns)
        assert result.tool_counts.get("Read") == 2
        assert result.tool_counts.get("Bash") == 1

    def test_agent_flag(self):
        analyzer = SessionAnalyzer()
        turns = [self._make_turn(tool_calls=[{"name": "Task"}])]
        result = analyzer.analyze("test", turns)
        assert result.uses_task_agent is True

    def test_render_summary(self):
        analyzer = SessionAnalyzer()
        result = analyzer.analyze("test", [self._make_turn()])
        rendered = render_analytics_summary(result)
        assert "Session Analytics" in rendered
        assert "$" in rendered  # cost is shown

    def test_empty_turns(self):
        analyzer = SessionAnalyzer()
        result = analyzer.analyze("empty", [])
        assert result.total_input_tokens == 0
        assert len(result.turns) == 0


# ── MTB ──────────────────────────────────────────────────────────────────────


class TestMTB:
    def test_record_and_total(self):
        mtb = MTB()
        mtb.record(model="nvidia/meta/llama-3.1-70b", input_tokens=1000,
                   output_tokens=500, estimated_cost=0.01)
        assert mtb.total_cost() == pytest.approx(0.01)

    def test_tier_resolution(self):
        mtb = MTB()
        assert mtb._resolve_tier("nvidia/meta/llama-3.1-70b") == ModelTier.PRIMARY
        assert mtb._resolve_tier("gemini-2.0-flash") == ModelTier.SECONDARY_A
        assert mtb._resolve_tier("claude-opus-4-6") == ModelTier.SECONDARY_B
        assert mtb._resolve_tier("copilot") == ModelTier.TERTIARY

    def test_by_tier(self):
        mtb = MTB()
        mtb.record(model="nvidia/x", input_tokens=100, output_tokens=50, estimated_cost=0.01)
        mtb.record(model="gemini-2.0-flash", input_tokens=100, output_tokens=50, estimated_cost=0.005)
        by_tier = mtb.by_tier()
        assert ModelTier.PRIMARY in by_tier
        assert ModelTier.SECONDARY_A in by_tier

    def test_summary_render(self):
        mtb = MTB()
        mtb.record(model="nvidia/x", input_tokens=100, output_tokens=50, estimated_cost=0.01)
        summary = mtb.summary()
        assert "MTB" in summary
        assert "$" in summary

    def test_clear(self):
        mtb = MTB()
        mtb.record(model="nvidia/x", input_tokens=100, output_tokens=50, estimated_cost=0.01)
        mtb.clear()
        assert mtb.total_cost() == 0.0

    def test_daily_summary(self):
        mtb = MTB()
        mtb.record(model="nvidia/x", input_tokens=100, output_tokens=50, estimated_cost=0.01)
        daily = mtb.daily_summary()
        assert len(daily) >= 1

    def test_total_tokens(self):
        mtb = MTB()
        mtb.record(model="nvidia/x", input_tokens=500, output_tokens=200)
        inp, out = mtb.total_tokens()
        assert inp == 500
        assert out == 200
