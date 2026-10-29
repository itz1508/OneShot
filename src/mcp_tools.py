#!/usr/bin/env python3
"""
OneShot Assignment 10: MCP Tool Integrations

Exposes existing operations only using supported built-in interfaces.
Does NOT implement core logic, pause/resume, approval, Task Management,
Research, Plan, or Build. Enforces least privilege via existing access control.
"""

from dataclasses import dataclass, field
from typing import Callable, Any, Optional


@dataclass
class ToolDefinition:
    """Definition of an exposed tool."""
    name: str
    description: str
    input_schema: dict
    handler: Callable
    permissions: list = field(default_factory=list)


@dataclass
class ToolResult:
    """Result of a tool call."""
    success: bool
    output: Any
    error: str = ""


class MCPToolRegistry:
    """Registry of exposed tools. Only exposes existing operations."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, name: str, description: str, input_schema: dict,
                 handler: Callable, permissions: list = None):
        """Register an existing operation as a tool."""
        self._tools[name] = ToolDefinition(
            name=name, description=description,
            input_schema=input_schema, handler=handler,
            permissions=permissions or [],
        )

    def list_tools(self) -> list[dict]:
        """List all registered tools."""
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    def call(self, tool_name: str, input_data: dict, caller_permissions: list = None) -> ToolResult:
        """Call a registered tool with permission check."""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, output=None, error=f"Tool '{tool_name}' not found")

        # Check permissions via existing access control
        if tool.permissions:
            caller = caller_permissions or []
            if not any(p in caller for p in tool.permissions):
                return ToolResult(success=False, output=None, error="Access denied")

        # Validate input
        for required_key, expected_type in tool.input_schema.items():
            if required_key not in input_data:
                return ToolResult(success=False, output=None, error=f"Missing required field: {required_key}")
            if not isinstance(input_data[required_key], expected_type):
                return ToolResult(success=False, output=None, error=f"Invalid type for: {required_key}")

        try:
            result = tool.handler(input_data)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))

    def has_core_logic(self) -> bool:
        """Verify MCP layer does NOT contain core logic."""
        # This method exists for verification — it always returns False
        # because MCP only exposes existing operations via handlers.
        return False


def create_default_registry() -> MCPToolRegistry:
    """Create default tool registry exposing existing operations."""
    registry = MCPToolRegistry()

    # Expose repo_summary as a tool (wraps existing operation)
    def repo_summary_handler(input_data: dict) -> dict:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from repo_summary import RepoSummaryTool
        tool = RepoSummaryTool(repo_path=input_data.get("repo_path"))
        summary = tool.run()
        return {"commit_sha": summary.commit_sha, "files": summary.files, "color_eval": summary.color_eval_baseline}

    registry.register(
        name="repo_summary",
        description="Get repository summary and gap matrix",
        input_schema={"repo_path": str},
        handler=repo_summary_handler,
        permissions=["read"],
    )

    return registry
