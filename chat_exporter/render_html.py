from __future__ import annotations

import json

from .markdown_lite import render_markdown
from .models import Session, turn_kind
from .theme import THEME_TOGGLE_BUTTON, THEME_TOGGLE_JS, head
from .util import fmt_duration, html_escape, truncate

TEXT_LIMIT = 8000
THINKING_LIMIT = 3000
RESULT_LIMIT = 3000
INPUT_LIMIT = 2000

# Tools whose first argument is the interesting part, shown in the collapsed
# summary so a reader can scan a long session without expanding anything.
_SUMMARY_FIELD = {
    "Bash": "description",
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
    "Glob": "pattern",
    "Grep": "pattern",
    "WebFetch": "url",
    "WebSearch": "query",
    "Task": "description",
    "Skill": "skill",
}

_CSS = """
body { padding: 0 0 6rem; }

.doc { max-width: 860px; margin: 0 auto; padding: 0 1.25rem; }

/* Inside the browser shell the frame already shows the title and a theme
   toggle, so the page's own masthead would be a second copy of both. */
html.embedded .masthead { display: none; }
html.embedded .hero { padding-top: 1.4rem; }

.masthead {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--paper) 88%, transparent);
  backdrop-filter: saturate(1.6) blur(12px);
  border-bottom: 1px solid var(--line);
}
.masthead-inner {
  max-width: 860px; margin: 0 auto; padding: .7rem 1.25rem;
  display: flex; align-items: center; gap: .75rem;
}
.masthead h1 {
  font-size: 14.5px; font-weight: 600; margin: 0; flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; letter-spacing: -.005em;
}

.hero { padding: 2.2rem 0 1.4rem; border-bottom: 1px solid var(--line); margin-bottom: 1.6rem; }
.hero h2 {
  font-size: 25px; line-height: 1.25; margin: 0 0 .85rem;
  font-weight: 640; letter-spacing: -.02em;
}
.facts { display: flex; flex-wrap: wrap; gap: .4rem; }
.facts .pill strong { color: var(--ink); font-weight: 600; }
.src { margin-top: .85rem; }

.turn { display: flex; gap: .85rem; margin: 0 0 1.5rem; scroll-margin-top: 4.5rem; }
.gutter { flex: none; width: 30px; display: flex; flex-direction: column; align-items: center; gap: .4rem; }
.avatar {
  width: 30px; height: 30px; border-radius: 9px; flex: none;
  display: grid; place-items: center;
  font-size: 10.5px; font-weight: 700; letter-spacing: .02em;
  border: 1px solid transparent;
}
.rail { width: 2px; flex: 1; border-radius: 2px; background: var(--line-soft); min-height: 4px; }
.body { flex: 1; min-width: 0; padding-top: 3px; }

.turn-head {
  display: flex; align-items: baseline; gap: .5rem; flex-wrap: wrap;
  font-size: 12px; color: var(--ink-faint); margin-bottom: .35rem;
}
.turn-head .who { font-weight: 650; font-size: 12.5px; letter-spacing: .01em; }
.turn-head .anchor { color: var(--ink-faint); opacity: 0; transition: opacity .15s; }
.turn:hover .turn-head .anchor { opacity: 1; }

/* --- lanes -------------------------------------------------------------
   Human input is the thing you scan for, so it gets the only filled card.
   Claude's prose sits on the page unadorned. Machine output (tool calls and
   their results) is muted and monospaced so it never reads as either. */

.role-user .avatar    { background: var(--user); color: #fff; border-color: var(--user); }
.role-user .who       { color: var(--user); }
.role-user .rail      { background: var(--user-line); }
.role-user .body {
  background: var(--user-bg);
  border: 1px solid var(--user-line);
  border-left: 3px solid var(--user);
  border-radius: var(--radius);
  padding: .55rem .9rem .7rem;
}
.role-user .prose { font-size: 15px; }

.role-assistant .avatar { background: var(--assistant-bg); color: var(--assistant); border-color: var(--assistant-line); }
.role-assistant .who  { color: var(--assistant); }
.role-assistant .rail { background: var(--assistant-line); }

.role-system .avatar  { background: var(--system-bg); color: var(--system); border-color: var(--system-line); }
.role-system .who     { color: var(--system); }
.role-system .rail    { background: var(--system-line); }
.role-system .body    { opacity: .85; }
.role-system .prose   { font-size: 13.5px; color: var(--ink-soft); }

.role-tool .avatar {
  background: var(--surface-2); color: var(--ink-faint);
  border-color: var(--line); font-family: var(--mono); font-size: 11px;
}
.role-tool .who  { color: var(--ink-faint); font-weight: 600; }
.role-tool .rail { background: var(--line-soft); }

.muted-note { margin: .5rem 0; color: var(--ink-faint); font-size: 13px; }
.result-sep {
  margin: .75rem 0 .1rem; font-size: 10px; font-weight: 700;
  letter-spacing: .07em; text-transform: uppercase; color: var(--ink-faint);
}
details.fold.tool > summary .label { font-family: var(--mono); font-size: 11.5px; }

.prose > :first-child { margin-top: 0; }
.prose > :last-child { margin-bottom: 0; }
.prose p { margin: .65rem 0; }
.prose h1, .prose h2, .prose h3, .prose h4, .prose h5, .prose h6 {
  margin: 1.25rem 0 .5rem; line-height: 1.3; font-weight: 640; letter-spacing: -.01em;
}
.prose h1 { font-size: 19px; } .prose h2 { font-size: 17px; }
.prose h3 { font-size: 15.5px; } .prose h4, .prose h5, .prose h6 { font-size: 14.5px; }
.prose ul, .prose ol { margin: .6rem 0; padding-left: 1.35rem; }
.prose li { margin: .22rem 0; }
.prose blockquote {
  margin: .8rem 0; padding: .1rem 0 .1rem .9rem;
  border-left: 2.5px solid var(--line); color: var(--ink-soft);
}
.prose strong { font-weight: 640; color: var(--ink); }
.table-wrap { overflow-x: auto; margin: .8rem 0; }
.prose table { border-collapse: collapse; font-size: 13px; width: 100%; }
.prose th, .prose td {
  border: 1px solid var(--line); padding: .38rem .6rem; text-align: left; vertical-align: top;
}
.prose th { background: var(--surface); font-weight: 620; }
.prose img { max-width: 100%; height: auto; }

details.fold {
  margin: .55rem 0; border: 1px solid var(--line); border-radius: var(--radius-sm);
  background: var(--surface); overflow: hidden;
}
details.fold > summary {
  cursor: pointer; list-style: none; padding: .45rem .7rem;
  display: flex; align-items: center; gap: .5rem;
  font-size: 12.5px; color: var(--ink-soft);
  transition: background .12s;
}
details.fold > summary::-webkit-details-marker { display: none; }
details.fold > summary:hover { background: var(--surface-2); }
details.fold > summary .chev { flex: none; width: 12px; height: 12px; transition: transform .15s; color: var(--ink-faint); }
details.fold[open] > summary .chev { transform: rotate(90deg); }
details.fold > summary .label { font-weight: 620; color: var(--ink); letter-spacing: .01em; }
details.fold > summary .hint {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: var(--mono); font-size: 11.5px; color: var(--ink-faint);
}
.fold-body { padding: .1rem .7rem .55rem; border-top: 1px solid var(--line-soft); }
.fold-body pre { margin: .55rem 0; }
.fold-body > :first-child { margin-top: .55rem; }

details.thinking { background: transparent; border-style: dashed; }
details.thinking > summary .label { color: var(--ink-faint); font-style: italic; font-weight: 500; }
details.thinking .fold-body { color: var(--ink-soft); font-size: 14px; }

.dot { width: 6px; height: 6px; border-radius: 99px; flex: none; background: var(--ok); }
.dot.bad { background: var(--err); }
details.err { border-color: color-mix(in srgb, var(--err) 35%, var(--line)); background: var(--err-bg); }

.diff-del { color: var(--err); }
.diff-add { color: var(--ok); }

.warnings { border: 1px solid var(--line); border-left: 3px solid var(--system); border-radius: var(--radius-sm);
  background: var(--system-bg); padding: .7rem 1rem; margin-top: 2rem; font-size: 13px; }
.warnings h3 { margin: 0 0 .4rem; font-size: 13px; }
.warnings ul { margin: 0; padding-left: 1.1rem; }

.totop {
  position: fixed; right: 1.1rem; bottom: 1.1rem; z-index: 30;
  width: 34px; height: 34px; border-radius: 10px; cursor: pointer;
  display: grid; place-items: center;
  background: var(--surface); color: var(--ink-soft);
  border: 1px solid var(--line); box-shadow: var(--shadow);
  opacity: 0; pointer-events: none; transition: opacity .18s;
}
.totop.show { opacity: 1; pointer-events: auto; }
.totop:hover { color: var(--ink); background: var(--surface-2); }

@media (max-width: 620px) {
  .gutter { width: 24px; }
  .avatar { width: 24px; height: 24px; border-radius: 7px; font-size: 9px; }
  .hero h2 { font-size: 21px; }
}
"""

_CHEV = ('<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>')


_LANE_LABEL = {
    "user": "You",
    "assistant": "Claude",
    "system": "System",
    "tool": "Tool result",
}
_LANE_INITIALS = {"user": "YOU", "assistant": "AI", "system": "SYS", "tool": "&gt;_"}


def _lane_label(turn, kind: str) -> str:
    label = _LANE_LABEL[kind]
    if kind == "system" and turn.is_compact_summary:
        label = "System · compacted summary"
    elif kind == "system" and turn.is_meta:
        label = "System · injected context"
    return f"Subagent · {label}" if turn.is_sidechain else label


def _fold(label: str, hint: str, inner: str, *, cls: str = "", open_: bool = False, dot: str = "") -> str:
    attrs = f' class="fold {cls}"'.replace("  ", " ") if cls else ' class="fold"'
    return (
        f"<details{attrs}{' open' if open_ else ''}>"
        f"<summary>{_CHEV}{dot}<span class=\"label\">{label}</span>"
        f'<span class="hint">{hint}</span></summary>'
        f'<div class="fold-body">{inner}</div></details>'
    )


def _tool_summary_hint(name: str, inp: dict) -> str:
    field = _SUMMARY_FIELD.get(name)
    value = inp.get(field) if field else None
    if not value and name == "Bash":
        value = inp.get("command", "")
    if not value:
        for key in ("file_path", "path", "query", "prompt", "pattern"):
            if inp.get(key):
                value = inp[key]
                break
    text = str(value or "")
    return html_escape(truncate(text.replace("\n", " "), 140))


def _result_fold(text: str, is_error: bool) -> str:
    """Standalone fold for a tool result with no matching call."""
    text = (text or "").strip()
    inner = (
        f"<pre><code>{html_escape(truncate(text, RESULT_LIMIT))}</code></pre>"
        if text else '<p class="muted-note">(no output)</p>'
    )
    return _fold(
        "Result · error" if is_error else "Result",
        "",
        inner,
        cls="err" if is_error else "",
        dot=f'<span class="dot{" bad" if is_error else ""}"></span>',
    )


def _tool_use_html(block: dict, call=None) -> str:
    """One fold containing a tool invocation and, when matched, its output."""
    name = block.get("name") or "unknown"
    inp = block.get("input") or {}
    parts: list[str] = []

    if name == "Bash":
        if inp.get("description"):
            parts.append(f'<p class="muted-note">{html_escape(inp["description"])}</p>')
        parts.append(f"<pre data-lang=\"bash\"><code>{html_escape(inp.get('command', ''))}</code></pre>")
    elif name == "Edit":
        old = html_escape(truncate(str(inp.get("old_string", "")), INPUT_LIMIT))
        new = html_escape(truncate(str(inp.get("new_string", "")), INPUT_LIMIT))
        parts.append(
            f'<pre><code><span class="diff-del">--- old\n{old}</span>\n\n'
            f'<span class="diff-add">+++ new\n{new}</span></code></pre>'
        )
    elif name == "Write":
        content = truncate(str(inp.get("content", "")), INPUT_LIMIT)
        parts.append(f"<pre><code>{html_escape(content)}</code></pre>")
    else:
        dumped = truncate(json.dumps(inp, ensure_ascii=False, indent=2), INPUT_LIMIT)
        parts.append(f'<pre data-lang="json"><code>{html_escape(dumped)}</code></pre>')

    is_error = False
    if call is not None:
        is_error = bool(call.result_is_error)
        result = (call.result_text or "").strip()
        parts.append('<div class="result-sep">Output</div>')
        if result:
            parts.append(f"<pre><code>{html_escape(truncate(result, RESULT_LIMIT))}</code></pre>")
        else:
            parts.append('<p class="muted-note">(no output)</p>')

    dot = f'<span class="dot{" bad" if is_error else ""}"></span>' if call is not None else ""
    return _fold(
        html_escape(name),
        _tool_summary_hint(name, inp),
        "".join(parts),
        cls="tool" + (" err" if is_error else ""),
        dot=dot,
    )


def render_session_html(session: Session) -> str:
    n_user, n_assistant = session.counts
    title = html_escape(session.title)

    facts = [
        ("Project", session.project_cwd or session.project_dir),
        ("Started", session.start_ts or "unknown"),
        ("Duration", fmt_duration(session.start_ts, session.end_ts)),
        ("Turns", f"{n_user + n_assistant}"),
        ("Tools", str(len(session.tool_calls))),
    ]
    if session.git_branch:
        facts.insert(1, ("Branch", session.git_branch))

    body: list[str] = ['<div class="doc">', '<header class="hero">', f"<h2>{title}</h2>", '<div class="facts">']
    for key, value in facts:
        body.append(f'<span class="pill">{html_escape(key)} <strong>{html_escape(str(value))}</strong></span>')
    body.append("</div>")
    body.append(f'<div class="mono-sm src">{html_escape(session.session_id)}</div>')
    body.append("</header>")

    # Results are rendered inside the tool call that produced them, so the
    # machine-output turns that carry them collapse away entirely.
    by_id = {tc.tool_use_id: tc for tc in session.tool_calls if tc.tool_use_id}
    inlined: set[str] = set()

    for turn in session.turns:
        kind_of_turn = turn_kind(turn)
        blocks: list[str] = []

        for block in turn.blocks:
            kind = block.get("kind")
            if kind == "text":
                text = (block.get("text") or "").strip()
                if text:
                    blocks.append(f'<div class="prose">{render_markdown(truncate(text, TEXT_LIMIT))}</div>')
            elif kind == "thinking":
                text = (block.get("text") or "").strip()
                if text:
                    inner = f'<div class="prose">{render_markdown(truncate(text, THINKING_LIMIT))}</div>'
                    blocks.append(_fold("Thinking", "", inner, cls="thinking"))
            elif kind == "tool_use":
                call = by_id.get(block.get("id") or "")
                blocks.append(_tool_use_html(block, call))
                if call:
                    inlined.add(call.tool_use_id)
            elif kind == "tool_result":
                # Already shown under its call; only orphans render standalone.
                if block.get("tool_use_id") in inlined:
                    continue
                blocks.append(_result_fold(block.get("text") or "", bool(block.get("is_error"))))

        if not blocks:
            continue

        uuid = html_escape(turn.uuid)
        body.append(f'<article class="turn role-{kind_of_turn}" id="{uuid}">')
        body.append(
            f'<div class="gutter"><div class="avatar">{_LANE_INITIALS[kind_of_turn]}</div>'
            '<div class="rail"></div></div>'
        )
        body.append('<div class="body">')
        body.append(
            f'<div class="turn-head"><span class="who">{html_escape(_lane_label(turn, kind_of_turn))}</span>'
            f"<span>{html_escape(turn.timestamp)}</span>"
            f'<a class="anchor" href="#{uuid}" title="Link to this turn">#</a></div>'
        )
        body.extend(blocks)
        body.append("</div></article>")

    if session.parse_warnings:
        body.append('<div class="warnings"><h3>Parse warnings</h3><ul>')
        for warning in session.parse_warnings:
            body.append(f"<li>{html_escape(warning)}</li>")
        body.append("</ul></div>")

    body.append("</div>")

    masthead = (
        '<div class="masthead"><div class="masthead-inner">'
        f"<h1>{title}</h1>{THEME_TOGGLE_BUTTON}"
        "</div></div>"
    )
    totop = ('<button class="totop" id="toTop" title="Back to top" aria-label="Back to top">'
             '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" '
             'stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>')

    script = f"""<script>{THEME_TOGGLE_JS}
(function () {{
  var b = document.getElementById('toTop');
  addEventListener('scroll', function () {{ b.classList.toggle('show', scrollY > 600); }}, {{passive:true}});
  b.addEventListener('click', function () {{ scrollTo({{top:0, behavior:'smooth'}}); }});
}})();
</script>"""

    # Set before first paint so the masthead never flashes in the frame.
    embed_check = (
        "<script>try{if(window.self!==window.top)"
        "document.documentElement.className+=' embedded';}catch(e){}</script>"
    )

    return (
        f"<!doctype html><html><head>{head(title, _CSS)}{embed_check}</head>"
        f"<body>{masthead}{''.join(body)}{totop}{script}</body></html>"
    )
