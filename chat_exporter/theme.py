"""Shared design system for every generated page.

One source of truth for colour, type, spacing and the light/dark toggle, so
the browser shell, the search page and each conversation read as one product
rather than three scripts that happen to emit HTML.

Theme resolution has three states: an explicit choice stamps
`data-theme="dark"|"light"` on <html>, and the default "system" setting
stamps nothing, leaving `prefers-color-scheme` to decide. Every colour is
therefore defined on bare `:root` first, then overridden in both the media
query and the `[data-theme]` selector so the toggle wins in either direction.
"""

from __future__ import annotations

# --- design tokens ---------------------------------------------------------

TOKENS = """
:root {
  color-scheme: light dark;

  --ink:        #17191c;
  --ink-soft:   #565c66;
  --ink-faint:  #878d99;
  --paper:      #ffffff;
  --surface:    #f7f8fa;
  --surface-2:  #eef0f4;
  --line:       #e3e6ec;
  --line-soft:  #edeff3;

  --accent:      #4f46e5;
  --accent-soft: #eef2ff;
  --accent-ink:  #4338ca;

  --user:        #4f46e5;
  --user-bg:     #f5f5ff;
  --user-line:   #e0e0fb;
  --assistant:   #0f766e;
  --assistant-bg:#f2fbf9;
  --assistant-line:#d3efea;
  --system:      #92700e;
  --system-bg:   #fdfaf1;
  --system-line: #f0e6c8;

  --ok:     #0f766e;
  --err:    #c2313c;
  --err-bg: #fdf3f4;
  --mark:   #fde68a;
  --mark-ink:#422006;

  --code-bg:  #f5f6f8;
  --code-ink: #1f2430;

  --radius:    12px;
  --radius-sm: 8px;
  --shadow:    0 1px 2px rgba(16,19,26,.05), 0 8px 24px -12px rgba(16,19,26,.15);
  --shadow-lg: 0 24px 60px -24px rgba(16,19,26,.32);

  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ink:        #e7e9ee;
    --ink-soft:   #a2a9b8;
    --ink-faint:  #6f7686;
    --paper:      #0d0f13;
    --surface:    #14171d;
    --surface-2:  #1b1f27;
    --line:       #272c36;
    --line-soft:  #1e222a;

    --accent:      #8b87ff;
    --accent-soft: #1d1b3a;
    --accent-ink:  #a5a1ff;

    --user:        #8b87ff;
    --user-bg:     #15162a;
    --user-line:   #2a2a52;
    --assistant:   #4fd1c5;
    --assistant-bg:#0e1d1c;
    --assistant-line:#1d3b38;
    --system:      #d9b45a;
    --system-bg:   #1e1a10;
    --system-line: #3a3116;

    --ok:     #4fd1c5;
    --err:    #ff8087;
    --err-bg: #241416;
    --mark:   #7c5e10;
    --mark-ink:#fff3cd;

    --code-bg:  #171b22;
    --code-ink: #d7dce6;

    --shadow:    0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
    --shadow-lg: 0 24px 60px -24px rgba(0,0,0,.75);
  }
}

:root[data-theme="dark"] {
  --ink:        #e7e9ee;
  --ink-soft:   #a2a9b8;
  --ink-faint:  #6f7686;
  --paper:      #0d0f13;
  --surface:    #14171d;
  --surface-2:  #1b1f27;
  --line:       #272c36;
  --line-soft:  #1e222a;

  --accent:      #8b87ff;
  --accent-soft: #1d1b3a;
  --accent-ink:  #a5a1ff;

  --user:        #8b87ff;
  --user-bg:     #15162a;
  --user-line:   #2a2a52;
  --assistant:   #4fd1c5;
  --assistant-bg:#0e1d1c;
  --assistant-line:#1d3b38;
  --system:      #d9b45a;
  --system-bg:   #1e1a10;
  --system-line: #3a3116;

  --ok:     #4fd1c5;
  --err:    #ff8087;
  --err-bg: #241416;
  --mark:   #7c5e10;
  --mark-ink:#fff3cd;

  --code-bg:  #171b22;
  --code-ink: #d7dce6;

  --shadow:    0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  --shadow-lg: 0 24px 60px -24px rgba(0,0,0,.75);
}
"""

# --- base element styles ---------------------------------------------------

BASE = """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

code, pre, kbd { font-family: var(--mono); }
pre {
  background: var(--code-bg);
  color: var(--code-ink);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  padding: .8rem .95rem;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.55;
  margin: .7rem 0;
  tab-size: 2;
}
pre code { background: none; padding: 0; font-size: inherit; border: none; }
:not(pre) > code {
  background: var(--surface-2);
  border: 1px solid var(--line-soft);
  border-radius: 5px;
  padding: .1em .38em;
  font-size: .875em;
  word-break: break-word;
}
kbd {
  background: var(--surface-2); border: 1px solid var(--line);
  border-bottom-width: 2px; border-radius: 5px;
  padding: .08em .4em; font-size: .78em; color: var(--ink-soft);
}
mark { background: var(--mark); color: var(--mark-ink); border-radius: 3px; padding: .05em .15em; }
hr { border: none; border-top: 1px solid var(--line); margin: 2rem 0; }

::-webkit-scrollbar { width: 11px; height: 11px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--line); border-radius: 99px;
  border: 3px solid var(--paper); background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: var(--ink-faint); background-clip: padding-box; }

:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

.pill {
  display: inline-flex; align-items: center; gap: .3em;
  font-size: 11px; font-weight: 500; letter-spacing: .01em;
  padding: .18em .55em; border-radius: 99px;
  background: var(--surface-2); color: var(--ink-soft);
  border: 1px solid var(--line-soft); white-space: nowrap;
}
.mono-sm { font-family: var(--mono); font-size: 11.5px; color: var(--ink-faint); }

.theme-toggle {
  appearance: none; cursor: pointer;
  width: 30px; height: 30px; flex: none;
  display: grid; place-items: center;
  border: 1px solid var(--line); border-radius: 8px;
  background: var(--surface); color: var(--ink-soft);
  transition: background .15s, color .15s, border-color .15s;
}
.theme-toggle:hover { background: var(--surface-2); color: var(--ink); border-color: var(--ink-faint); }
.theme-toggle svg { width: 15px; height: 15px; }
.theme-toggle .sun { display: none; }
:root[data-theme="dark"] .theme-toggle .sun { display: block; }
:root[data-theme="dark"] .theme-toggle .moon { display: none; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .theme-toggle .sun { display: block; }
  :root:not([data-theme="light"]) .theme-toggle .moon { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
"""

# Inlined in <head> so the stored theme applies before first paint (no flash).
THEME_BOOT = (
    "<script>try{var t=localStorage.getItem('cca-theme');"
    "if(t==='dark'||t==='light')document.documentElement.dataset.theme=t;}catch(e){}</script>"
)

THEME_TOGGLE_BUTTON = """<button class="theme-toggle" id="themeToggle" title="Toggle theme" aria-label="Toggle colour theme">
<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
</button>"""

THEME_TOGGLE_JS = """
(function () {
  var btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var root = document.documentElement;
    var cur = root.dataset.theme;
    if (!cur) {
      cur = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    var next = cur === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('cca-theme', next); } catch (e) {}
    // Keep embedded conversation frames in step with the shell.
    document.querySelectorAll('iframe').forEach(function (f) {
      try { f.contentDocument.documentElement.dataset.theme = next; } catch (e) {}
    });
  });
})();
"""


def head(title: str, extra_css: str = "") -> str:
    """Standard <head> for a generated page."""
    return (
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        f"{THEME_BOOT}"
        f"<style>{TOKENS}{BASE}{extra_css}</style>"
    )
