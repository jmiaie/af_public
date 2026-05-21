"""
AegisFlow Analytics — session analytics, tool categories, and cost estimation
ported from cc-lens (Arindam200/cc-lens).

Tool categories: categorize any OpenClaw/Claude tool by type (file-io, shell, agent, web, etc.).
Session analytics: compute token/cost stats from session turn logs.
"""

from aegisflow.analytics.session import (
    SessionAnalytics,
    SessionAnalyzer,
    render_analytics_summary,
)
from aegisflow.analytics.tool_categories import (
    CATEGORY_LABELS,
    ToolCategory,
    categorize_tool,
    parse_mcp_tool,
    tool_display_name,
)

__all__ = [
    "ToolCategory",
    "categorize_tool",
    "parse_mcp_tool",
    "tool_display_name",
    "CATEGORY_LABELS",
    "SessionAnalytics",
    "SessionAnalyzer",
    "render_analytics_summary",
]
