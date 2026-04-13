---
title: "Your Claude History IS Your Weekly Update"
date: 2026-04-13T12:12:04+0800
tags: [llm, agents, claude-code, productivity]
---

Every session you run with Claude Code gets written to a `.jsonl` file under `~/.claude/projects/`. Those files are your work log — you just haven't been reading them.

## The Prompt

When you need to generate your weekly update, give Claude this prompt:

```
Go through my Claude session files under ~/.claude/projects/ for all work-related
repos, find all .jsonl files modified in the last 7 days, extract the first user
prompt from each session, and group them into a weekly summary organized by
repo/theme. Estimate hours based on message count. Format it as a team update
with bullet points per area. Skip personal/non-work sessions.
```

## How It Works

Claude Code writes every session as an append-only `.jsonl` to:

```
~/.claude/projects/<encoded-working-dir>/<session-uuid>.jsonl
```

The path encoding is just `/` → `-`, so `/Users/you/Work/myproject/backend`
becomes `-Users-you-Work-myproject-backend`. Each repo you `cd` into gets
its own bucket. Git worktrees get their own bucket too.

Each line in the file is a JSON event: user message, assistant message, tool call,
tool result, or summary. The first `user` event with a `text` content block is
effectively the session title — it's whatever you typed to kick things off.

To find recent sessions across all repos:

```bash
find ~/.claude/projects -name "*.jsonl" -newer ~/.claude/projects/some-reference-file
```

Or just sort by mtime and filter by date in Python — that's what Claude does when
you ask it.

## What You Get

A session started with:

> "can you help me investigate the alert spike in the production cluster"

...with 680 messages → probably 1.5-2h of work on that investigation.

A session with 15 messages → quick task, ~0.25h.

Message count is a rough but useful heuristic for time spent. You'll want to
sanity-check outliers (very long sessions can be one deep investigation or
several unrelated things chained together).

## Why This Works Better Than Manual Logging

- Zero overhead — the log writes itself as a side effect of working
- First prompt captures intent better than a summary you write after the fact
- Message count gives you time estimation without a stopwatch
- Covers everything across all repos, not just the stuff you remembered to log

The main gap: sessions where you did a lot of work but with few back-and-forth
messages (e.g., long autonomous runs). Those look deceptively short. Adjust
for those manually.
