from __future__ import annotations

from collections import Counter, defaultdict

from .util import truncate


def render_bash_commands_markdown(records: list[dict]) -> str:
    lines = ["# Bash Commands", "", f"{len(records)} commands executed across all sessions.", ""]
    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)

    for sid, recs in sorted(by_session.items(), key=lambda kv: kv[1][0]["timestamp"] or ""):
        recs = sorted(recs, key=lambda r: r["timestamp"] or "")
        lines.append(f"## {recs[0]['session_title']} (`{sid}`)")
        lines.append("")
        for r in recs:
            status = "ERROR" if r.get("is_error") else "ok"
            lines.append(f"**{r['timestamp']}** — {status}" + (f" — {r['description']}" if r.get("description") else ""))
            lines.append("```bash")
            lines.append(r["command"] or "")
            lines.append("```")
            out = r.get("stdout") or ""
            if out:
                lines.append("<details><summary>stdout</summary>")
                lines.append("")
                lines.append("```")
                lines.append(truncate(out, 1500))
                lines.append("```")
                lines.append("</details>")
            err = r.get("stderr") or ""
            if err:
                lines.append("<details><summary>stderr</summary>")
                lines.append("")
                lines.append("```")
                lines.append(truncate(err, 1500))
                lines.append("```")
                lines.append("</details>")
            lines.append("")
        lines.append("")
    return "\n".join(lines)


def render_file_modifications_markdown(records: list[dict]) -> str:
    lines = ["# File Modifications", "", f"{len(records)} file-modifying tool calls across all sessions.", ""]

    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_file[r.get("file_path") or "(unknown)"].append(r)

    lines.append("## Files touched")
    lines.append("")
    for path, recs in sorted(by_file.items()):
        lines.append(f"- `{path}` — {len(recs)} change(s)")
    lines.append("")
    lines.append("---")
    lines.append("")

    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)

    for sid, recs in sorted(by_session.items(), key=lambda kv: kv[1][0]["timestamp"] or ""):
        recs = sorted(recs, key=lambda r: r["timestamp"] or "")
        lines.append(f"## {recs[0]['session_title']} (`{sid}`)")
        lines.append("")
        for r in recs:
            status = " (ERROR)" if r.get("is_error") else ""
            lines.append(f"### {r['timestamp']} — {r['action']}{status} — `{r.get('file_path', '')}`")
            if r["action"] == "write":
                lines.append(f"- content length: {r.get('content_length', 0)} chars")
                lines.append("```")
                lines.append(r.get("content_preview", ""))
                lines.append("```")
            elif r["action"] == "edit":
                lines.append("```diff")
                for l in (r.get("old_string_preview") or "").splitlines():
                    lines.append(f"- {l}")
                for l in (r.get("new_string_preview") or "").splitlines():
                    lines.append(f"+ {l}")
                lines.append("```")
            elif r["action"] == "multi_edit":
                lines.append(f"- {r.get('edit_count', 0)} edit(s) in this call")
            elif r["action"].startswith("notebook"):
                lines.append(f"- cell: `{r.get('cell_id', '')}`")
            lines.append("")
        lines.append("")
    return "\n".join(lines)


def render_tool_invocations_markdown(records: list[dict]) -> str:
    lines = ["# Tool Invocations", "", f"{len(records)} tool calls across all sessions.", ""]
    counts = Counter(r["tool_name"] for r in records)
    lines.append("## By tool")
    lines.append("")
    for name, n in counts.most_common():
        lines.append(f"- {name}: {n}")
    lines.append("")
    lines.append("---")
    lines.append("")

    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)

    for sid, recs in sorted(by_session.items(), key=lambda kv: kv[1][0]["call_timestamp"] or ""):
        recs = sorted(recs, key=lambda r: r["call_timestamp"] or "")
        lines.append(f"## {recs[0]['session_title']} (`{sid}`) — {len(recs)} calls")
        lines.append("")
        for r in recs:
            status = " ERROR" if r.get("result_is_error") else ""
            lines.append(f"- `{r['call_timestamp']}` **{r['tool_name']}**{status} ({r['caller']})")
        lines.append("")
    return "\n".join(lines)


def render_architectural_decisions_markdown(records: list[dict]) -> str:
    lines = [
        "# Architectural Decisions",
        "",
        "Heuristically extracted from plan proposals (`ExitPlanMode`), decision-point "
        "questions (`AskUserQuestion`), and decision-language mentions in assistant text. "
        f"{len(records)} candidate entries — review for signal vs. noise.",
        "",
    ]

    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)

    kind_labels = {
        "plan_proposed": "Plan proposed",
        "decision_point_asked": "Decision point (user asked)",
        "mentions_decision_language": "Decision-language mention",
    }

    for sid, recs in sorted(by_session.items(), key=lambda kv: kv[1][0]["timestamp"] or ""):
        recs = sorted(recs, key=lambda r: r["timestamp"] or "")
        lines.append(f"## {recs[0]['session_title']} (`{sid}`)")
        lines.append("")
        for r in recs:
            label = kind_labels.get(r["kind"], r["kind"])
            lines.append(f"### {r['timestamp']} — {label}")
            lines.append("")
            lines.append("> " + r["text"].replace("\n", "\n> "))
            lines.append("")
        lines.append("")
    return "\n".join(lines)
