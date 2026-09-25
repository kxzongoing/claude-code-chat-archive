from __future__ import annotations

import json

from .models import Session, turn_kind
from .util import fmt_duration, truncate

TEXT_LIMIT = 8000
THINKING_LIMIT = 3000
RESULT_LIMIT = 3000
INPUT_LIMIT = 2000


_LANE_LABEL = {"user": "You", "assistant": "Claude", "system": "System", "tool": "Tool result"}


def _role_label(turn) -> str:
    kind = turn_kind(turn)
    label = _LANE_LABEL[kind]
    if kind == "system":
        if turn.is_compact_summary:
            label = "System (compacted summary)"
        elif turn.is_meta:
            label = "System (injected context)"
    return f"Subagent — {label}" if turn.is_sidechain else label


def _render_tool_use(block: dict) -> list[str]:
    name = block.get("name") or "unknown"
    inp = block.get("input") or {}
    lines = [f"**Tool call: `{name}`**", ""]

    if name == "Bash":
        if inp.get("description"):
            lines.append(f"*{inp['description']}*")
        lines.append("```bash")
        lines.append(inp.get("command", ""))
        lines.append("```")
    elif name == "Edit":
        lines.append(f"File: `{inp.get('file_path', '')}`")
        lines.append("")
        lines.append("```diff")
        for l in truncate(str(inp.get("old_string", "")), INPUT_LIMIT).splitlines():
            lines.append(f"- {l}")
        for l in truncate(str(inp.get("new_string", "")), INPUT_LIMIT).splitlines():
            lines.append(f"+ {l}")
        lines.append("```")
    elif name == "Write":
        lines.append(f"File: `{inp.get('file_path', '')}`")
        lines.append("")
        lines.append("```")
        lines.append(truncate(str(inp.get("content", "")), INPUT_LIMIT))
        lines.append("```")
    elif name in ("Read", "Glob", "Grep"):
        lines.append("```json")
        lines.append(json.dumps(inp, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("```json")
        lines.append(truncate(json.dumps(inp, ensure_ascii=False, indent=2), INPUT_LIMIT))
        lines.append("```")

    return lines


def render_session_markdown(session: Session) -> str:
    lines: list[str] = []
    lines.append(f"# {session.title}")
    lines.append("")
    n_user, n_assistant = session.counts
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Session ID | `{session.session_id}` |")
    lines.append(f"| Project | `{session.project_cwd or session.project_dir}` |")
    lines.append(f"| Git branch | `{session.git_branch or ''}` |")
    lines.append(f"| Started | {session.start_ts or ''} |")
    lines.append(f"| Ended | {session.end_ts or ''} |")
    lines.append(f"| Duration | {fmt_duration(session.start_ts, session.end_ts)} |")
    lines.append(f"| Turns | {n_user} user / {n_assistant} assistant |")
    lines.append(f"| Tool calls | {len(session.tool_calls)} |")
    lines.append(f"| Source | `{session.file_path}` |")
    lines.append("")
    lines.append("---")
    lines.append("")

    for turn in session.turns:
        label = _role_label(turn)
        lines.append(f"## {label} — {turn.timestamp} `{turn.uuid}`")
        lines.append("")
        for block in turn.blocks:
            kind = block.get("kind")
            if kind == "text":
                text = block.get("text", "").strip()
                if text:
                    lines.append(truncate(text, TEXT_LIMIT))
                    lines.append("")
            elif kind == "thinking":
                text = block.get("text", "").strip()
                if text:
                    lines.append("<details>")
                    lines.append("<summary>Thinking</summary>")
                    lines.append("")
                    lines.append(truncate(text, THINKING_LIMIT))
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")
            elif kind == "tool_use":
                lines.extend(_render_tool_use(block))
                lines.append("")
            elif kind == "tool_result":
                text = block.get("text", "").strip()
                status = "error" if block.get("is_error") else "ok"
                lines.append(f"**Tool result** ({status}):")
                lines.append("```")
                lines.append(truncate(text, RESULT_LIMIT))
                lines.append("```")
                lines.append("")
        lines.append("")

    if session.parse_warnings:
        lines.append("---")
        lines.append("")
        lines.append("### Parse warnings")
        for w in session.parse_warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)
