from __future__ import annotations

import re

from .models import Session, ToolCall
from .util import as_text

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

_DECISION_KEYWORDS = re.compile(
    r"\b("
    r"architecture|architectural|design decision|trade-?off|"
    r"we(?:'ll| will) use|we(?:'ll| will) go with|we should use|"
    r"decided to|decision:|instead of using|instead of|going with|"
    r"chose to|chosen approach|the approach (?:is|will be|taken)|"
    r"key design|invariant:|critical invariant"
    r")\b",
    re.IGNORECASE,
)


def tool_call_record(session: Session, tc: ToolCall) -> dict:
    return {
        "session_id": session.session_id,
        "session_title": session.title,
        "project_cwd": tc.project_cwd,
        "tool_name": tc.name,
        "tool_use_id": tc.tool_use_id,
        "caller": tc.caller,
        "call_timestamp": tc.call_timestamp,
        "input": tc.input,
        "result_timestamp": tc.result_timestamp,
        "result_is_error": tc.result_is_error,
        "result_text": tc.result_text,
    }


def extract_tool_invocations(session: Session) -> list[dict]:
    return [tool_call_record(session, tc) for tc in session.tool_calls]


def extract_bash_commands(session: Session) -> list[dict]:
    out = []
    for tc in session.tool_calls:
        if tc.name != "Bash":
            continue
        stdout = stderr = None
        interrupted = False
        if isinstance(tc.tool_use_result, dict):
            stdout = tc.tool_use_result.get("stdout")
            stderr = tc.tool_use_result.get("stderr")
            interrupted = bool(tc.tool_use_result.get("interrupted"))
        out.append(
            {
                "session_id": session.session_id,
                "session_title": session.title,
                "project_cwd": tc.project_cwd,
                "timestamp": tc.call_timestamp,
                "command": tc.input.get("command", ""),
                "description": tc.input.get("description"),
                "run_in_background": bool(tc.input.get("run_in_background")),
                "timeout_ms": tc.input.get("timeout"),
                "stdout": stdout if stdout is not None else tc.result_text,
                "stderr": stderr,
                "interrupted": interrupted,
                "is_error": tc.result_is_error,
            }
        )
    return out


def extract_file_modifications(session: Session) -> list[dict]:
    out = []
    for tc in session.tool_calls:
        if tc.name not in FILE_TOOLS:
            continue
        inp = tc.input
        entry = {
            "session_id": session.session_id,
            "session_title": session.title,
            "project_cwd": tc.project_cwd,
            "timestamp": tc.call_timestamp,
            "tool": tc.name,
            "is_error": tc.result_is_error,
        }
        if tc.name == "Write":
            entry.update(
                file_path=inp.get("file_path"),
                action="write",
                content_preview=as_text(inp.get("content"))[:500],
                content_length=len(as_text(inp.get("content"))),
            )
        elif tc.name == "Edit":
            entry.update(
                file_path=inp.get("file_path"),
                action="edit",
                replace_all=bool(inp.get("replace_all")),
                old_string_preview=as_text(inp.get("old_string"))[:300],
                new_string_preview=as_text(inp.get("new_string"))[:300],
            )
        elif tc.name == "MultiEdit":
            edits = inp.get("edits") or []
            entry.update(
                file_path=inp.get("file_path"),
                action="multi_edit",
                edit_count=len(edits),
            )
        elif tc.name == "NotebookEdit":
            entry.update(
                file_path=inp.get("notebook_path"),
                action=f"notebook_{inp.get('edit_mode', 'replace')}",
                cell_id=inp.get("cell_id"),
            )
        out.append(entry)
    return out


def _paragraph_hits(text: str) -> list[str]:
    hits = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if para and _DECISION_KEYWORDS.search(para):
            hits.append(para)
    return hits


def extract_architectural_decisions(session: Session) -> list[dict]:
    out = []
    seen = set()

    def add(timestamp: str, kind: str, text: str):
        text = text.strip()
        if not text or text in seen:
            return
        seen.add(text)
        out.append(
            {
                "session_id": session.session_id,
                "session_title": session.title,
                "project_cwd": session.project_cwd,
                "timestamp": timestamp,
                "kind": kind,
                "text": text,
            }
        )

    for turn in session.turns:
        if turn.role != "assistant":
            continue
        for block in turn.blocks:
            if block.get("kind") == "text":
                for para in _paragraph_hits(block.get("text", "")):
                    add(turn.timestamp, "mentions_decision_language", para)
            elif block.get("kind") == "tool_use" and block.get("name") == "ExitPlanMode":
                plan = block.get("input", {}).get("plan")
                if plan:
                    add(turn.timestamp, "plan_proposed", plan)
            elif block.get("kind") == "tool_use" and block.get("name") == "AskUserQuestion":
                questions = block.get("input", {}).get("questions") or []
                for q in questions:
                    qtext = q.get("question", "")
                    options = ", ".join(o.get("label", "") for o in q.get("options", []))
                    add(
                        turn.timestamp,
                        "decision_point_asked",
                        f"{qtext}\nOptions considered: {options}",
                    )

    return out
