# Claude Code Chat Archive

**Claude Code deletes your session transcripts after 30 days. This archives them permanently, and makes them browsable and searchable.**

Claude Code stores every conversation as a `.jsonl` file under `~/.claude/projects`, then prunes anything older than `cleanupPeriodDays` (default: **30**). Once pruned, those conversations are gone. This tool exports them first — as readable Markdown and HTML — and keeps them in an append-only archive that survives the prune.

Python 3.9+, standard library only. Nothing to install, nothing sent anywhere.

## Quick start

```bash
git clone https://github.com/kxzongoing/claude-code-chat-archive.git
cd claude-code-chat-archive
python3 export_claude_chats.py
```

Then open `index.html` in a browser. That's it.

The first run exports everything currently in `~/.claude/projects`. Every later run picks up what's new and leaves the rest alone.

## Stop losing chats first

Before anything else, widen Claude Code's retention window. Add this to `~/.claude/settings.json`:

```json
{
  "cleanupPeriodDays": 365
}
```

This tool can only archive what still exists when it runs. Raising the retention window buys you a year of margin; running the exporter regularly (see below) closes the gap entirely.

> **Already lost chats?** If you had exported them before, they aren't gone — see [Recovering pruned sessions](#recovering-pruned-sessions).

## Keep it running

The exporter only captures what's live at the moment it runs. To never miss a session, run it on a schedule.

**macOS / Linux (cron)** — `crontab -e`, then:

```
0 20 * * * cd /path/to/claude-code-chat-archive && /usr/bin/python3 export_claude_chats.py >/dev/null 2>&1
```

**Windows** — Task Scheduler, daily, action `python3 export_claude_chats.py`, "Start in" set to the checkout.

## What you get

Open **`index.html`** — a sidebar lists every chat newest-first; click to read it, filter by title or project once the list grows.

Open **`index/search.html`** — client-side substring search across every turn, bash command, and file edit, linking back to the source conversation. No server needed.

Everything else is plain JSON and Markdown, easy to grep or feed to other tools:

| Path | Contents |
|---|---|
| `sessions/<project>/<id>/` | `raw.json` (original records), `conversation.md`, `conversation.html` |
| `index/session_index.{json,md}` | One row per session: title, project, duration, links |
| `extracts/tool_invocations.{json,md}` | Every tool call, matched with its result |
| `extracts/file_modifications.{json,md}` | Every Edit/Write/MultiEdit/NotebookEdit |
| `extracts/bash_commands.{json,md}` | Every Bash call with stdout/stderr |
| `extracts/architectural_decisions.{json,md}` | Heuristically pulled decision points |
| `timeline/timeline.{json,md}` | All of the above merged, sorted, grouped by date |

Session UUIDs and original timestamps are preserved everywhere — filenames, table rows, HTML anchors.

`architectural_decisions` is a heuristic (plan proposals, `AskUserQuestion` points, decision-language in assistant text). Read it for signal, not as a curated list.

## Options

```
--root <dir>         Source projects dir (default: ~/.claude/projects)
--output <dir>       Export dir (default: this checkout)
--project <substr>   Only process project dirs matching a substring
--force              Re-render every session, ignoring the manifest
```

## How it stays safe

**Incremental.** `manifest.json` records a sha256 of each session's source `.jsonl`. Unchanged sessions are skipped; new or edited ones are re-rendered.

**Append-only.** This is the important part. Aggregate documents are rebuilt on every run from the union of *live sources* **and** *every session still listed in `manifest.json`*, replayed from its archived `raw.json`. So when Claude Code prunes a source file, the session stays in your index anyway. **Once exported, a conversation is in the archive permanently.**

**Local.** Reads `~/.claude/projects`, writes to disk. No network calls, no telemetry, no dependencies.

### Recovering pruned sessions

If you exported sessions in the past and they've since disappeared from your index, they are almost certainly still on disk. Earlier versions of this tool rebuilt the index only from live sources, so pruned sessions silently dropped out even though `sessions/` still held them.

Just run the exporter again:

```bash
python3 export_claude_chats.py
```

The backfill pass restores every session listed in `manifest.json` from its archived `raw.json`. The summary line reports how many came back:

```
Sessions found: 23 | rendered: 2 | unchanged (skipped): 21 | restored from archive: 28 | failed: 0
Total sessions in index: 51
```

As long as `manifest.json` and `sessions/` are intact, nothing is lost.

## Privacy

**Your exported conversations are private. Do not commit them.**

The archive contains whatever you discussed with Claude — proprietary source, file paths, customer data, credentials pasted into prompts. The included `.gitignore` excludes every directory the exporter writes (`sessions/`, `index/`, `extracts/`, `timeline/`, `index.html`, `manifest.json`), so a fork of this repo stays code-only.

If you point `--output` somewhere else, add that path to `.gitignore` too. Before your first push, confirm:

```bash
git status --porcelain     # should list source files only
```

To back up the archive itself, use a **private** repo or ordinary file backup — never a public one.

## Contributing

Issues and PRs welcome. Please never include real transcript content in a bug report — a redacted snippet or the session structure is enough.

## License

MIT — see [LICENSE](LICENSE).
