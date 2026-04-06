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

## AXI: 10 Principles for Agent-Ergonomic CLIs

[AXI](https://axi.md/) takes these ideas further with a research-backed framework. Their benchmark (490 browser automation runs, 425 GitHub runs) shows that principled CLI design beats protocol choice — AXI-style CLIs hit 100% success rates at lower cost than both raw CLIs and MCP.

### Token Efficiency

The biggest insight: agents burn context window on verbose output. AXI addresses this with:

- **Token-optimized output format** — skip JSON braces/quotes/commas for ~40% token savings. LLMs parse it fine.
- **Minimal defaults** — return 3-4 fields per list item, not 10+. Let agents opt-in to more with `--fields`.
- **Content truncation with hints** — `"(truncated, 2847 chars total — use --full)"` instead of dumping everything. The agent decides if it needs the rest.

### Pre-Computed Aggregates

Eliminate round trips by including derived fields. Instead of making the agent count results or check CI status across multiple calls:

```
totalCount: 42
ci: 27 passed, 0 failed, 10 skipped
```

One call instead of three.

### Combined Operations

Collapse multi-step sequences into single commands. In browser automation, `click --query` returns the updated page snapshot automatically — no separate "click" then "screenshot" calls. `fill @uid --submit` fills a form, submits, waits for load, and returns the new state in one shot.

This reduced browser tasks from ~13 turns (code-writing approach) to 4.5 turns.

### Definitive Empty States

Never return empty output. Agents can't tell "no results" from "silent failure":

```
# Bad: (no output)

# Good:
issues[0]: No open issues matching "login bug"
```

### Contextual Disclosure (Next-Step Hints)

Append `help[]` lines after output suggesting what to do next:

```
help: view issue details → gh-axi issues view <number>
help: filter by label   → gh-axi issues --label bug
```

This is like actionable error messages but for success paths — the agent always knows what's possible next without reading docs.

### Ambient Context

Auto-install into shell session hooks to display a compact dashboard of relevant state before the agent even asks. Directory-scoped, so `cd`-ing into a repo shows open PRs, CI status, etc. The agent starts with context instead of spending turns discovering it.

### Key Takeaway

The empirical results are striking: AXI CLIs achieved 100% success at $0.05-0.07/task, while MCP averaged 82-87% success at $0.10-0.15/task. The interface design matters more than the protocol. Structured errors to stdout (not stderr), no interactive prompts, idempotent mutations, and clean exit codes form the baseline — the principles above are what separate good from great.

## Practical Implications

For lgtm-cli specifically, adding an `agent schema` command and structured error responses would make it significantly easier for the lgtm agent skill and lgtm-mcp to use it programmatically. Right now the skill has to know the CLI's interface upfront — with a schema command, it could discover capabilities at runtime.

The pattern generalizes: any CLI that might be called by an AI agent (which is increasingly all of them) benefits from treating its interface as an API surface rather than a human-readable display.

We tested these ideas by applying AXI principles to lgtm-cli and running controlled experiments — see [AXI Principles Experiment: lgtm-cli Before & After](/notes/axi-principles-lgtm-cli-experiments/) for the full results. TL;DR: contextual hints reduced CLI calls by 15-25% and errors by 80%, but content truncation (which we didn't implement) would have the highest impact.
