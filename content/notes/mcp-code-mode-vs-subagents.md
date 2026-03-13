---
title: "MCP Code Mode vs Subagent Pattern for Observability"
date: 2026-03-13T00:00:00+0800
tags: [mcp, llm, observability, lgtm]
---

Comparing two approaches to keeping raw JSON out of the main context window when querying LGTM backends (Loki, Prometheus, Tempo).

## The two approaches

**Code Mode (MCP server)** — inspired by [Cloudflare MCP](https://github.com/cloudflare/mcp). Instead of many individual tools, expose 2 tools (`search` + `execute`) where the agent writes Python code that runs server-side with LGTM clients injected into scope. Filtering happens in code before results return. Implemented in [lgtm-mcp v2.0.0](https://github.com/pokgak/lgtm-mcp).

**Subagent Pattern (agent-skills)** — the main model orchestrates, Haiku subagents execute CLI queries and return summaries. The entire query execution happens outside the main context. Implemented in the `lgtm` agent skill.

## Comparison

| | **Code Mode (MCP)** | **Subagent (agent-skills)** |
|---|---|---|
| **Where filtering happens** | Server-side, in Python code the agent writes | In a Haiku subagent that runs CLI commands and summarizes |
| **What stays out of context** | Raw API responses (agent filters in code before return) | Everything — the subagent's entire execution is outside main context |
| **Round-trips** | 1 MCP tool call can do N queries | 1 Task call can do N queries |
| **Cost** | Main model writes code + reads filtered result | Haiku runs queries (cheap), main model only sees summary |
| **Token budget for main model** | ~1,200 tokens (tool descriptions) + filtered results | ~0 tokens for queries, just the summary string |
| **Query flexibility** | Full Python — asyncio.gather, conditionals, transforms | Full bash — pipes, jq, conditionals |
| **Error handling** | Python tracebacks from exec() | Haiku can retry/adapt, or report the error in summary |

## Where subagent wins

- **Context isolation is total** — the main model never sees any query results, only the subagent's summary. Code mode still returns filtered results to the main context.
- **Cheaper** — Haiku does the grunt work. Code mode has the main model (Opus/Sonnet) writing Python, which costs more per token.
- **Better summarization** — the subagent can reason about what matters before reporting back. Code mode just returns data, the main model still has to interpret it.
- **Orchestration pattern is proven** — discovery → investigation → synthesis flow with parallel Task calls is well-established.

## Where code mode wins

- **Works in Claude Desktop** — no subagent/Task tool available there. Code mode is the only way to do multi-query composition in a single tool call.
- **Lower latency for simple queries** — no subagent spawn overhead, direct API call.
- **Tighter integration** — typed Python clients with proper auth, connection pooling, OpenTelemetry tracing. The CLI tool is a separate process each invocation.
- **Visual rendering** — Claude Desktop can render charts/dashboards from the returned data.
- **Multi-query in one call** — can asyncio.gather multiple queries and return combined results.

## When to use which

- **Claude Code / agentic workflows** → subagent pattern. Context isolation is strictly superior, Haiku is cheaper for the query-execute-summarize loop.
- **Claude Desktop** → code mode MCP. No subagents available, and it enables visual chart/dashboard rendering.

They're complementary, not competing — different runtimes, same backends.

## References

- [lgtm-mcp code mode](https://github.com/pokgak/lgtm-mcp) (v2.0.0)
- [Cloudflare MCP](https://github.com/cloudflare/mcp) (inspiration)
