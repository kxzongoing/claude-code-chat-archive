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


def turn_kind(turn: "Turn") -> str:
    """Classify a turn into a display lane: user | assistant | tool | system.

    The transport puts `tool_result` blocks inside *user*-role records — that
    is how the API returns tool output, not something the human typed. Turns
    carrying only tool results are machine output and must never be attributed
    to the user. Likewise `isMeta` turns are injected context (system
    reminders), not typed input.
    """
    if turn.role == "system" or turn.is_compact_summary:
        return "system"
    if turn.role == "user":
        if turn.is_meta:
            return "system"
        authored = [b for b in turn.blocks if b.get("kind") in ("text", "thinking")]
        if not authored and any(b.get("kind") == "tool_result" for b in turn.blocks):
            return "tool"
        return "user"
    return "assistant"


def has_visible_content(turn: "Turn") -> bool:
    """True if a turn renders anything a reader can see.

    Assistant turns sometimes carry only a redacted `thinking` block with no
    text, which the renderers skip; counting those would report more turns
    than the page displays.
    """
    for block in turn.blocks:
        kind = block.get("kind")
        if kind in ("tool_use", "tool_result"):
            return True
        if kind in ("text", "thinking") and (block.get("text") or "").strip():
            return True
    return False


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
    def counts(self) -> tuple[int, int]:
        """(human turns, Claude turns) as actually displayed.

        Excludes tool output and injected context — machine records the
        transport stores under the `user` role — and turns with nothing to
        show (e.g. redacted thinking blocks), so the count always matches
        what a reader sees on the page.
        """
        user = assistant = 0
        for turn in self.turns:
            kind = turn_kind(turn)
            if kind not in ("user", "assistant") or not has_visible_content(turn):
                continue
            if kind == "user":
                user += 1
            else:
                assistant += 1
        return user, assistant

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
