#!/usr/bin/env python3
"""Build a demo archive from invented transcripts.

Screenshots of a personal archive leak real work, so this synthesises a set
of plausible sessions, writes them as Claude Code `.jsonl` transcripts, and
runs them through the *real* exporter. The resulting pages come out of the
same renderers as a genuine archive — accurate to screenshot, safe to
publish, and useful for eyeballing UI changes without touching your own data.

    python3 tools/make_demo.py            # -> docs/demo/
    python3 tools/make_demo.py --open     # ...and open it

Everything below is fiction: no real project, path, or person.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- invented transcripts --------------------------------------------------
# Each session: (title, project cwd, git branch, hours ago, [turns...]).
# A turn is ("user"|"assistant", text) or ("tool", name, input, output, is_error).

SESSIONS = [
    (
        "Fix flaky checkout integration test",
        "/home/dev/storefront", "fix/flaky-checkout", 3,
        [
            ("user", "The `checkout_completes_order` test fails maybe one run in five on CI but never locally. Can you work out why?"),
            ("assistant", "A failure that only shows up on CI usually means a timing or ordering assumption. Let me look at the test first."),
            ("tool", "Read", {"file_path": "tests/test_checkout.py"},
             "def test_checkout_completes_order(client, cart):\n    cart.add(SKU_WIDGET, qty=2)\n    resp = client.post('/checkout')\n    assert resp.status_code == 200\n    assert Order.objects.count() == 1\n", False),
            ("tool", "Bash", {"command": "pytest tests/test_checkout.py -q --count=20", "description": "Run the test 20 times to reproduce"},
             "....F...............F\n2 failed, 18 passed in 41.02s", False),
            ("assistant", "Reproduced — 2 failures in 20 runs. The assertion is on a **global** `Order` count, so it depends on no other test having left an order behind.\n\nTwo things are going on:\n\n1. `Order.objects.count()` counts rows from the whole database, not this cart.\n2. The checkout task is dispatched asynchronously, so the row may not exist yet when the assertion runs.\n\nThe fix is to scope the assertion to the cart and wait on the task:"),
            ("tool", "Edit", {"file_path": "tests/test_checkout.py",
                               "old_string": "    assert Order.objects.count() == 1",
                               "new_string": "    wait_for_tasks()\n    assert cart.orders.count() == 1"},
             "Edit applied to tests/test_checkout.py", False),
            ("tool", "Bash", {"command": "pytest tests/test_checkout.py -q --count=50", "description": "Re-run 50 times to confirm"},
             "..................................................\n50 passed in 1m 38s", False),
            ("assistant", "50/50 green.\n\n**What was wrong:** the test asserted on a global row count and raced the async task. Scoping to `cart.orders` and waiting on the queue removes both assumptions.\n\nWorth grepping for the same pattern elsewhere — `Order.objects.count()` appears in two other tests."),
            ("user", "Good catch. Fix those two as well and push a branch."),
        ],
    ),
    (
        "Speed up the nightly analytics rollup",
        "/home/dev/analytics-pipeline", "perf/rollup", 9,
        [
            ("user", "Our nightly rollup takes 40 minutes and it's getting worse every week. Where's the time going?"),
            ("assistant", "Let me profile it before changing anything — 40 minutes could be one bad query or a thousand small ones."),
            ("tool", "Bash", {"command": "python -m cProfile -s cumtime jobs/rollup.py --dry-run | head -25", "description": "Profile the rollup job"},
             "         8214551 function calls (8104233 primitive calls) in 2281.4 seconds\n\n   ncalls  tottime  percall  cumtime  percall filename:lineno(function)\n     1     0.004    0.004 2281.401 2281.401 rollup.py:1(<module>)\n 14204     1.882    0.000 2190.773    0.154 rollup.py:88(fetch_account_events)\n 14204  2104.339    0.148 2104.339    0.148 {method 'execute' of 'Cursor'}", False),
            ("assistant", "There it is. `fetch_account_events` is called **14,204 times** — once per account — and each call issues its own query. That's a textbook N+1: 2,104 of the 2,281 seconds are spent inside `Cursor.execute`.\n\nThe rollup doesn't need per-account isolation; it can pull all events in one pass and group in memory."),
            ("tool", "Read", {"file_path": "jobs/rollup.py"},
             "def fetch_account_events(account_id, day):\n    return db.query(\n        'SELECT kind, amount FROM events WHERE account_id = %s AND day = %s',\n        (account_id, day),\n    )\n\ndef run(day):\n    for account in Account.active():\n        rows = fetch_account_events(account.id, day)\n        write_rollup(account, aggregate(rows))", False),
            ("tool", "Edit", {"file_path": "jobs/rollup.py",
                               "old_string": "    for account in Account.active():\n        rows = fetch_account_events(account.id, day)",
                               "new_string": "    events = fetch_all_events(day)  # one query, grouped by account\n    for account in Account.active():\n        rows = events.get(account.id, ())"},
             "Edit applied to jobs/rollup.py", False),
            ("tool", "Bash", {"command": "time python jobs/rollup.py --day 2026-09-24", "description": "Time the rewritten rollup"},
             "rollup complete: 14204 accounts, 3.9M events\n\nreal\t1m52.407s\nuser\t1m31.002s\nsys\t0m9.771s", False),
            ("assistant", "**40 minutes → 1m52s**, about a 21× improvement.\n\nThe memory cost is modest: 3.9M events grouped into a dict is roughly 310 MB at peak, well inside the job's 2 GB limit. If event volume grows past ~10M we'd want to chunk by day-hour, but that's a long way off."),
        ],
    ),
    (
        "Design the notification preferences schema",
        "/home/dev/storefront", "feat/notif-prefs", 27,
        [
            ("user", "I need a schema for per-user notification preferences. Channels are email, SMS and push; categories are orders, shipping, promos and security. Users should be able to mute a whole category or a single channel within it."),
            ("assistant", "The requirement that matters most is *mute a category **or** a channel within it* — that rules out a single flat boolean per pair, because you'd lose the distinction between \"category is off\" and \"this one channel is off\".\n\nI'd model it as two tables:\n\n| Table | Purpose |\n|---|---|\n| `notification_category_prefs` | One row per (user, category) — the category-level switch |\n| `notification_channel_prefs` | One row per (user, category, channel) — the finer override |\n\nResolution is then: a notification sends if the category is enabled **and** no channel override disables it. Absent rows mean \"use the default\", so you don't need to backfill anything for existing users."),
            ("user", "Why not a single table with a nullable channel column?"),
            ("assistant", "That works too and is genuinely simpler — one table, `(user_id, category, channel NULL)` where a NULL channel means the category row.\n\nThe tradeoff is that you lose the ability to put a foreign key or NOT NULL constraint on `channel`, and every query needs `channel IS NULL OR channel = %s`. With only four categories and three channels the table stays tiny either way, so I'd take the single-table version for the simpler migration — the constraint you give up isn't buying much here.\n\nSecurity is worth special-casing regardless: most products don't let users mute security alerts at all."),
            ("user", "Agreed on security being non-mutable. Let's go with the single table."),
        ],
    ),
    (
        "Track down the memory leak in the websocket worker",
        "/home/dev/realtime-gateway", "main", 32,
        [
            ("user", "The websocket worker's RSS climbs from 200 MB to 3 GB over about six hours and then gets OOM-killed. Restarting resets it."),
            ("assistant", "Steady linear growth that survives idle periods usually means we're retaining objects per connection. Let me snapshot the heap at two points and diff them."),
            ("tool", "Bash", {"command": "py-spy dump --pid 4417 && python -c \"import tracemalloc\" ", "description": "Snapshot worker state"},
             "Process 4417: gunicorn realtime.app\nThread 0x7f2 (active): \"MainThread\"\n    _handle_frame (realtime/socket.py:212)\n    dispatch (realtime/socket.py:88)", False),
            ("tool", "Bash", {"command": "python tools/heapdiff.py --pid 4417 --interval 600", "description": "Diff heap over 10 minutes"},
             "top growth over 600s:\n  realtime.socket.Connection        +18442 objects   +214.8 MB\n  realtime.metrics._Sample          +18442 objects    +38.1 MB\n  builtins.dict                     +36901 objects    +61.2 MB", False),
            ("assistant", "`Connection` objects are never being freed — 18,442 accumulated in ten minutes, matching the connection rate exactly. Something holds a strong reference after disconnect."),
            ("tool", "Grep", {"pattern": "_active_connections|CONNECTIONS", "path": "realtime/"},
             "realtime/metrics.py:31:CONNECTIONS = []\nrealtime/metrics.py:44:    CONNECTIONS.append(_Sample(conn, time.time()))\nrealtime/socket.py:96:    metrics.record_open(self)", False),
            ("tool", "Read", {"file_path": "realtime/metrics.py"},
             "CONNECTIONS = []\n\ndef record_open(conn):\n    CONNECTIONS.append(_Sample(conn, time.time()))\n\ndef snapshot():\n    return len(CONNECTIONS)", False),
            ("assistant", "Found it. `metrics.CONNECTIONS` is a module-level list that only ever grows — `record_open` appends a `_Sample` holding a strong reference to the `Connection`, and nothing ever removes it. `snapshot()` only reads the length, so the objects themselves are pure garbage retention.\n\nThe metric only needs a **count**, not the objects:"),
            ("tool", "Edit", {"file_path": "realtime/metrics.py",
                               "old_string": "CONNECTIONS = []\n\ndef record_open(conn):\n    CONNECTIONS.append(_Sample(conn, time.time()))\n\ndef snapshot():\n    return len(CONNECTIONS)",
                               "new_string": "_open_count = 0\n\ndef record_open(conn):\n    global _open_count\n    _open_count += 1\n\ndef record_close(conn):\n    global _open_count\n    _open_count -= 1\n\ndef snapshot():\n    return _open_count"},
             "Edit applied to realtime/metrics.py", False),
            ("tool", "Bash", {"command": "pytest tests/test_metrics.py -q", "description": "Verify metrics tests still pass"},
             "F..\ntests/test_metrics.py::test_snapshot_counts_open FAILED\n\nE   AssertionError: assert 0 == 2\nE    +  where 0 = snapshot()\n\n1 failed, 2 passed", False),
            ("assistant", "Expected — the test never calls `record_close`, so the counter drops below what it asserts. The test was written against the leaking implementation. Let me update it to open and close symmetrically."),
            ("tool", "Bash", {"command": "pytest tests/test_metrics.py -q", "description": "Re-run after fixing the test"},
             "...\n3 passed in 0.44s", False),
            ("assistant", "Green. Worth watching RSS on one canary worker for a full day before rolling out — the leak took six hours to show, so a short soak wouldn't prove much."),
        ],
    ),
    (
        "Write the incident postmortem for the payment outage",
        "/home/dev/storefront", "main", 54,
        [
            ("user", "Draft a postmortem for Tuesday's 43-minute payment outage. Root cause was an expired TLS certificate on the processor callback endpoint."),
            ("assistant", "## Incident: payment callbacks failing\n\n**Duration:** 43 minutes · **Impact:** ~1,850 orders stuck in `pending`\n\n### What happened\n\nThe TLS certificate on `callbacks.internal` expired at 02:14 UTC. Our payment processor could no longer deliver webhooks, so orders were authorised but never marked paid. Customers saw a spinner and many retried, creating duplicate authorisations.\n\n### Why it wasn't caught\n\nThe certificate was issued manually during last year's migration and never added to the renewal automation. Monitoring checked that the endpoint **responded**, not that its certificate was valid — so the check stayed green until the handshake failed outright.\n\n### Remediation\n\n1. Move `callbacks.internal` onto the automated renewal path — *owner: platform, due this week*\n2. Add certificate-expiry alerting at 30/14/7 days for every internal endpoint\n3. Reconcile the 1,850 pending orders and refund duplicate authorisations\n4. Audit for other manually-issued certificates\n\n### What went well\n\nThe on-call engineer identified the cause in 11 minutes from the handshake error, and the reconciliation script from a prior incident worked unmodified."),
            ("user", "Add a timeline section with the key timestamps."),
        ],
    ),
    (
        "Migrate the search index to the new cluster",
        "/home/dev/search-service", "chore/cluster-migration", 76,
        [
            ("user", "We need to move the search index to the new cluster with no downtime. Roughly 40M documents."),
            ("assistant", "For zero downtime with 40M documents the usual approach is dual-write then backfill then cut over:\n\n1. **Dual-write** to old and new clusters, ignoring failures on the new one so a problem there can't break production.\n2. **Backfill** historical documents into the new cluster while dual-writes keep the tail current.\n3. **Shadow-read** — serve from old, compare against new, measure divergence.\n4. **Cut over** reads once divergence is acceptably low, keeping dual-writes until you're confident.\n\nThe risky step is 2, because a backfill racing live writes can overwrite newer data with older. Using the document's `updated_at` as an external version solves that — the cluster then rejects any write older than what it already holds."),
            ("tool", "Bash", {"command": "curl -s $NEW_CLUSTER/_cluster/health | jq .", "description": "Check the new cluster is healthy"},
             '{\n  "cluster_name": "search-v2",\n  "status": "green",\n  "number_of_nodes": 6,\n  "active_primary_shards": 24,\n  "unassigned_shards": 0\n}', False),
            ("assistant", "Cluster is green with 6 nodes and no unassigned shards — good starting point. I'd size the backfill at 5,000 documents per batch and watch indexing latency before going faster."),
            ("user", "How long should the backfill take at that rate?"),
            ("assistant", "At 5,000 docs/batch with the cluster comfortably handling ~4 batches/second, that's roughly **20,000 docs/second** — so 40M documents lands around **35 minutes** of wall time if nothing throttles.\n\nRealistically budget 2–3× that. Backfills slow down as segment merges kick in, and you'll want to pause if indexing latency on the live path rises. I'd schedule a 2-hour window and treat finishing early as a bonus."),
        ],
    ),
    (
        "Review the rate limiter implementation",
        "/home/dev/api-gateway", "review/rate-limiter", 122,
        [
            ("user", "Can you review the token bucket rate limiter before I merge it?"),
            ("tool", "Read", {"file_path": "gateway/ratelimit.py"},
             "class TokenBucket:\n    def __init__(self, rate, capacity):\n        self.rate = rate\n        self.capacity = capacity\n        self.tokens = capacity\n        self.updated = time.time()\n\n    def allow(self, cost=1):\n        now = time.time()\n        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)\n        self.updated = now\n        if self.tokens >= cost:\n            self.tokens -= cost\n            return True\n        return False", False),
            ("assistant", "The algorithm is right — refill is proportional to elapsed time and capped at capacity, which is the correct token bucket shape. Three issues worth addressing before merge:\n\n**1. Not thread-safe.** `allow()` does read-modify-write on `self.tokens` with no lock. Under concurrent requests two callers can both observe enough tokens and both succeed, letting bursts through. A `threading.Lock` around the body is enough.\n\n**2. `time.time()` is wall-clock.** It can jump backwards (NTP correction, manual set), making `now - self.updated` negative and *removing* tokens. Use `time.monotonic()`.\n\n**3. No upper bound on `cost`.** A caller passing `cost` greater than `capacity` can never succeed and will retry forever. Worth raising `ValueError` at construction or clamping.\n\nThe first two are correctness bugs; the third is a foot-gun. None are hard to fix."),
            ("user", "Good points. Is the monotonic clock available on all our targets?"),
            ("assistant", "Yes — `time.monotonic()` has been in the standard library since Python 3.3 and is available on every platform you deploy to (Linux, macOS, Windows). It's guaranteed never to go backwards, though it isn't comparable across processes or reboots, which doesn't matter here since the bucket is per-process and short-lived."),
        ],
    ),
    (
        "Add structured logging across the worker fleet",
        "/home/dev/analytics-pipeline", "feat/structured-logs", 171,
        [
            ("user", "Our logs are unparseable free text. I want structured JSON logs with a request id threaded through everything."),
            ("assistant", "The threading part is what makes this worth doing properly. A `contextvars.ContextVar` holding the request id lets any log call pick it up without passing it through every function signature — and unlike thread-locals it survives `async` correctly."),
            ("tool", "Write", {"file_path": "common/logging.py",
                                "content": "import contextvars, json, logging, time\n\nrequest_id = contextvars.ContextVar('request_id', default=None)\n\nclass JsonFormatter(logging.Formatter):\n    def format(self, record):\n        payload = {\n            'ts': time.time(),\n            'level': record.levelname,\n            'logger': record.name,\n            'msg': record.getMessage(),\n        }\n        rid = request_id.get()\n        if rid:\n            payload['request_id'] = rid\n        if record.exc_info:\n            payload['exc'] = self.formatException(record.exc_info)\n        return json.dumps(payload)"},
             "Wrote 19 lines to common/logging.py", False),
            ("tool", "Bash", {"command": "python -m pytest tests/test_logging.py -q", "description": "Test the formatter"},
             "....\n4 passed in 0.19s", False),
            ("assistant", "Formatter is in and tested. Two things to decide before rolling it out fleet-wide:\n\n- **Log volume.** JSON is more verbose than the current format — expect roughly 1.6× the bytes. Worth checking your retention budget.\n- **Rollout order.** Ship the formatter to one worker class first. If your log aggregator has parsing rules built on the old format, they'll break silently and you'd rather find that on one service than twenty."),
        ],
    ),
]


# Fixed namespace so every run produces the same ids. The demo is committed,
# so random ids would rename all of its files on each rebuild.
_NS = uuid.UUID("6f1c9a4e-2b77-5d31-9e84-11f0a7c3d520")


def stable_id(*parts: object) -> str:
    return str(uuid.uuid5(_NS, "|".join(str(p) for p in parts)))


def _record(kind: str, ts: datetime, cwd: str, branch: str, content, parent: str | None,
            seed: object = "", **extra) -> dict:
    return {
        "type": kind,
        "uuid": stable_id(cwd, branch, kind, seed),
        "parentUuid": parent,
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "cwd": cwd,
        "gitBranch": branch,
        "message": {"role": kind, "content": content},
        **extra,
    }


def build_transcript(title, cwd, branch, hours_ago, turns) -> list[dict]:
    """Turn a scripted session into Claude Code `.jsonl` records."""
    # Anchored to a fixed hour rather than "now", so reruns on the same day
    # produce byte-identical output instead of churning the committed demo.
    # Still relative to today, so the Today / Yesterday grouping stays real.
    anchor = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0)
    start = anchor - timedelta(hours=hours_ago)
    records: list[dict] = [{"type": "ai-title", "aiTitle": title}]
    parent = None
    clock = start

    for turn in turns:
        clock += timedelta(seconds=45 + (len(records) * 17) % 180)

        if turn[0] == "user":
            rec = _record("user", clock, cwd, branch, [{"type": "text", "text": turn[1]}], parent,
                          seed=(title, len(records)))
            records.append(rec)
            parent = rec["uuid"]
        elif turn[0] == "assistant":
            rec = _record("assistant", clock, cwd, branch, [{"type": "text", "text": turn[1]}], parent,
                          seed=(title, len(records)))
            records.append(rec)
            parent = rec["uuid"]
        else:
            _, name, tool_input, output, is_error = turn
            tool_id = "toolu_" + uuid.uuid5(_NS, f"{title}|{len(records)}").hex[:20]
            call = _record("assistant", clock, cwd, branch,
                           [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}], parent,
                           seed=(title, len(records), "call"))
            records.append(call)
            result = _record("user", clock + timedelta(seconds=3), cwd, branch,
                             [{"type": "tool_result", "tool_use_id": tool_id,
                               "content": [{"type": "text", "text": output}], "is_error": is_error}],
                             call["uuid"], seed=(title, len(records), "result"))
            records.append(result)
            parent = result["uuid"]

    records.append({"type": "last-prompt", "lastPrompt": turns[-1][1] if turns[-1][0] != "tool" else title})
    return records


def scrub(output: str, *tmp_roots: str) -> int:
    """Replace the build machine's temp path with a neutral placeholder.

    The exporter records each session's source path in manifest.json and in
    the `Source` row of conversation.md. For a demo that gets committed and
    published, that would leak the directory it happened to be built in.

    Several spellings of the same directory are passed in because macOS
    resolves the temp dir through a `/private` symlink — whichever form the
    exporter stored has to match. Returns the number of files rewritten.
    """
    roots = sorted({r for r in tmp_roots if r}, key=len, reverse=True)
    changed = 0

    # The manifest stamps each entry with the time of export, which would be
    # the only thing changing between otherwise identical rebuilds.
    manifest_path = os.path.join(output, "manifest.json")
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        for entry in manifest.values():
            entry["exported_at"] = "2026-01-01T00:00:00Z"
            entry["mtime"] = 0.0
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

    for dirpath, _dirnames, filenames in os.walk(output):
        for name in filenames:
            if not name.endswith((".md", ".json", ".html")):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            replaced = text
            for root in roots:
                replaced = replaced.replace(root, "/demo")
            if replaced != text:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(replaced)
                changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default=os.path.join(ROOT, "docs", "demo"), help="Where to write the demo archive")
    ap.add_argument("--open", action="store_true", help="Open the result when finished")
    args = ap.parse_args()

    output = os.path.abspath(args.output)
    if os.path.isdir(output):
        shutil.rmtree(output)

    with tempfile.TemporaryDirectory() as projects:
        for title, cwd, branch, hours_ago, turns in SESSIONS:
            project_dir = "-" + cwd.lstrip("/").replace("/", "-")
            os.makedirs(os.path.join(projects, project_dir), exist_ok=True)
            path = os.path.join(projects, project_dir, f"{stable_id(title, cwd)}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for rec in build_transcript(title, cwd, branch, hours_ago, turns):
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "export_claude_chats.py"),
             "--root", projects, "--output", output],
            capture_output=True, text=True,
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode != 0:
            return result.returncode

        scrubbed = scrub(output, projects, os.path.realpath(projects))
        print(f"scrubbed build paths from {scrubbed} files")

    index = os.path.join(output, "index.html")
    print(f"\nDemo archive: {index}")
    print(f"Search page:  {os.path.join(output, 'index', 'search.html')}")
    print("\nAll content is fictional — safe to screenshot and publish.")

    if args.open:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, index], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
