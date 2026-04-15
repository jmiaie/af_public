"""
Tool category system ported from cc-lens (Arindam200/cc-lens).
Maps OpenClaw/Claude Code tool names to semantic categories.
"""

from enum import Enum


class ToolCategory(str, Enum):
    FILE_IO = "file-io"
    SHELL = "shell"
    AGENT = "agent"
    WEB = "web"
    PLANNING = "planning"
    TODO = "todo"
    SKILL = "skill"
    MCP = "mcp"
    OTHER = "other"


TOOL_CATEGORIES: dict[str, ToolCategory] = {
    # File I/O
    "Read": ToolCategory.FILE_IO,
    "Write": ToolCategory.FILE_IO,
    "Edit": ToolCategory.FILE_IO,
    "Glob": ToolCategory.FILE_IO,
    "Grep": ToolCategory.FILE_IO,
    "NotebookEdit": ToolCategory.FILE_IO,
    # Shell
    "Bash": ToolCategory.SHELL,
    "exec": ToolCategory.SHELL,
    # Agent (OpenClaw-style)
    "Task": ToolCategory.AGENT,
    "TaskCreate": ToolCategory.AGENT,
    "TaskUpdate": ToolCategory.AGENT,
    "TaskList": ToolCategory.AGENT,
    "TaskOutput": ToolCategory.AGENT,
    "TaskStop": ToolCategory.AGENT,
    "TaskGet": ToolCategory.AGENT,
    "sessions_spawn": ToolCategory.AGENT,
    "subagents": ToolCategory.AGENT,
    # Web
    "WebSearch": ToolCategory.WEB,
    "WebFetch": ToolCategory.WEB,
    "web_fetch": ToolCategory.WEB,
    "browser": ToolCategory.WEB,
    # Planning
    "EnterPlanMode": ToolCategory.PLANNING,
    "ExitPlanMode": ToolCategory.PLANNING,
    "AskUserQuestion": ToolCategory.PLANNING,
    # Todo
    "TodoWrite": ToolCategory.TODO,
    "TodoUpdate": ToolCategory.TODO,
    "TodoList": ToolCategory.TODO,
    # Skills
    "Skill": ToolCategory.SKILL,
    "ToolSearch": ToolCategory.SKILL,
    "ListMcpResourcesTool": ToolCategory.SKILL,
    "ReadMcpResourceTool": ToolCategory.SKILL,
}


CATEGORY_LABELS: dict[ToolCategory, str] = {
    ToolCategory.FILE_IO: "File I/O",
    ToolCategory.SHELL: "Shell",
    ToolCategory.AGENT: "Agents",
    ToolCategory.WEB: "Web",
    ToolCategory.PLANNING: "Planning",
    ToolCategory.TODO: "Todo",
    ToolCategory.SKILL: "Skills",
    ToolCategory.MCP: "MCP",
    ToolCategory.OTHER: "Other",
}


def categorize_tool(name: str) -> ToolCategory:
    if name.startswith("mcp__"):
        return ToolCategory.MCP
    return TOOL_CATEGORIES.get(name, ToolCategory.OTHER)


def parse_mcp_tool(name: str) -> tuple[str, str] | None:
    """Parse 'mcp__server__tool' → ('server', 'tool')."""
    if not name.startswith("mcp__"):
        return None
    parts = name.split("__")
    if len(parts) < 3:
        return None
    return parts[1], "__".join(parts[2:])


def tool_display_name(name: str) -> str:
    mcp = parse_mcp_tool(name)
    if mcp:
        return f"{mcp[0]} · {mcp[1]}"
    return name
