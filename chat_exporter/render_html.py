from __future__ import annotations

import json

from .models import Session
from .util import fmt_duration, html_escape, truncate

TEXT_LIMIT = 8000
THINKING_LIMIT = 3000
RESULT_LIMIT = 3000
INPUT_LIMIT = 2000

_CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card: #f9fafb; --code-bg: #f3f4f6; --accent: #2563eb;
  --user-bg: #eef2ff; --assistant-bg: #f0fdf4; --system-bg: #fafafa;
  --error: #dc2626; --ok: #059669;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --fg: #e5e7eb; --muted: #9ca3af; --border: #2a2e37;
    --card: #171a21; --code-bg: #1b1f27; --accent: #60a5fa;
    --user-bg: #16213a; --assistant-bg: #132018; --system-bg: #1a1a1a;
    --error: #f87171; --ok: #34d399;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 980px; margin: 0 auto; padding: 2rem 1.25rem 5rem; line-height: 1.55;
}
h1 { font-size: 1.6rem; }
table.meta { border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
table.meta td { border: 1px solid var(--border); padding: 0.35rem 0.7rem; }
table.meta td:first-child { color: var(--muted); white-space: nowrap; }
.turn { border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.15rem; margin: 1rem 0; background: var(--card); }
.turn.role-user { background: var(--user-bg); }
.turn.role-assistant { background: var(--assistant-bg); }
.turn.role-system { background: var(--system-bg); }
.turn-head { font-size: 0.8rem; color: var(--muted); margin-bottom: 0.6rem; }
.turn-head .role { font-weight: 600; color: var(--fg); }
pre { background: var(--code-bg); border-radius: 8px; padding: 0.75rem 0.9rem; overflow-x: auto; font-size: 0.85rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
details { margin: 0.6rem 0; }
summary { cursor: pointer; color: var(--accent); font-size: 0.85rem; }
.tool-name { font-weight: 600; }
.result-ok { color: var(--ok); }
.result-error { color: var(--error); }
.block { margin: 0.6rem 0; }
hr { border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }
a { color: var(--accent); }
"""


def _role_label(turn) -> str:
    prefix = "Subagent " if turn.is_sidechain else ""
    if turn.role == "system":
        return f"{prefix}System"
    if turn.is_compact_summary:
        return f"{prefix}System (Compacted Summary)"
    if turn.is_meta:
        return f"{prefix}System"
    return f"{prefix}{'User' if turn.role == 'user' else 'Assistant'}"


def _role_class(turn) -> str:
    if turn.role == "system" or turn.is_meta or turn.is_compact_summary:
        return "system"
    return "user" if turn.role == "user" else "assistant"


def _tool_use_html(block: dict) -> str:
    name = html_escape(block.get("name") or "unknown")
    inp = block.get("input") or {}
    parts = [f'<div class="block"><span class="tool-name">Tool call: {name}</span>']

    if block.get("name") == "Bash":
        if inp.get("description"):
            parts.append(f"<div><em>{html_escape(inp['description'])}</em></div>")
        parts.append(f"<pre><code>{html_escape(inp.get('command', ''))}</code></pre>")
    elif block.get("name") == "Edit":
        parts.append(f"<div>File: <code>{html_escape(str(inp.get('file_path', '')))}</code></div>")
        old = truncate(str(inp.get("old_string", "")), INPUT_LIMIT)
        new = truncate(str(inp.get("new_string", "")), INPUT_LIMIT)
        parts.append(f"<pre><code>--- old\n{html_escape(old)}\n\n+++ new\n{html_escape(new)}</code></pre>")
    elif block.get("name") == "Write":
        parts.append(f"<div>File: <code>{html_escape(str(inp.get('file_path', '')))}</code></div>")
        content = truncate(str(inp.get("content", "")), INPUT_LIMIT)
        parts.append(f"<pre><code>{html_escape(content)}</code></pre>")
    else:
        dumped = truncate(json.dumps(inp, ensure_ascii=False, indent=2), INPUT_LIMIT)
        parts.append(f"<pre><code>{html_escape(dumped)}</code></pre>")

    parts.append("</div>")
    return "".join(parts)


def render_session_html(session: Session) -> str:
    n_user = sum(1 for t in session.turns if t.role == "user")
    n_assistant = sum(1 for t in session.turns if t.role == "assistant")

    body = []
    body.append(f"<h1>{html_escape(session.title)}</h1>")
    body.append('<table class="meta">')
    rows = [
        ("Session ID", session.session_id),
        ("Project", session.project_cwd or session.project_dir),
        ("Git branch", session.git_branch or ""),
        ("Started", session.start_ts or ""),
        ("Ended", session.end_ts or ""),
        ("Duration", fmt_duration(session.start_ts, session.end_ts)),
        ("Turns", f"{n_user} user / {n_assistant} assistant"),
        ("Tool calls", str(len(session.tool_calls))),
        ("Source", session.file_path),
    ]
    for k, v in rows:
        body.append(f"<tr><td>{html_escape(k)}</td><td>{html_escape(str(v))}</td></tr>")
    body.append("</table><hr/>")

    for turn in session.turns:
        role_class = _role_class(turn)
        label = html_escape(_role_label(turn))
        body.append(f'<div class="turn role-{role_class}" id="{html_escape(turn.uuid)}">')
        body.append(
            f'<div class="turn-head"><span class="role">{label}</span> · {html_escape(turn.timestamp)} '
            f'· <code>{html_escape(turn.uuid)}</code></div>'
        )
        for block in turn.blocks:
            kind = block.get("kind")
            if kind == "text":
                text = block.get("text", "").strip()
                if text:
                    body.append(
                        f'<div class="block"><pre><code>{html_escape(truncate(text, TEXT_LIMIT))}</code></pre></div>'
                    )
            elif kind == "thinking":
                text = block.get("text", "").strip()
                if text:
                    body.append(
                        "<details><summary>Thinking</summary>"
                        f'<pre><code>{html_escape(truncate(text, THINKING_LIMIT))}</code></pre></details>'
                    )
            elif kind == "tool_use":
                body.append(_tool_use_html(block))
            elif kind == "tool_result":
                text = block.get("text", "").strip()
                status_class = "result-error" if block.get("is_error") else "result-ok"
                status_text = "error" if block.get("is_error") else "ok"
                body.append(
                    f'<div class="block"><span class="{status_class}">Tool result ({status_text}):</span>'
                    f'<pre><code>{html_escape(truncate(text, RESULT_LIMIT))}</code></pre></div>'
                )
        body.append("</div>")

    if session.parse_warnings:
        body.append("<hr/><h3>Parse warnings</h3><ul>")
        for w in session.parse_warnings:
            body.append(f"<li>{html_escape(w)}</li>")
        body.append("</ul>")

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html_escape(session.title)}</title>"
        f"<style>{_CSS}</style></head><body>{''.join(body)}</body></html>"
    )
