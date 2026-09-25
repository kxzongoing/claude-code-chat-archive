"""Claude Code session archiver.

Recursively scans a Claude Code `projects` directory (JSONL session
transcripts), reconstructs each conversation in chronological order, and
exports raw JSON, Markdown, HTML, session/search indexes, tool/file/bash
extracts, an architectural-decisions digest, and a project timeline.
"""
