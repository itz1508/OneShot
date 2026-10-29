#!/usr/bin/env python3
"""
OneShot Assignment 09: Build Execution

Executes approved build using supported built-in tools. Captures and hashes
artifacts, validates output schemas, runs fixtures, and traces the
Agent → Tool → Result → Agent continuation pattern. Partial failures
are preserved, not silently cleaned up.
"""

import hashlib
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable, Any


@dataclass
class Artifact:
    """A build artifact with hash."""
    path: str
    sha256: str
    size: int
    created_at: float


@dataclass
class ToolCall:
    """A single tool call in the execution trace."""
    tool: str
    input: dict
    output: Any
    timestamp: float


@dataclass
class BuildResult:
    """Result of build execution."""
    artifacts: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    fixture_results: dict = field(default_factory=dict)
    schema_valid: bool = False
    all_tests_pass: bool = False
    partial_failures: list = field(default_factory=list)
    finalized: bool = False


class BuildExecutor:
    """Executes build using supported tools, traces agent-tool continuation."""

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = Path(repo_path) if repo_path else Path(__file__).resolve().parent.parent
        self.trace: list[ToolCall] = []

    def _hash_file(self, filepath: str) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def call_tool(self, tool_name: str, tool_input: dict, tool_fn: Callable) -> Any:
        """Execute a tool call and record it in the trace (Agent → Tool → Result)."""
        timestamp = time.time()
        result = tool_fn(tool_input)
        self.trace.append(ToolCall(
            tool=tool_name, input=tool_input, output=result, timestamp=timestamp
        ))
        return result

    def capture_artifact(self, filepath: str) -> Artifact:
        """Capture an artifact with SHA-256 hash."""
        full_path = self.repo_path / filepath
        if not full_path.exists():
            raise FileNotFoundError(f"Artifact not found: {filepath}")
        return Artifact(
            path=filepath,
            sha256=self._hash_file(str(full_path)),
            size=full_path.stat().st_size,
            created_at=time.time(),
        )

    def validate_schema(self, output: dict, expected_schema: dict) -> bool:
        """Validate output against expected schema."""
        for key, expected_type in expected_schema.items():
            if key not in output:
                return False
            if not isinstance(output[key], expected_type):
                return False
        return True

    def run_fixtures(self, fixture_runner: Callable) -> dict:
        """Run the full fixture set."""
        return fixture_runner()

    def execute(self, build_steps: list, fixture_runner: Callable = None,
                expected_schema: dict = None) -> BuildResult:
        """Execute build steps, capture artifacts, run fixtures."""
        result = BuildResult()

        for step in build_steps:
            try:
                tool_name = step.get("tool", "unknown")
                tool_input = step.get("input", {})
                tool_fn = step.get("function", lambda x: None)
                output = self.call_tool(tool_name, tool_input, tool_fn)

                if step.get("artifact_path"):
                    artifact = self.capture_artifact(step["artifact_path"])
                    result.artifacts.append(asdict(artifact))

            except Exception as e:
                result.partial_failures.append({
                    "step": step.get("tool", "unknown"),
                    "error": str(e),
                })

        if fixture_runner:
            result.fixture_results = self.run_fixtures(fixture_runner)
            result.all_tests_pass = result.fixture_results.get("all_pass", False)

        if expected_schema:
            output_dict = {"artifacts": result.artifacts, "trace": [asdict(t) for t in self.trace]}
            result.schema_valid = self.validate_schema(output_dict, expected_schema)

        result.trace = [asdict(t) for t in self.trace]

        # Finalize only after all tests pass
        result.finalized = result.all_tests_pass and not result.partial_failures

        return result
