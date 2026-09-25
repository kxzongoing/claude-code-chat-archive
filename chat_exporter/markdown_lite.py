"""A small, dependency-free Markdown-to-HTML renderer.

Claude's messages are Markdown, so rendering them inside <pre> (as this
exporter originally did) turns ordinary prose into a terminal dump. This
covers the subset that actually shows up in transcripts: fenced code,
headings, lists, tables, blockquotes, rules, and inline emphasis/code/links.

Everything is escaped before any tag is emitted — transcript text is
untrusted input and frequently contains literal HTML.
"""

from __future__ import annotations

import re

from .util import html_escape

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)\s*$")
_ATX_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_RULE_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")

# Inline: code spans first so their contents are never re-parsed as emphasis.
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Emphasis content must end in a character that is neither whitespace nor a
# delimiter, so runs of asterisks used as decoration (`***** heading *****`)
# match nothing instead of interleaving into misnested tags.
_BOLD_RE = re.compile(r"\*\*(?!\s)([^\n]*?[^\s*])\*\*(?!\*)")
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]*?[^\s*])\*(?![\w*])")
_STRIKE_RE = re.compile(r"~~(?!\s)([^\n]*?[^\s~])~~")
_BARE_URL_RE = re.compile(r"(?<![\"'=>\]])\b(https?://[^\s<>\"')]+)")

_SAFE_HREF_RE = re.compile(r"^(https?:|mailto:|#|/|\.{1,2}/|[\w./-]+\.(?:html|md|json)(?:#.*)?$)", re.I)


def _safe_href(url: str) -> str | None:
    """Allow only hrefs that can't execute script (no javascript:/data:)."""
    return url if _SAFE_HREF_RE.match(url.strip()) else None


def render_inline(text: str) -> str:
    """Escape `text`, then apply inline Markdown. Returns HTML."""
    placeholders: list[str] = []

    def stash(html: str) -> str:
        placeholders.append(html)
        return f"\x00{len(placeholders) - 1}\x00"

    # Code spans are extracted pre-escape so emphasis never fires inside them.
    def code_span(m: re.Match) -> str:
        return stash(f"<code>{html_escape(m.group(1))}</code>")

    text = _CODE_SPAN_RE.sub(code_span, text)

    def link(m: re.Match) -> str:
        href = _safe_href(m.group(2))
        label = html_escape(m.group(1))
        if not href:
            return stash(label)
        return stash(f'<a href="{html_escape(href)}" target="_blank" rel="noopener">{label}</a>')

    text = _LINK_RE.sub(link, text)

    text = html_escape(text)

    # Each emphasis pass stashes its output, so a later pattern can never match
    # across markup an earlier one inserted (which produced misnested tags).
    def emphasis(pattern: re.Pattern, tag: str, source: str) -> str:
        return pattern.sub(lambda m: stash(f"<{tag}>{m.group(1)}</{tag}>"), source)

    # Bold first, running the italic pass over its contents so `**bold *and
    # italic***` still nests correctly.
    text = _BOLD_RE.sub(
        lambda m: stash(f"<strong>{emphasis(_ITALIC_RE, 'em', m.group(1))}</strong>"), text
    )
    text = emphasis(_STRIKE_RE, "del", text)
    text = emphasis(_ITALIC_RE, "em", text)
    text = _BARE_URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)

    # Stashed HTML can itself contain earlier placeholders (a code span inside
    # bold), so expand repeatedly until none are left.
    token = re.compile(r"\x00(\d+)\x00")
    for _ in range(len(placeholders) + 1):
        text, count = token.subn(lambda m: placeholders[int(m.group(1))], text)
        if not count:
            break
    return text


def _close_lists(stack: list[str], out: list[str], depth: int = 0) -> None:
    while len(stack) > depth:
        out.append(f"</{stack.pop()}>")


def render_markdown(text: str) -> str:
    """Render a Markdown document to HTML."""
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    list_stack: list[str] = []
    para: list[str] = []
    quote: list[str] = []
    i = 0

    def flush_para() -> None:
        if para:
            out.append(f"<p>{render_inline(' '.join(para).strip())}</p>")
            para.clear()

    def flush_quote() -> None:
        if quote:
            out.append(f"<blockquote>{render_markdown(chr(10).join(quote))}</blockquote>")
            quote.clear()

    def flush_all() -> None:
        flush_para()
        flush_quote()
        _close_lists(list_stack, out)

    while i < len(lines):
        line = lines[i]

        fence = _FENCE_RE.match(line)
        if fence:
            flush_all()
            marker, lang = fence.group(1)[0], fence.group(2)
            body: list[str] = []
            i += 1
            while i < len(lines):
                closing = _FENCE_RE.match(lines[i])
                if closing and closing.group(1)[0] == marker:
                    i += 1
                    break
                body.append(lines[i])
                i += 1
            lang_attr = f' data-lang="{html_escape(lang)}"' if lang else ""
            out.append(f"<pre{lang_attr}><code>{html_escape(chr(10).join(body))}</code></pre>")
            continue

        if not line.strip():
            flush_para()
            flush_quote()
            i += 1
            continue

        if _RULE_RE.match(line):
            flush_all()
            out.append("<hr/>")
            i += 1
            continue

        quoted = _QUOTE_RE.match(line)
        if quoted:
            flush_para()
            _close_lists(list_stack, out)
            quote.append(quoted.group(1))
            i += 1
            continue
        flush_quote()

        heading = _ATX_RE.match(line)
        if heading:
            flush_all()
            level = len(heading.group(1))
            out.append(f"<h{level}>{render_inline(heading.group(2).strip())}</h{level}>")
            i += 1
            continue

        # Table: a header row followed by a |---|---| separator.
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            flush_all()
            i = _emit_table(lines, i, out)
            continue

        ul, ol = _UL_RE.match(line), _OL_RE.match(line)
        if ul or ol:
            flush_para()
            match = ul or ol
            indent = len(match.group(1).expandtabs(4))
            content = (ul.group(2) if ul else ol.group(3))
            tag = "ul" if ul else "ol"
            depth = indent // 2 + 1

            while len(list_stack) > depth:
                out.append(f"</{list_stack.pop()}>")
            if len(list_stack) < depth:
                while len(list_stack) < depth:
                    out.append(f"<{tag}>")
                    list_stack.append(tag)
            elif list_stack and list_stack[-1] != tag:
                out.append(f"</{list_stack.pop()}>")
                out.append(f"<{tag}>")
                list_stack.append(tag)

            out.append(f"<li>{render_inline(content.strip())}</li>")
            i += 1
            continue

        _close_lists(list_stack, out)
        para.append(line.strip())
        i += 1

    flush_all()
    return "".join(out)


def _emit_table(lines: list[str], i: int, out: list[str]) -> int:
    """Emit a pipe table starting at `lines[i]`; returns the next index."""

    def cells(row: str) -> list[str]:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]

    aligns = []
    for spec in cells(lines[i + 1]):
        left, right = spec.startswith(":"), spec.endswith(":")
        aligns.append("center" if left and right else "right" if right else "left")

    def row_html(row: str, tag: str) -> str:
        tds = []
        for n, cell in enumerate(cells(row)):
            align = aligns[n] if n < len(aligns) else "left"
            style = f' style="text-align:{align}"' if align != "left" else ""
            tds.append(f"<{tag}{style}>{render_inline(cell)}</{tag}>")
        return f"<tr>{''.join(tds)}</tr>"

    out.append('<div class="table-wrap"><table>')
    out.append(f"<thead>{row_html(lines[i], 'th')}</thead><tbody>")
    i += 2
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        out.append(row_html(lines[i], "td"))
        i += 1
    out.append("</tbody></table></div>")
    return i
