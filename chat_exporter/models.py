from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Turn:
    """One reconstructed conversation turn (a `user`, `assistant`, or
    `system` record — the latter currently only used for compact-boundary
    markers)."""

    uuid: str
    parent_uuid: Optional[str]
    session_id: str
    role: str  # "user" | "assistant" | "system"
    timestamp: str
    is_meta: bool
    is_sidechain: bool
    blocks: list[dict] = field(default_factory=list)
    tool_use_result: Optional[dict] = None
    git_branch: Optional[str] = None
    cwd: Optional[str] = None
    is_compact_summary: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    """A `tool_use` block joined with its matching `tool_result`, if any."""

    session_id: str
    tool_use_id: str
    name: str
    input: dict
    call_timestamp: str
    caller: str
    project_cwd: Optional[str] = None
    result_text: Optional[str] = None
    result_is_error: bool = False
    result_timestamp: Optional[str] = None
    tool_use_result: Optional[dict] = None


@dataclass
class Session:
    session_id: str
    project_dir: str
    file_path: str
    project_cwd: Optional[str] = None
    git_branch: Optional[str] = None
    ai_titles: list[str] = field(default_factory=list)
    last_prompt: Optional[str] = None
    turns: list[Turn] = field(default_factory=list)
    raw_records: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    source_sha256: str = ""
    source_size: int = 0
    source_mtime: float = 0.0

    @property
    def title(self) -> str:
        if self.ai_titles:
            return self.ai_titles[-1]
        return self.session_id

    @property
    def start_ts(self) -> Optional[str]:
        return self.turns[0].timestamp if self.turns else None

    @property
    def end_ts(self) -> Optional[str]:
        return self.turns[-1].timestamp if self.turns else None
