from __future__ import annotations

import json
import os

from .models import Session, ToolCall, Turn
from .scanner import SessionFile
from .util import as_text, sha256_file


def _normalize_blocks(content) -> list[dict]:
    """Normalize a message's `content` (str or list of content blocks) into
    a uniform list of {"kind": ..., ...} dicts."""
    if content is None:
        return []
    if isinstance(content, str):
        return [{"kind": "text", "text": content}]
    blocks: list[dict] = []
    for item in content:
        if not isinstance(item, dict):
            blocks.append({"kind": "text", "text": str(item)})
            continue
        btype = item.get("type")
        if btype == "text":
            blocks.append({"kind": "text", "text": item.get("text", "")})
        elif btype == "thinking":
            blocks.append({"kind": "thinking", "text": item.get("thinking", "")})
        elif btype == "tool_use":
            blocks.append(
                {
                    "kind": "tool_use",
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "input": item.get("input", {}),
                    "caller": (item.get("caller") or {}).get("type", "direct"),
                }
            )
        elif btype == "tool_result":
            blocks.append(
                {
                    "kind": "tool_result",
                    "tool_use_id": item.get("tool_use_id"),
                    "text": as_text(item.get("content")),
                    "is_error": bool(item.get("is_error")),
                }
            )
        else:
            blocks.append({"kind": btype or "unknown", "raw": item})
    return blocks


def parse_session_file(sf: SessionFile) -> Session:
    session = Session(
        session_id=sf.session_id,
        project_dir=sf.project_dir,
        file_path=sf.path,
    )

    try:
        session.source_size = os.path.getsize(sf.path)
        session.source_mtime = os.path.getmtime(sf.path)
        session.source_sha256 = sha256_file(sf.path)
    except OSError as exc:
        session.parse_warnings.append(f"could not stat file: {exc}")

    records: list[dict] = []
    with open(sf.path, "r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                session.parse_warnings.append(f"line {lineno}: invalid JSON ({exc})")

    return _build_session(session, records)


def parse_archived_session(
    project_dir: str,
    session_id: str,
    raw_path: str,
    manifest_entry: dict | None = None,
) -> Session:
    """Rebuild a Session from a previously exported `raw.json`.

    Claude Code prunes `~/.claude/projects/*.jsonl` after `cleanupPeriodDays`,
    so a session we archived months ago may no longer have a live source. The
    `raw.json` we wrote at export time holds the same records the `.jsonl`
    did, which is enough to regenerate every aggregate document. Source
    metadata (sha256/size/mtime) is carried over from the manifest so the
    incremental check in the caller still sees an unchanged session.
    """
    entry = manifest_entry or {}
    session = Session(
        session_id=session_id,
        project_dir=project_dir,
        file_path=entry.get("source_path") or raw_path,
        source_sha256=entry.get("sha256", ""),
        source_size=entry.get("size", 0),
        source_mtime=entry.get("mtime", 0.0),
    )

    with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
        records = json.load(f)
    if not isinstance(records, list):
        raise ValueError(f"{raw_path}: expected a JSON array of records")

    return _build_session(session, records)


def _build_session(session: Session, records: list[dict]) -> Session:
    """Reconstruct turns and tool calls from raw records.

    Shared by the live-`.jsonl` and archived-`raw.json` entry points so both
    produce byte-identical renderings of the same conversation.
    """
    session.raw_records = records

    turns: list[Turn] = []
    for rec in records:
        rtype = rec.get("type")
        if rtype == "ai-title" and rec.get("aiTitle"):
            session.ai_titles.append(rec["aiTitle"])
        elif rtype == "last-prompt":
            session.last_prompt = rec.get("lastPrompt")

        if rec.get("gitBranch") and not session.git_branch:
            session.git_branch = rec["gitBranch"]
        if rec.get("cwd") and not session.project_cwd:
            session.project_cwd = rec["cwd"]

        if rtype == "system" and rec.get("subtype") == "compact_boundary":
            turns.append(
                Turn(
                    uuid=rec.get("uuid", ""),
                    parent_uuid=rec.get("parentUuid"),
                    session_id=session.session_id,
                    role="system",
                    timestamp=rec.get("timestamp", ""),
                    is_meta=True,
                    is_sidechain=bool(rec.get("isSidechain")),
                    blocks=[{"kind": "text", "text": rec.get("content") or "Conversation compacted"}],
                    raw=rec,
                )
            )
            continue

        if rtype not in ("user", "assistant"):
            continue

        message = rec.get("message") or {}
        blocks = _normalize_blocks(message.get("content"))
        turns.append(
            Turn(
                uuid=rec.get("uuid", ""),
                parent_uuid=rec.get("parentUuid"),
                session_id=session.session_id,
                role=rec.get("type"),
                timestamp=rec.get("timestamp", ""),
                is_meta=bool(rec.get("isMeta")),
                is_sidechain=bool(rec.get("isSidechain")),
                blocks=blocks,
                tool_use_result=rec.get("toolUseResult"),
                git_branch=rec.get("gitBranch"),
                cwd=rec.get("cwd"),
                is_compact_summary=bool(rec.get("isCompactSummary")),
                raw=rec,
            )
        )

    # Chronological reconstruction. Python's sort is stable, so entries that
    # share a timestamp (or lack one) keep their original file order.
    turns.sort(key=lambda t: t.timestamp or "")
    _fix_local_parent_order(turns)
    session.turns = turns

    session.tool_calls = _match_tool_calls(session)
    return session


def _fix_local_parent_order(turns: list[Turn]) -> None:
    """Synthetic records (e.g. a compact-boundary marker and the summary
    turn injected right after it) can carry timestamps a few ms out of
    causal order, which timestamp-sort alone would render backwards. Where
    a turn ends up immediately before its own parent, swap them — the
    parentUuid chain is the authoritative order, the clock isn't.
    """
    changed = True
    guard = 0
    while changed and guard < len(turns):
        changed = False
        guard += 1
        for i in range(len(turns) - 1):
            child, parent = turns[i], turns[i + 1]
            if child.parent_uuid == parent.uuid:
                turns[i], turns[i + 1] = parent, child
                changed = True


def _match_tool_calls(session: Session) -> list[ToolCall]:
    pending: dict[str, ToolCall] = {}
    ordered: list[ToolCall] = []

    for turn in session.turns:
        if turn.role == "assistant":
            for block in turn.blocks:
                if block.get("kind") != "tool_use":
                    continue
                tc = ToolCall(
                    session_id=session.session_id,
                    tool_use_id=block.get("id") or "",
                    name=block.get("name") or "unknown",
                    input=block.get("input") or {},
                    call_timestamp=turn.timestamp,
                    caller=block.get("caller", "direct"),
                    project_cwd=turn.cwd or session.project_cwd,
                )
                ordered.append(tc)
                if tc.tool_use_id:
                    pending[tc.tool_use_id] = tc
        else:
            result_blocks = [b for b in turn.blocks if b.get("kind") == "tool_result"]
            single_structured = turn.tool_use_result if len(result_blocks) == 1 else None
            for block in result_blocks:
                tc = pending.get(block.get("tool_use_id"))
                if not tc:
                    continue
                tc.result_text = block.get("text", "")
                tc.result_is_error = bool(block.get("is_error"))
                tc.result_timestamp = turn.timestamp
                tc.tool_use_result = single_structured

    return ordered
