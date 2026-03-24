---
title: "Agent-Friendly CLI Design"
date: 2026-03-24T00:00:00+0800
tags: [cli, llm, agents, developer-tools]
---

Notes on what makes a CLI tool usable by AI agents, based on comparing [lgtm-cli](https://github.com/pokgak/lgtm-cli) (Grafana LGTM stack) with [pup](https://github.com/DataDog/pup) (Datadog CLI).

Traditional CLIs are built for humans reading terminal output. Agent-friendly CLIs treat their own interface as an API: structured input, structured output, self-documenting schemas, and actionable errors. The cost of adding these features is low, but it dramatically improves how well AI agents can use your tools.

## Self-Discoverable Commands

CLIs that output their own command schema as JSON (not just `--help` text) let AI agents understand capabilities without parsing documentation. Instead of scraping `--help` output and guessing at flag combinations, the agent gets a machine-readable description of everything the tool can do.

Example: `pup agent schema` returns the full command tree, flags, query syntax, and best practices as structured JSON. An agent can call this once at the start of a session and know exactly what's available.

Compare this to `--help` text, which varies wildly between tools, has no guaranteed structure, and often omits important details like valid enum values or flag interactions.

## Structured Output Envelopes

Wrapping responses in a consistent envelope helps agents handle responses uniformly:

```json
{
  "status": "success",
  "data": [...],
  "metadata": {
    "count": 42,
    "command": "tool query --filter ..."
  }
}
```

The agent always knows where to find the data, whether it was truncated, and what command produced it. Without this, agents have to guess whether output is CSV, plain text, a table, or something else — and parsing heuristics break across tool versions.

## Actionable Error Messages

Instead of just `Error: auth failed`, return structured errors with recovery suggestions:

```json
{
  "status": "error",
  "error_message": "Authentication failed: API key expired",
  "suggestions": [
    "Run 'tool auth login' to re-authenticate",
    "Set API_KEY environment variable",
    "Check token expiry with 'tool auth status'"
  ]
}
```

This lets agents self-recover without human help. The agent can try each suggestion in order, rather than asking the user what to do or searching documentation.

## Agent Auto-Detection

Detecting AI agent callers via environment variables (`CLAUDECODE`, `CURSOR_AGENT`, etc.) and auto-switching to machine-friendly output — no `--agent` flag needed.

When an agent is detected:
- Help output switches to JSON schema instead of formatted text
- Errors include structured suggestions
- Interactive prompts are skipped (fail with actionable error instead of hanging)
- Output defaults to JSON instead of human-formatted tables

This is better than requiring `--json` or `--agent` flags because agents don't always control the initial invocation. Environment-based detection works even when the agent is calling a script that calls the CLI internally.

## Practical Implications

For lgtm-cli specifically, adding an `agent schema` command and structured error responses would make it significantly easier for the lgtm agent skill and lgtm-mcp to use it programmatically. Right now the skill has to know the CLI's interface upfront — with a schema command, it could discover capabilities at runtime.

The pattern generalizes: any CLI that might be called by an AI agent (which is increasingly all of them) benefits from treating its interface as an API surface rather than a human-readable display.
