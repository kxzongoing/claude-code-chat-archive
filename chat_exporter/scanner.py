from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SessionFile:
    project_dir: str  # first path component under root, e.g. "-Users-me-repo"
    session_id: str  # filename stem
    path: str


def scan_session_files(root: str) -> list[SessionFile]:
    """Recursively find every *.jsonl session transcript under `root`.

    Each Claude Code project gets one directory directly under `root` (named
    after its cwd with path separators replaced by `-`); session transcripts
    are `<uuid>.jsonl` files inside it. We walk recursively rather than
    assuming that fixed depth, in case of nested project layouts.
    """
    root = os.path.abspath(os.path.expanduser(root))
    results: list[SessionFile] = []
    if not os.path.isdir(root):
        return results

    for dirpath, dirnames, filenames in os.walk(root):
        for fname in filenames:
            if not fname.endswith(".jsonl"):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            parts = rel.split(os.sep)
            project_dir = parts[0]
            session_id = fname[: -len(".jsonl")]
            results.append(SessionFile(project_dir=project_dir, session_id=session_id, path=full))
    results.sort(key=lambda sf: (sf.project_dir, sf.session_id))
    return results
