from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional


def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_duration(start: Optional[str], end: Optional[str]) -> str:
    a, b = parse_ts(start), parse_ts(end)
    if not a or not b:
        return "unknown"
    seconds = max(0, int((b - a).total_seconds()))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def slugify(text: str, max_len: int = 60) -> str:
    text = text.strip().replace(" ", "-")
    text = _SLUG_RE.sub("-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text or "untitled")[:max_len]


def truncate(text: str, limit: int) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more characters]"


def as_text(value) -> str:
    """Best-effort flatten of a tool_result `content` field to plain text."""
    import json

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def decode_project_dir(dirname: str) -> str:
    """Best-effort recovery of a real path from a `-`-encoded project dir name.

    Lossy (hyphens in real path components can't be distinguished from the
    path-separator encoding), used only as a display fallback when no `cwd`
    was recorded in the session itself.
    """
    if dirname.startswith("-"):
        return "/" + dirname[1:].replace("-", "/")
    return dirname
