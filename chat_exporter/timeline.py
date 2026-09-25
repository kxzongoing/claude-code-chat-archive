from __future__ import annotations

from collections import defaultdict

from .models import Session
from .util import truncate


def session_timeline_events(
    session: Session,
    file_mods: list[dict],
    bash_cmds: list[dict],
    decisions: list[dict],
) -> list[dict]:
    events: list[dict] = []

    if session.start_ts:
        events.append(
            {
                "timestamp": session.start_ts,
                "kind": "session_start",
                "session_id": session.session_id,
                "title": session.title,
                "summary": f"Session started: {session.title}",
            }
        )
    if session.end_ts and session.end_ts != session.start_ts:
        events.append(
            {
                "timestamp": session.end_ts,
                "kind": "session_end",
                "session_id": session.session_id,
                "title": session.title,
                "summary": f"Session ended: {session.title}",
            }
        )

    for fm in file_mods:
        events.append(
            {
                "timestamp": fm["timestamp"],
                "kind": "file_modification",
                "session_id": session.session_id,
                "title": session.title,
                "summary": f"{fm['tool']} `{fm.get('file_path', '')}`",
            }
        )

    for bc in bash_cmds:
        cmd = truncate((bc.get("command") or "").splitlines()[0] if bc.get("command") else "", 140)
        events.append(
            {
                "timestamp": bc["timestamp"],
                "kind": "bash_command",
                "session_id": session.session_id,
                "title": session.title,
                "summary": f"`{cmd}`",
            }
        )

    for d in decisions:
        events.append(
            {
                "timestamp": d["timestamp"],
                "kind": "architectural_decision",
                "session_id": session.session_id,
                "title": session.title,
                "summary": truncate(d["text"].splitlines()[0], 160),
            }
        )

    return events


def render_timeline_markdown(events: list[dict]) -> str:
    events = sorted(events, key=lambda e: e["timestamp"] or "")
    by_date: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        date = (e["timestamp"] or "unknown")[:10]
        by_date[date].append(e)

    lines = ["# Project Timeline", "", f"{len(events)} events across all sessions.", ""]
    for date in sorted(by_date.keys()):
        lines.append(f"## {date}")
        lines.append("")
        for e in by_date[date]:
            time = (e["timestamp"] or "")[11:19]
            lines.append(f"- `{time}` **[{e['kind']}]** {e['summary']} _(session: {e['title']})_")
        lines.append("")
    return "\n".join(lines)
