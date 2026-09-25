from __future__ import annotations

import json

from .models import Session
from .util import fmt_duration, truncate

SEARCH_SNIPPET_LIMIT = 4000


def session_index_entry(session: Session, rel_md: str, rel_html: str, rel_raw: str) -> dict:
    n_user = sum(1 for t in session.turns if t.role == "user")
    n_assistant = sum(1 for t in session.turns if t.role == "assistant")
    return {
        "session_id": session.session_id,
        "project_dir": session.project_dir,
        "project_cwd": session.project_cwd,
        "title": session.title,
        "git_branch": session.git_branch,
        "started": session.start_ts,
        "ended": session.end_ts,
        "duration": fmt_duration(session.start_ts, session.end_ts),
        "user_turns": n_user,
        "assistant_turns": n_assistant,
        "tool_calls": len(session.tool_calls),
        "last_prompt": truncate(session.last_prompt or "", 300),
        "markdown_path": rel_md,
        "html_path": rel_html,
        "raw_json_path": rel_raw,
    }


def render_session_index_markdown(entries: list[dict]) -> str:
    lines = ["# Session Index", "", f"{len(entries)} sessions.", ""]
    lines.append("| Started | Title | Project | Duration | Turns | Tools | Links |")
    lines.append("|---|---|---|---|---|---|---|")
    for e in sorted(entries, key=lambda x: x["started"] or "", reverse=True):
        turns = f"{e['user_turns']}u/{e['assistant_turns']}a"
        links = f"[md]({e['markdown_path']}) · [html]({e['html_path']})"
        title = (e["title"] or "").replace("|", "\\|")
        project = (e["project_cwd"] or e["project_dir"]).replace("|", "\\|")
        lines.append(
            f"| {e['started']} | {title} | `{project}` | {e['duration']} | {turns} | {e['tool_calls']} | {links} |"
        )
    return "\n".join(lines)


def search_records(session: Session, rel_html: str) -> list[dict]:
    records: list[dict] = []

    def add(uuid, ts, role, kind, text):
        text = (text or "").strip()
        if not text:
            return
        records.append(
            {
                "session_id": session.session_id,
                "title": session.title,
                "project": session.project_cwd or session.project_dir,
                "uuid": uuid,
                "timestamp": ts,
                "role": role,
                "kind": kind,
                "text": truncate(text, SEARCH_SNIPPET_LIMIT),
                "url": f"{rel_html}#{uuid}",
            }
        )

    for turn in session.turns:
        for block in turn.blocks:
            if block.get("kind") == "text":
                add(turn.uuid, turn.timestamp, turn.role, "text", block.get("text"))

    for tc in session.tool_calls:
        if tc.name == "Bash":
            add(tc.tool_use_id, tc.call_timestamp, "assistant", "bash", tc.input.get("command"))
        elif tc.name in ("Edit", "Write", "MultiEdit"):
            path = tc.input.get("file_path", "")
            add(tc.tool_use_id, tc.call_timestamp, "assistant", "file_mod", f"[{tc.name}] {path}")

    return records


def build_browser_html(entries: list[dict]) -> str:
    """Two-pane browser: sidebar of session titles (newest first), main pane
    is an <iframe> pointed at the selected session's conversation.html.

    `entries` items need: session_id, title, project, started, duration,
    tool_calls, turns, html_path (root-relative, e.g. "sessions/.../conversation.html").
    """
    ordered = sorted(entries, key=lambda e: e["started"] or "", reverse=True)
    payload = json.dumps(ordered, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Claude Code Chat Archive</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#6b7280; --border:#e5e7eb; --card:#f9fafb; --accent:#2563eb; --active:#dbeafe; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f1115; --fg:#e5e7eb; --muted:#9ca3af; --border:#2a2e37; --card:#171a21; --accent:#60a5fa; --active:#1e3a5f; }}
}}
* {{ box-sizing: border-box; }}
html, body {{ height:100%; margin:0; }}
body {{ display:flex; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
#sidebar {{ width:320px; min-width:320px; border-right:1px solid var(--border); overflow-y:auto; display:flex; flex-direction:column; }}
#sidebar-head {{ padding:0.9rem 1rem 0.6rem; border-bottom:1px solid var(--border); }}
#sidebar-head h1 {{ font-size:1rem; margin:0 0 0.6rem; }}
#sidebar-head a {{ font-size:0.78rem; color:var(--accent); text-decoration:none; }}
#filter {{ width:100%; padding:0.45rem 0.6rem; font-size:0.85rem; border-radius:6px; border:1px solid var(--border);
  background:var(--card); color:var(--fg); margin-top:0.5rem; }}
#list {{ list-style:none; margin:0; padding:0; overflow-y:auto; }}
#list li {{ padding:0.65rem 1rem; border-bottom:1px solid var(--border); cursor:pointer; }}
#list li:hover {{ background:var(--card); }}
#list li.active {{ background:var(--active); }}
#list .title {{ font-size:0.85rem; font-weight:600; margin-bottom:0.2rem; }}
#list .meta {{ font-size:0.72rem; color:var(--muted); }}
#main {{ flex:1; display:flex; flex-direction:column; min-width:0; }}
#mainbar {{ padding:0.6rem 1rem; border-bottom:1px solid var(--border); font-size:0.8rem; color:var(--muted);
  display:flex; justify-content:space-between; align-items:center; gap:1rem; }}
#mainbar a {{ color:var(--accent); text-decoration:none; white-space:nowrap; }}
#frame {{ flex:1; border:none; width:100%; background:var(--bg); }}
#empty {{ margin:2rem; color:var(--muted); }}
</style></head><body>
<div id="sidebar">
  <div id="sidebar-head">
    <h1>Claude Code Chats</h1>
    <a href="index/search.html">Full-text search &rarr;</a> &nbsp;·&nbsp;
    <a href="index/session_index.md">Session index &rarr;</a>
    <input id="filter" type="search" placeholder="Filter by title or project...">
  </div>
  <ul id="list"></ul>
</div>
<div id="main">
  <div id="mainbar"><span id="mainbar-text"></span><a id="mainbar-open" href="#" target="_blank">open in new tab &#8599;</a></div>
  <iframe id="frame"></iframe>
</div>
<script>
const SESSIONS = {payload};
const list = document.getElementById('list');
const frame = document.getElementById('frame');
const filter = document.getElementById('filter');
const mainbarText = document.getElementById('mainbar-text');
const mainbarOpen = document.getElementById('mainbar-open');

function esc(s) {{
  return (s || '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
}}

function select(session, el) {{
  document.querySelectorAll('#list li.active').forEach(n => n.classList.remove('active'));
  if (el) el.classList.add('active');
  frame.src = session.html_path;
  mainbarText.textContent = session.title + '  ·  ' + session.project + '  ·  ' + session.started;
  mainbarOpen.href = session.html_path;
}}

function renderList(filterText) {{
  const t = (filterText || '').trim().toLowerCase();
  const items = SESSIONS.filter(s => !t || s.title.toLowerCase().includes(t) || s.project.toLowerCase().includes(t));
  list.innerHTML = '';
  items.forEach((s, i) => {{
    const li = document.createElement('li');
    li.innerHTML = `<div class="title">${{esc(s.title)}}</div>` +
      `<div class="meta">${{esc(s.started)}} &middot; ${{esc(s.duration)}} &middot; ${{s.turns}} turns &middot; ${{s.tool_calls}} tools</div>`;
    li.addEventListener('click', () => select(s, li));
    list.appendChild(li);
    if (i === 0 && !t) select(s, li);
  }});
  if (!items.length) {{
    frame.removeAttribute('src');
    mainbarText.textContent = 'No sessions match "' + filterText + '"';
  }}
}}

filter.addEventListener('input', () => renderList(filter.value));
renderList('');
</script>
</body></html>"""


def build_search_html(search_index: list[dict]) -> str:
    # Escape "</" so a transcript containing a literal "</script>" (e.g. one
    # discussing HTML) can't prematurely close the embedding <script> tag.
    payload = json.dumps(search_index, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Claude Code Chat Search</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#6b7280; --border:#e5e7eb; --card:#f9fafb; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f1115; --fg:#e5e7eb; --muted:#9ca3af; --border:#2a2e37; --card:#171a21; --accent:#60a5fa; }}
}}
* {{ box-sizing: border-box; }}
body {{ background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  max-width: 900px; margin: 0 auto; padding: 2rem 1.25rem 5rem; }}
input {{ width:100%; padding:0.7rem 0.9rem; font-size:1rem; border-radius:8px; border:1px solid var(--border);
  background:var(--card); color:var(--fg); }}
.result {{ border:1px solid var(--border); border-radius:8px; padding:0.75rem 1rem; margin:0.75rem 0; background:var(--card); }}
.result .head {{ font-size:0.8rem; color:var(--muted); margin-bottom:0.35rem; }}
.result a {{ color: var(--accent); text-decoration:none; }}
.result pre {{ white-space:pre-wrap; word-break:break-word; margin:0.4rem 0 0; font-size:0.85rem; }}
mark {{ background:#fde68a; color:#1a1a1a; }}
#count {{ color:var(--muted); font-size:0.85rem; margin:0.5rem 0 1rem; }}
</style></head><body>
<h1>Claude Code Chat Search</h1>
<input id="q" type="search" placeholder="Search across all archived sessions..." autofocus>
<div id="count"></div>
<div id="results"></div>
<script>
const DATA = {payload};
const q = document.getElementById('q');
const results = document.getElementById('results');
const count = document.getElementById('count');

function esc(s) {{
  return s.replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
}}
function highlight(text, term) {{
  if (!term) return esc(text);
  const idx = text.toLowerCase().indexOf(term.toLowerCase());
  if (idx === -1) return esc(text.slice(0, 300));
  const start = Math.max(0, idx - 150);
  const end = Math.min(text.length, idx + term.length + 150);
  const snippet = (start > 0 ? '...' : '') + text.slice(start, end) + (end < text.length ? '...' : '');
  const rel = idx - start;
  return esc(snippet.slice(0, rel)) + '<mark>' + esc(snippet.slice(rel, rel + term.length)) + '</mark>' + esc(snippet.slice(rel + term.length));
}}
function render(term) {{
  const t = term.trim().toLowerCase();
  const matches = t ? DATA.filter(r => r.text.toLowerCase().includes(t) || r.title.toLowerCase().includes(t)) : [];
  count.textContent = t ? matches.length + ' results' : 'Type to search ' + DATA.length + ' indexed turns/commands/file-edits.';
  results.innerHTML = matches.slice(0, 200).map(r => `
    <div class="result">
      <div class="head">${{esc(r.title)}} · ${{esc(r.project)}} · ${{esc(r.timestamp)}} · ${{esc(r.role)}}/${{esc(r.kind)}}
        · <a href="${{r.url}}" target="_blank">open</a></div>
      <pre>${{highlight(r.text, term)}}</pre>
    </div>`).join('');
}}
q.addEventListener('input', () => render(q.value));
render('');
</script>
</body></html>"""
