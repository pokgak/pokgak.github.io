---
title: "Agent-Friendly CLI Design"
date: 2026-03-24T00:00:00+0800
tags: [cli, llm, agents, developer-tools]
---

What makes a CLI usable by AI agents. Based on comparing [lgtm-cli](https://github.com/pokgak/lgtm-cli) with [pup](https://github.com/DataDog/pup) (Datadog CLI).

Core idea: treat the CLI interface as an API — structured input, structured output, self-documenting schemas, actionable errors.

## Self-Discoverable Commands

- Output command schema as JSON, not just `--help` text
- Agent calls once at session start, knows everything available
- Example: `pup agent schema` returns full command tree, flags, query syntax as structured JSON
- `--help` varies wildly between tools, no guaranteed structure, often omits valid enum values

## Structured Output Envelopes

- Wrap responses in a consistent envelope: `{ status, data, metadata: { count, command } }`
- Agent always knows where to find data, whether it was truncated, what command produced it
- Without this, agents guess if output is CSV, plain text, or table — parsing heuristics break across versions

## Actionable Error Messages

- Instead of `Error: auth failed`, return structured errors with recovery suggestions
- `{ status: "error", error_message: "...", suggestions: ["Run 'tool auth login'", ...] }`
- Lets agents self-recover without human help

## Agent Auto-Detection

- Detect AI agent callers via env vars (`CLAUDECODE`, `CURSOR_AGENT`, etc.)
- Auto-switch to machine-friendly output — no `--agent` flag needed
- When detected: JSON help, structured errors, skip interactive prompts, default to JSON output
- Better than `--json` flag because agents don't always control the initial invocation

## AXI: 10 Principles for Agent-Ergonomic CLIs

[AXI](https://axi.md/) research-backed framework. Benchmark: 490 browser automation runs, 425 GitHub runs. AXI CLIs hit 100% success at lower cost than both raw CLIs and MCP.

Key principles:

- **Token-optimized output** — skip JSON braces/quotes for ~40% savings. LLMs parse it fine
- **Minimal defaults** — return 3-4 fields per list item, not 10+. Let agents opt-in with `--fields`
- **Content truncation with hints** — `"(truncated, 2847 chars total — use --full)"` instead of dumping everything
- **Pre-computed aggregates** — include derived fields (`totalCount: 42`, `ci: 27 passed, 0 failed`) to eliminate round trips
- **Combined operations** — collapse multi-step sequences into single commands. Reduced browser tasks from ~13 turns to 4.5
- **Definitive empty states** — never return empty output. `issues[0]: No open issues matching "login bug"` not silence
- **Contextual disclosure** — append `help[]` lines suggesting next steps after output
- **Ambient context** — auto-install into shell hooks to show relevant state before agent asks

Key result: AXI CLIs achieved 100% success at $0.05-0.07/task vs MCP at 82-87% success at $0.10-0.15/task. Interface design matters more than protocol.

## Practical Implication

For lgtm-cli: adding `agent schema` + structured errors would improve programmatic usage by the lgtm skill and lgtm-mcp. Pattern generalizes to any CLI that might be called by an agent.

We tested these ideas — see [AXI Principles Experiment](/experiments/axi-principles-lgtm-cli-experiments/) for results. TL;DR: contextual hints reduced CLI calls by 15-25% and errors by 80%, but content truncation (not implemented) would have highest impact.
