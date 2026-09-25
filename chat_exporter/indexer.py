from __future__ import annotations

import json

from .models import Session
from .theme import THEME_TOGGLE_BUTTON, THEME_TOGGLE_JS, head
from .util import fmt_duration, truncate

SEARCH_SNIPPET_LIMIT = 4000


def session_index_entry(session: Session, rel_md: str, rel_html: str, rel_raw: str) -> dict:
    n_user, n_assistant = session.counts
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


_BROWSER_CSS = """
html, body { height: 100%; overflow: hidden; }
body { display: flex; }

#sidebar {
  width: 328px; flex: none; display: flex; flex-direction: column;
  border-right: 1px solid var(--line); background: var(--surface); min-height: 0;
}
.brand { padding: .85rem .95rem .7rem; display: flex; align-items: center; gap: .6rem; }
.brand-mark {
  width: 26px; height: 26px; flex: none; border-radius: 8px;
  background: linear-gradient(140deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #22d3ee));
  display: grid; place-items: center; color: #fff; font-size: 13px; font-weight: 700;
}
.brand-text { flex: 1; min-width: 0; }
.brand h1 { font-size: 13.5px; font-weight: 650; margin: 0; letter-spacing: -.01em; }
.brand .sub { font-size: 11px; color: var(--ink-faint); }

.searchbox { padding: 0 .95rem .6rem; position: relative; }
.searchbox svg { position: absolute; left: 1.5rem; top: 50%; transform: translateY(-58%); width: 13px; height: 13px; color: var(--ink-faint); pointer-events: none; }
#filter {
  width: 100%; padding: .42rem .6rem .42rem 1.85rem;
  font: inherit; font-size: 12.5px; color: var(--ink);
  background: var(--paper); border: 1px solid var(--line); border-radius: 8px;
}
#filter::placeholder { color: var(--ink-faint); }
#filter:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.searchbox kbd { position: absolute; right: 1.5rem; top: 50%; transform: translateY(-55%); pointer-events: none; }
#filter:focus ~ kbd { display: none; }

.quicklinks { padding: 0 .95rem .6rem; display: flex; gap: .4rem; }
.quicklinks a {
  flex: 1; text-align: center; font-size: 11.5px; padding: .3rem .4rem;
  border: 1px solid var(--line); border-radius: 7px; color: var(--ink-soft); background: var(--paper);
}
.quicklinks a:hover { color: var(--accent); border-color: var(--accent); text-decoration: none; }

#list { flex: 1; overflow-y: auto; list-style: none; margin: 0; padding: 0 .55rem .8rem; min-height: 0; }
.daygroup {
  position: sticky; top: 0; z-index: 2; padding: .7rem .4rem .3rem;
  font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: var(--ink-faint); background: var(--surface);
}
#list li {
  padding: .5rem .55rem; border-radius: 9px; cursor: pointer; margin-bottom: 1px;
  border: 1px solid transparent; transition: background .12s;
}
#list li:hover { background: var(--surface-2); }
#list li.active { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 35%, transparent); }
#list li.active .title { color: var(--accent-ink); }
#list .title {
  font-size: 12.8px; font-weight: 580; line-height: 1.35; margin-bottom: .2rem;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
#list .meta { font-size: 11px; color: var(--ink-faint); display: flex; gap: .45rem; flex-wrap: wrap; }
#list .meta .proj {
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: var(--mono); font-size: 10.5px;
}
.noresults { padding: 1.5rem .8rem; text-align: center; color: var(--ink-faint); font-size: 12.5px; }

#main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--paper); }
#mainbar {
  display: flex; align-items: center; gap: .7rem;
  padding: .55rem .9rem; border-bottom: 1px solid var(--line); background: var(--surface);
}
#mainbar .info { flex: 1; min-width: 0; }
#mainbar .t { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#mainbar .m { font-size: 11px; color: var(--ink-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.iconbtn {
  width: 30px; height: 30px; flex: none; display: grid; place-items: center;
  border: 1px solid var(--line); border-radius: 8px; background: var(--paper); color: var(--ink-soft);
}
.iconbtn:hover { color: var(--ink); background: var(--surface-2); border-color: var(--ink-faint); text-decoration: none; }
#frame { flex: 1; width: 100%; border: none; background: var(--paper); }

.empty { margin: auto; text-align: center; color: var(--ink-faint); padding: 2rem; }
.empty h2 { font-size: 15px; color: var(--ink-soft); margin: 0 0 .3rem; font-weight: 600; }

#sidebarToggle { display: none; }
@media (max-width: 760px) {
  #sidebar {
    position: fixed; inset: 0 auto 0 0; z-index: 40; width: 86%; max-width: 330px;
    transform: translateX(-101%); transition: transform .22s ease; box-shadow: var(--shadow-lg);
  }
  body.nav-open #sidebar { transform: none; }
  #sidebarToggle { display: grid; }
}
"""

_BROWSER_JS = """
var SESSIONS = __PAYLOAD__;
var list = document.getElementById('list');
var frame = document.getElementById('frame');
var filter = document.getElementById('filter');
var barTitle = document.getElementById('barTitle');
var barMeta = document.getElementById('barMeta');
var barOpen = document.getElementById('barOpen');
var visible = [];
var cursor = -1;

function esc(s) {
  return (s == null ? '' : String(s)).replace(/[&<>"]/g, function (c) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];
  });
}

// Relative day buckets, so the newest work is labelled the way you think of it.
function dayLabel(iso) {
  if (!iso) return 'Undated';
  var d = new Date(iso);
  if (isNaN(d)) return 'Undated';
  var today = new Date(); today.setHours(0,0,0,0);
  var that = new Date(d); that.setHours(0,0,0,0);
  var days = Math.round((today - that) / 86400000);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return 'Earlier this week';
  if (days < 30) return 'Earlier this month';
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

function shortDate(iso) {
  var d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
         d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function basename(p) {
  var parts = String(p || '').split('/').filter(Boolean);
  return parts.length ? parts[parts.length - 1] : p;
}

function select(i) {
  var s = visible[i];
  if (!s) return;
  cursor = i;
  Array.prototype.forEach.call(list.querySelectorAll('li'), function (n) {
    n.classList.toggle('active', n.dataset.idx === String(i));
  });
  var el = list.querySelector('li[data-idx="' + i + '"]');
  if (el) el.scrollIntoView({ block: 'nearest' });
  frame.src = s.html_path;
  barTitle.textContent = s.title;
  barMeta.textContent = basename(s.project) + ' · ' + shortDate(s.started) + ' · ' +
                        s.duration + ' · ' + s.turns + ' turns · ' + s.tool_calls + ' tools';
  barOpen.href = s.html_path;
  document.body.classList.remove('nav-open');
  // Match the frame to the shell's theme once it loads.
  frame.onload = function () {
    try {
      var t = document.documentElement.dataset.theme;
      if (t) frame.contentDocument.documentElement.dataset.theme = t;
    } catch (e) {}
  };
}

function render(term) {
  var t = (term || '').trim().toLowerCase();
  visible = SESSIONS.filter(function (s) {
    return !t || (s.title || '').toLowerCase().indexOf(t) >= 0 ||
                 (s.project || '').toLowerCase().indexOf(t) >= 0;
  });

  if (!visible.length) {
    list.innerHTML = '<div class="noresults">No sessions match<br><strong>' + esc(term) + '</strong></div>';
    frame.removeAttribute('src');
    barTitle.textContent = 'No matches';
    barMeta.textContent = '';
    return;
  }

  var html = '';
  var lastDay = null;
  visible.forEach(function (s, i) {
    var day = dayLabel(s.started);
    if (day !== lastDay) { html += '<div class="daygroup">' + esc(day) + '</div>'; lastDay = day; }
    html += '<li data-idx="' + i + '">' +
      '<div class="title">' + esc(s.title) + '</div>' +
      '<div class="meta"><span>' + esc(shortDate(s.started)) + '</span>' +
      '<span>' + esc(s.duration) + '</span>' +
      '<span>' + s.turns + ' turns</span></div>' +
      '<div class="meta"><span class="proj">' + esc(s.project) + '</span></div></li>';
  });
  list.innerHTML = html;

  Array.prototype.forEach.call(list.querySelectorAll('li'), function (li) {
    li.addEventListener('click', function () { select(Number(li.dataset.idx)); });
  });
  select(0);
}

filter.addEventListener('input', function () { render(filter.value); });

document.addEventListener('keydown', function (e) {
  var typing = document.activeElement === filter;
  if (e.key === '/' && !typing) { e.preventDefault(); filter.focus(); filter.select(); return; }
  if (e.key === 'Escape' && typing) { filter.value = ''; render(''); filter.blur(); return; }
  if (e.key === 'ArrowDown' || (e.key === 'j' && !typing)) { e.preventDefault(); select(Math.min(cursor + 1, visible.length - 1)); }
  if (e.key === 'ArrowUp'   || (e.key === 'k' && !typing)) { e.preventDefault(); select(Math.max(cursor - 1, 0)); }
});

var toggle = document.getElementById('sidebarToggle');
if (toggle) toggle.addEventListener('click', function () { document.body.classList.toggle('nav-open'); });

render('');
"""


def build_browser_html(entries: list[dict]) -> str:
    """Two-pane browser: a date-grouped sidebar of sessions (newest first),
    with the selected session's conversation.html in an <iframe>.

    `entries` items need: session_id, title, project, started, duration,
    tool_calls, turns, html_path (root-relative, e.g. "sessions/.../conversation.html").
    """
    ordered = sorted(entries, key=lambda e: e["started"] or "", reverse=True)
    payload = json.dumps(ordered, ensure_ascii=False).replace("</", "<\\/")
    total_turns = sum(e.get("turns") or 0 for e in ordered)

    script = _BROWSER_JS.replace("__PAYLOAD__", payload)
    sub = f"{len(ordered)} sessions · {total_turns:,} turns"

    return f"""<!doctype html><html><head>{head("Claude Code Chat Archive", _BROWSER_CSS)}</head><body>
<aside id="sidebar">
  <div class="brand">
    <div class="brand-mark">◆</div>
    <div class="brand-text">
      <h1>Chat Archive</h1>
      <div class="sub">{sub}</div>
    </div>
    {THEME_TOGGLE_BUTTON}
  </div>
  <div class="searchbox">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="filter" type="search" placeholder="Filter sessions..." autocomplete="off">
    <kbd>/</kbd>
  </div>
  <div class="quicklinks">
    <a href="index/search.html">Full-text search</a>
    <a href="timeline/timeline.md">Timeline</a>
  </div>
  <ul id="list"></ul>
</aside>
<main id="main">
  <div id="mainbar">
    <button class="iconbtn" id="sidebarToggle" title="Toggle sessions" aria-label="Toggle session list">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
    </button>
    <div class="info"><div class="t" id="barTitle"></div><div class="m" id="barMeta"></div></div>
    <a class="iconbtn" id="barOpen" href="#" target="_blank" title="Open in new tab" aria-label="Open in new tab">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/></svg>
    </a>
  </div>
  <iframe id="frame" title="Conversation"></iframe>
</main>
<script>{THEME_TOGGLE_JS}{script}</script>
</body></html>"""


_SEARCH_CSS = """
body { padding: 0 0 5rem; }
.wrap { max-width: 880px; margin: 0 auto; padding: 0 1.25rem; }

.topbar { border-bottom: 1px solid var(--line); background: var(--surface); margin-bottom: 1.6rem; }
.topbar .wrap { display: flex; align-items: center; gap: .7rem; padding-top: .6rem; padding-bottom: .6rem; }
.topbar h1 { font-size: 13.5px; font-weight: 650; margin: 0; flex: 1; letter-spacing: -.01em; }
.topbar a.back { font-size: 12px; color: var(--ink-soft); }
.topbar a.back:hover { color: var(--accent); }

.searchrow { position: relative; margin-bottom: .8rem; }
.searchrow > svg {
  position: absolute; left: .85rem; top: 50%; transform: translateY(-50%);
  width: 17px; height: 17px; color: var(--ink-faint); pointer-events: none;
}
#q {
  width: 100%; padding: .78rem 1rem .78rem 2.5rem;
  font: inherit; font-size: 15px; color: var(--ink);
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
}
#q::placeholder { color: var(--ink-faint); }
#q:focus { outline: none; border-color: var(--accent); background: var(--paper); box-shadow: 0 0 0 4px var(--accent-soft); }

.filters { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; margin-bottom: 1rem; }
.chip {
  appearance: none; cursor: pointer; font: inherit;
  font-size: 11.5px; font-weight: 500; padding: .25rem .65rem; border-radius: 99px;
  border: 1px solid var(--line); background: var(--surface); color: var(--ink-soft);
  transition: all .12s;
}
.chip:hover { border-color: var(--ink-faint); color: var(--ink); }
.chip[aria-pressed="true"] {
  background: var(--accent); border-color: var(--accent); color: #fff;
}
.count { font-size: 12.5px; color: var(--ink-faint); margin-left: auto; }

.result {
  border: 1px solid var(--line); border-radius: var(--radius);
  padding: .7rem .9rem; margin-bottom: .6rem; background: var(--surface);
  transition: border-color .12s, transform .12s;
}
.result:hover { border-color: var(--ink-faint); }
.result .head { display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; margin-bottom: .4rem; }
.result .head .t { font-size: 12.8px; font-weight: 600; color: var(--ink); }
.result .head .t:hover { color: var(--accent); }
.result .head .meta { font-size: 11px; color: var(--ink-faint); }
.result pre {
  white-space: pre-wrap; word-break: break-word; margin: 0;
  max-height: 16rem; overflow: auto; font-size: 12px;
}
.kind {
  font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  padding: .1em .45em; border-radius: 4px; border: 1px solid var(--line-soft);
}
.kind-text { background: var(--accent-soft); color: var(--accent-ink); }
.kind-bash { background: var(--surface-2); color: var(--ink-soft); }
.kind-file_mod { background: var(--assistant-bg); color: var(--assistant); }

.state { text-align: center; color: var(--ink-faint); padding: 3rem 1rem; }
.state h2 { font-size: 15px; color: var(--ink-soft); margin: 0 0 .3rem; font-weight: 600; }
.state kbd { margin: 0 .1em; }
.more { text-align: center; font-size: 12px; color: var(--ink-faint); padding: .8rem; }
"""

_SEARCH_JS = """
var DATA = __PAYLOAD__;
var LIMIT = 120;
var q = document.getElementById('q');
var results = document.getElementById('results');
var count = document.getElementById('count');
var kinds = { text: true, bash: true, file_mod: true };
var timer = null;

function esc(s) {
  return (s == null ? '' : String(s)).replace(/[&<>"]/g, function (c) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];
  });
}

// Window the snippet around the first hit, then highlight every occurrence
// inside that window (escaping before any markup is inserted).
function snippet(text, term) {
  var low = text.toLowerCase();
  var idx = low.indexOf(term);
  if (idx === -1) return esc(text.slice(0, 260));
  var start = Math.max(0, idx - 170), end = Math.min(text.length, idx + term.length + 260);
  var slice = text.slice(start, end);
  var out = '', pos = 0, sl = slice.toLowerCase(), hit;
  while ((hit = sl.indexOf(term, pos)) !== -1) {
    out += esc(slice.slice(pos, hit)) + '<mark>' + esc(slice.slice(hit, hit + term.length)) + '</mark>';
    pos = hit + term.length;
  }
  out += esc(slice.slice(pos));
  // Messages are Markdown; showing raw ** and ` markers in a preview is just
  // noise. Stripped after highlighting so it can't disturb the <mark> tags.
  out = out.replace(/\\*\\*/g, '').replace(/(^|[\\s(])`([^`\\n]+)`/g, '$1$2');
  return (start > 0 ? '…' : '') + out + (end < text.length ? '…' : '');
}

function shortDate(iso) {
  var d = new Date(iso);
  return isNaN(d) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function render() {
  var term = q.value.trim().toLowerCase();
  if (!term) {
    results.innerHTML = '<div class="state"><h2>Search your whole archive</h2>' +
      'Every turn, bash command and file edit — ' + DATA.length.toLocaleString() + ' entries indexed.<br><br>' +
      'Press <kbd>/</kbd> to focus, <kbd>Esc</kbd> to clear.</div>';
    count.textContent = '';
    return;
  }

  var matches = DATA.filter(function (r) {
    return kinds[r.kind] !== false &&
      ((r.text || '').toLowerCase().indexOf(term) >= 0 || (r.title || '').toLowerCase().indexOf(term) >= 0);
  });

  count.textContent = matches.length.toLocaleString() + (matches.length === 1 ? ' result' : ' results');

  if (!matches.length) {
    results.innerHTML = '<div class="state"><h2>No matches</h2>Nothing in the archive contains “' + esc(q.value) + '”.</div>';
    return;
  }

  var html = matches.slice(0, LIMIT).map(function (r) {
    return '<div class="result">' +
      '<div class="head">' +
        '<a class="t" href="' + esc(r.url) + '" target="_blank">' + esc(r.title) + '</a>' +
        '<span class="kind kind-' + esc(r.kind) + '">' + esc(r.kind === 'file_mod' ? 'file' : r.kind) + '</span>' +
        '<span class="meta">' + esc(r.role) + ' · ' + esc(shortDate(r.timestamp)) + ' · ' + esc(r.project) + '</span>' +
      '</div><pre>' + snippet(r.text || '', term) + '</pre></div>';
  }).join('');

  if (matches.length > LIMIT) {
    html += '<div class="more">Showing first ' + LIMIT + ' of ' + matches.length.toLocaleString() +
            ' — refine your search to narrow it down.</div>';
  }
  results.innerHTML = html;
}

q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(render, 110); });

Array.prototype.forEach.call(document.querySelectorAll('.chip[data-kind]'), function (chip) {
  chip.addEventListener('click', function () {
    var k = chip.dataset.kind;
    kinds[k] = !kinds[k];
    chip.setAttribute('aria-pressed', kinds[k] ? 'true' : 'false');
    render();
  });
});

document.addEventListener('keydown', function (e) {
  if (e.key === '/' && document.activeElement !== q) { e.preventDefault(); q.focus(); q.select(); }
  if (e.key === 'Escape') { q.value = ''; render(); q.blur(); }
});

render();
"""


def build_search_html(search_index: list[dict]) -> str:
    # Escape "</" so a transcript containing a literal "</script>" (e.g. one
    # discussing HTML) can't prematurely close the embedding <script> tag.
    payload = json.dumps(search_index, ensure_ascii=False).replace("</", "<\\/")
    script = _SEARCH_JS.replace("__PAYLOAD__", payload)

    return f"""<!doctype html><html><head>{head("Search · Claude Code Chat Archive", _SEARCH_CSS)}</head><body>
<div class="topbar"><div class="wrap">
  <h1>Search the archive</h1>
  <a class="back" href="../index.html">&larr; All sessions</a>
  {THEME_TOGGLE_BUTTON}
</div></div>
<div class="wrap">
  <div class="searchrow">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="q" type="search" placeholder="Search every turn, command and file edit..." autofocus autocomplete="off">
  </div>
  <div class="filters">
    <button class="chip" data-kind="text" aria-pressed="true">Messages</button>
    <button class="chip" data-kind="bash" aria-pressed="true">Commands</button>
    <button class="chip" data-kind="file_mod" aria-pressed="true">File edits</button>
    <span class="count" id="count"></span>
  </div>
  <div id="results"></div>
</div>
<script>{THEME_TOGGLE_JS}{script}</script>
</body></html>"""
