#!/usr/bin/env python3
"""Archive Claude Code session transcripts into a browsable, searchable export.

Scans a `~/.claude/projects` tree, reconstructs each session's conversation
in chronological order, and writes:

  sessions/<project>/<session_id>/raw.json          raw JSON archive
  sessions/<project>/<session_id>/conversation.md    beautiful markdown
  sessions/<project>/<session_id>/conversation.html  beautiful html
  index/session_index.{json,md}                      session index
  index/search_index.json + index/search.html         search index (browsable)
  extracts/tool_invocations.{json,md}
  extracts/file_modifications.{json,md}
  extracts/bash_commands.{json,md}
  extracts/architectural_decisions.{json,md}
  timeline/timeline.{json,md}

Incremental by default: a session whose source `.jsonl` is unchanged since
the last run (tracked via sha256 in manifest.json) is left alone. A
session that is new or has changed content has its per-session files
replaced. Pass --force to replace every session's files regardless of
manifest state.

The archive is append-only. Claude Code prunes `~/.claude/projects` after
`cleanupPeriodDays`, so a session exported months ago may have no live
source. The aggregate documents (index/extracts/timeline) are rebuilt in
full on every run from the union of live sources *and* every session still
recorded in manifest.json, replayed from its archived `raw.json`. A session
that has been exported once therefore stays in the index forever.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chat_exporter.extract import (
    extract_architectural_decisions,
    extract_bash_commands,
    extract_file_modifications,
    extract_tool_invocations,
)
from chat_exporter.indexer import (
    build_browser_html,
    build_search_html,
    render_session_index_markdown,
    search_records,
    session_index_entry,
)
from chat_exporter.manifest import load_manifest, manifest_key, save_manifest
from chat_exporter.parser import parse_archived_session, parse_session_file
from chat_exporter.render_html import render_session_html
from chat_exporter.render_markdown import render_session_markdown
from chat_exporter.reports import (
    render_architectural_decisions_markdown,
    render_bash_commands_markdown,
    render_file_modifications_markdown,
    render_tool_invocations_markdown,
)
from chat_exporter.scanner import scan_session_files
from chat_exporter.timeline import render_timeline_markdown, session_timeline_events
from chat_exporter.util import fmt_duration, now_iso

DEFAULT_ROOT = "~/.claude/projects"
# Export into the checkout itself by default; .gitignore keeps the generated
# archive (which contains your actual conversations) out of version control.
DEFAULT_OUTPUT = os.path.dirname(os.path.abspath(__file__))


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT, help=f"Claude projects dir (default: {DEFAULT_ROOT})")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="Export output dir (default: this checkout)")
    ap.add_argument("--project", default=None, help="Only process project dirs containing this substring")
    ap.add_argument("--force", action="store_true", help="Re-render every session's files, ignoring the manifest")
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    output = os.path.abspath(os.path.expanduser(args.output))
    os.makedirs(output, exist_ok=True)

    session_files = scan_session_files(root)
    if args.project:
        session_files = [sf for sf in session_files if args.project in sf.project_dir]

    if not session_files:
        print(f"No session .jsonl files found under {root}")
        return 0

    manifest = load_manifest(output)
    sessions_dir = os.path.join(output, "sessions")
    index_dir = os.path.join(output, "index")
    extracts_dir = os.path.join(output, "extracts")
    timeline_dir = os.path.join(output, "timeline")

    all_index_entries = []
    all_browser_entries = []
    all_search_records = []
    all_tool_calls = []
    all_file_mods = []
    all_bash_cmds = []
    all_decisions = []
    all_timeline_events = []

    written, skipped, failed, restored = 0, 0, 0, 0
    live_keys: set[str] = set()

    def accumulate(session, raw_path: str, md_path: str, html_path: str) -> None:
        """Feed one session into every aggregate document."""
        rel_md = os.path.relpath(md_path, index_dir)
        rel_html = os.path.relpath(html_path, index_dir)
        rel_raw = os.path.relpath(raw_path, index_dir)
        all_index_entries.append(session_index_entry(session, rel_md, rel_html, rel_raw))

        n_user, n_assistant = session.counts
        all_browser_entries.append(
            {
                "session_id": session.session_id,
                "title": session.title,
                "project": session.project_cwd or session.project_dir,
                "started": session.start_ts,
                "duration": fmt_duration(session.start_ts, session.end_ts),
                "turns": n_user + n_assistant,
                "tool_calls": len(session.tool_calls),
                "html_path": os.path.relpath(html_path, output),
            }
        )

        all_search_records.extend(search_records(session, rel_html))

        all_tool_calls.extend(extract_tool_invocations(session))
        file_mods = extract_file_modifications(session)
        bash_cmds = extract_bash_commands(session)
        decisions = extract_architectural_decisions(session)
        all_file_mods.extend(file_mods)
        all_bash_cmds.extend(bash_cmds)
        all_decisions.extend(decisions)
        all_timeline_events.extend(session_timeline_events(session, file_mods, bash_cmds, decisions))

    for sf in session_files:
        try:
            session = parse_session_file(sf)
        except Exception as exc:  # noqa: BLE001 - keep scanning other sessions
            print(f"[error] failed to parse {sf.path}: {exc}", file=sys.stderr)
            failed += 1
            continue

        key = manifest_key(sf.project_dir, sf.session_id)
        prior = manifest.get(key)
        session_out_dir = os.path.join(sessions_dir, sf.project_dir, sf.session_id)
        raw_path = os.path.join(session_out_dir, "raw.json")
        md_path = os.path.join(session_out_dir, "conversation.md")
        html_path = os.path.join(session_out_dir, "conversation.html")

        needs_write = (
            args.force
            or prior is None
            or prior.get("sha256") != session.source_sha256
            or not (os.path.isfile(raw_path) and os.path.isfile(md_path) and os.path.isfile(html_path))
        )

        if needs_write:
            write_json(raw_path, session.raw_records)
            write_text(md_path, render_session_markdown(session))
            write_text(html_path, render_session_html(session))
            manifest[key] = {
                "sha256": session.source_sha256,
                "size": session.source_size,
                "mtime": session.source_mtime,
                "source_path": session.file_path,
                "exported_at": now_iso(),
            }
            written += 1
        else:
            skipped += 1

        accumulate(session, raw_path, md_path, html_path)
        live_keys.add(key)

    # --- backfill: sessions we archived whose source .jsonl is now gone ---
    # Claude Code prunes ~/.claude/projects after `cleanupPeriodDays`. Without
    # this pass, the aggregates below would silently forget every session that
    # aged out, even though its export is still sitting in sessions/.
    for key in sorted(manifest):
        if key in live_keys:
            continue
        project_dir, _, session_id = key.rpartition("/")
        session_out_dir = os.path.join(sessions_dir, project_dir, session_id)
        raw_path = os.path.join(session_out_dir, "raw.json")
        md_path = os.path.join(session_out_dir, "conversation.md")
        html_path = os.path.join(session_out_dir, "conversation.html")

        if not os.path.isfile(raw_path):
            print(f"[warn] {key}: source pruned and no archived raw.json; cannot restore", file=sys.stderr)
            failed += 1
            continue

        try:
            session = parse_archived_session(project_dir, session_id, raw_path, manifest.get(key))
        except Exception as exc:  # noqa: BLE001 - keep restoring other sessions
            print(f"[error] failed to restore {raw_path}: {exc}", file=sys.stderr)
            failed += 1
            continue

        # Regenerate any per-session rendering that went missing; raw.json is
        # the archive of record, the md/html are derived from it.
        if args.force or not os.path.isfile(md_path):
            write_text(md_path, render_session_markdown(session))
        if args.force or not os.path.isfile(html_path):
            write_text(html_path, render_session_html(session))

        accumulate(session, raw_path, md_path, html_path)
        restored += 1

    # --- aggregates: always rebuilt in full from current data ---
    write_text(os.path.join(output, "index.html"), build_browser_html(all_browser_entries))
    write_json(os.path.join(index_dir, "session_index.json"), all_index_entries)
    write_text(os.path.join(index_dir, "session_index.md"), render_session_index_markdown(all_index_entries))
    write_json(os.path.join(index_dir, "search_index.json"), all_search_records)
    write_text(os.path.join(index_dir, "search.html"), build_search_html(all_search_records))

    write_json(os.path.join(extracts_dir, "tool_invocations.json"), all_tool_calls)
    write_text(os.path.join(extracts_dir, "tool_invocations.md"), render_tool_invocations_markdown(all_tool_calls))
    write_json(os.path.join(extracts_dir, "file_modifications.json"), all_file_mods)
    write_text(
        os.path.join(extracts_dir, "file_modifications.md"), render_file_modifications_markdown(all_file_mods)
    )
    write_json(os.path.join(extracts_dir, "bash_commands.json"), all_bash_cmds)
    write_text(os.path.join(extracts_dir, "bash_commands.md"), render_bash_commands_markdown(all_bash_cmds))
    write_json(os.path.join(extracts_dir, "architectural_decisions.json"), all_decisions)
    write_text(
        os.path.join(extracts_dir, "architectural_decisions.md"),
        render_architectural_decisions_markdown(all_decisions),
    )

    write_json(os.path.join(timeline_dir, "timeline.json"), sorted(all_timeline_events, key=lambda e: e["timestamp"] or ""))
    write_text(os.path.join(timeline_dir, "timeline.md"), render_timeline_markdown(all_timeline_events))

    save_manifest(output, manifest)

    print(
        f"Sessions found: {len(session_files)} | rendered: {written} | unchanged (skipped): {skipped} | "
        f"restored from archive: {restored} | failed: {failed}"
    )
    print(f"Total sessions in index: {len(all_index_entries)}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
