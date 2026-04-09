---
title: "MCP Code Mode vs Subagent Pattern for Observability"
date: 2026-03-13T00:00:00+0800
tags: [mcp, llm, observability, lgtm]
---

Two approaches to keeping raw JSON out of the main context window when querying LGTM backends (Loki, Prometheus, Tempo).

## Code Mode (MCP server)

- Inspired by [Cloudflare MCP](https://github.com/cloudflare/mcp)
- Expose 2 tools (`search` + `execute`) — agent writes Python code that runs server-side with LGTM clients injected
- Filtering happens in code before results return
- Implemented in [lgtm-mcp v2.0.0](https://github.com/pokgak/lgtm-mcp)

## Subagent Pattern (agent-skills)

- Main model orchestrates, Haiku subagents execute CLI queries and return summaries
- Entire query execution happens outside main context
- Implemented in the `lgtm` agent skill

## Comparison

| | **Code Mode (MCP)** | **Subagent (agent-skills)** |
|---|---|---|
| **Where filtering happens** | Server-side, in Python code the agent writes | In a Haiku subagent that runs CLI commands and summarizes |
| **What stays out of context** | Raw API responses (agent filters in code before return) | Everything — subagent's entire execution is outside main context |
| **Round-trips** | 1 MCP tool call can do N queries | 1 Task call can do N queries |
| **Cost** | Main model writes code + reads filtered result | Haiku runs queries (cheap), main model only sees summary |
| **Token budget** | ~1,200 tokens (tool descriptions) + filtered results | ~0 tokens for queries, just the summary string |
| **Query flexibility** | Full Python — asyncio.gather, conditionals, transforms | Full bash — pipes, jq, conditionals |
| **Error handling** | Python tracebacks from exec() | Haiku can retry/adapt, or report error in summary |

## Subagent wins

- **Total context isolation** — main model never sees query results, only subagent's summary
- **Cheaper** — Haiku does the grunt work
- **Better summarization** — subagent reasons about what matters before reporting back
- **Proven orchestration** — discovery -> investigation -> synthesis flow with parallel Task calls

## Code mode wins

- **Works in Claude Desktop** — no subagent/Task tool available there
- **Lower latency** for simple queries — no subagent spawn overhead
- **Tighter integration** — typed Python clients with auth, connection pooling, OTel tracing
- **Visual rendering** — Claude Desktop can render charts from returned data
- **Multi-query in one call** — asyncio.gather multiple queries

## When to use which

- **Claude Code / agentic workflows** -> subagent pattern (context isolation is strictly superior, Haiku is cheaper)
- **Claude Desktop** -> code mode MCP (no subagents available, enables visual rendering)

Complementary, not competing — different runtimes, same backends.

## References

- [lgtm-mcp code mode](https://github.com/pokgak/lgtm-mcp) (v2.0.0)
- [Cloudflare MCP](https://github.com/cloudflare/mcp) (inspiration)
