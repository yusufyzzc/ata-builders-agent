from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    APPOINTMENT = "appointment"
    COWORKING_SEARCH = "coworking_search"
    TRIP_PLANNING = "trip_planning"
    MEETING = "meeting"
    REMINDER = "reminder"
    UNKNOWN = "unknown"


class ToolStatus(str, Enum):
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    FAILURE = "failure"


@dataclass
class ToolResult:
    tool: str
    status: ToolStatus
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class TaskState:
    raw_request: str
    task_type: TaskType = TaskType.UNKNOWN
    slots: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    final_answer: str = ""

    def add_tool_result(self, result: ToolResult) -> None:
        self.tool_results.append(result)
        if result.status == ToolStatus.FAILURE:
            self.blockers.append(f"{result.tool} failed: {result.message}")
        elif result.status == ToolStatus.NO_RESULTS:
            self.blockers.append(f"{result.tool} returned no results: {result.message}")
