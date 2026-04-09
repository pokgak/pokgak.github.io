---
title: "AXI Principles Experiment: lgtm-cli Before & After"
date: 2026-04-06T00:00:00+0800
tags: [cli, llm, agents, experiments, observability]
---

Testing whether [AXI principles](https://axi.md/) applied to [lgtm-cli](https://github.com/pokgak/lgtm-cli) measurably improve agent performance on observability tasks.

Companion to [Agent-Friendly CLI Design](/notes/agent-friendly-cli-design/).

## The Question

Do AXI principles (structured envelopes, contextual hints, definitive empty states) reduce agent errors and token usage when querying Grafana LGTM backends?

## Setup

**Changes applied** ([PR #5](https://github.com/pokgak/lgtm-cli/pull/5)):
1. **Definitive empty states** — envelope includes `empty: true` and `message: "No results found"` when count is 0
2. **Contextual disclosure** — every command returns `hints[]` with concrete next-step command templates using `<placeholders>`
3. **Limit-reached warnings** — log/trace queries detect when results hit the limit and add a hint
4. **Errors to stdout in envelope mode** — structured errors go to stdout so agents always capture them

**Method:** Three investigation tasks, each run twice: raw JSON output (baseline) vs envelope+hints. Isolated Sonnet agent with identical prompts except `--envelope` flag. Tracking wrapper logged every CLI call.

**Instance:** Production Grafana Cloud stack with Loki, Prometheus, and Tempo.

---

## Experiment 1: Error Log Discovery

**Why this matters:** Tests the most common observability workflow — find what's broken, get examples. This is where `--help` avoidance and hint-following should show the biggest improvement.

**Hypothesis:** Envelope agent will make fewer CLI calls (hints replace `--help` lookups) and produce less output tokens (structured responses vs raw JSON dumps). Expect ~20% reduction in calls.

**Method:** Prompt: "Find what apps are logging errors and show example error logs from the top 2 most active apps."

**Results:**

| Metric | Raw | Envelope | Delta |
|---|---|---|---|
| CLI calls | 20 | 15 | **-25%** |
| Failed calls | 0 | 0 | — |
| Output tokens | 32,316 | 15,838 | **-51%** |
| Duration (ms) | 39,172 | 20,872 | **-47%** |
| Agent tool uses | 22 | 17 | **-23%** |

**What this tells us:** Hypothesis confirmed. Envelope agent followed hints like `"get values -> lgtm loki label-values <label>"` instead of spending calls on `--help` and trial-and-error. Both agents identified the same top error-producing services. The 25% call reduction matches our prediction; the 51% token reduction exceeded it.

---

## Experiment 2: Cross-Signal Correlation

**Why this matters:** Cross-signal correlation (traces -> logs) is the hardest observability task for agents — requires knowing the relationship between backends and the right query patterns. This tests whether cross-signal hints can teach that relationship.

**Hypothesis:** Envelope agent will make significantly fewer errors because cross-signal hints (`tempo trace -> loki query`) teach the backend relationship directly. Expect error count to drop by 50%+.

**Method:** Prompt: "Find the slowest traces in the last 15 minutes and check if there are corresponding error logs."

**Results:**

| Metric | Raw | Envelope | Delta |
|---|---|---|---|
| CLI calls | 34 | 29 | **-15%** |
| Failed calls | 10 | 2 | **-80%** |
| Output tokens | 3,741,744 | 155,024 | **-96%** |
| Duration (ms) | 35,478 | 35,900 | ~same |
| Agent tool uses | 35 | 30 | **-14%** |

**What this tells us:** Hypothesis confirmed — error reduction exceeded prediction (80% vs 50%). The raw agent made 10 failed calls due to CLI syntax confusion (wrong flags, wrong subcommands). The 96% token reduction is partly misleading — raw agent happened to dump full trace payloads — but the cross-signal hint was used directly: after `tempo trace <id>`, envelope agent saw `"find logs -> lgtm loki query '{traceID=\"<id>\"}'` and used it.

---

## Experiment 3: GPU Metrics Discovery

**Why this matters:** Tests whether hints help with domain-specific knowledge (PromQL patterns for GPU metrics). If hints can only improve CLI discoverability but not domain expertise, this task should show no improvement.

**Hypothesis:** Hints won't help here — both agents need to figure out PromQL patterns like `{__name__=~".*DCGM.*"}` which is domain knowledge, not CLI discoverability. Expect similar call counts and error rates.

**Method:** Prompt: "Check what Prometheus metrics are available for GPU monitoring and get current utilization values."

**Results:**

| Metric | Raw | Envelope | Delta |
|---|---|---|---|
| CLI calls | 11 | 13 | +18% |
| Failed calls | 1 | 3 | +2 |
| Output tokens | 131,849,807 | 13,397,202 | **-90%** |
| Duration (ms) | 25,505 | 9,108 | **-64%** |
| Agent tool uses | 13 | 16 | +23% |

**What this tells us:** Hypothesis confirmed — hints didn't help with PromQL patterns. Envelope agent made more calls and had more failures. The 90% token reduction is entirely because raw agent ran `prom series` with broad regex returning 500MB of JSON, not because of any behavioral improvement from hints.

---

## Final Summary

### What worked

| Finding | Evidence |
|---------|----------|
| **Contextual hints reduce `--help` calls** | Raw agents consistently called `--help` before using subcommands; envelope agents skipped this |
| **Cross-signal hints are the killer feature** | `tempo trace` -> `loki query` hint taught backend relationship (Task 2: 80% error reduction) |
| **Error reduction > token savings** | 10 -> 2 failed calls (Task 2) saved more real time than output size reduction |

### What didn't work

| Finding | Evidence |
|---------|----------|
| **Hints can't teach domain expertise** | PromQL/LogQL/TraceQL patterns need to be known upfront (Task 3: more errors with envelope) |
| **Output truncation is the missing piece** | Biggest token cost = massive API responses (500MB `prom series`). Our changes didn't address this. |
| **Envelope overhead on small responses** | ~30% more tokens for simple list/get commands where hints are noise |
| **TOON format doesn't help for observability** | Better PromQL gives 500x reduction vs TOON's 40%. Teach the agent to aggregate server-side. |

### Next steps

1. **Content truncation** — auto-truncate over N tokens with `"(truncated, showing 50 of 1120 results)"`. Biggest cost driver.
2. **Domain-specific suggestions** — after `prom labels`, suggest common PromQL for discovered metrics
3. **Adaptive hints** — only include when response is ambiguous, skip on terminal commands
4. **Run at scale** — these are n=1. Need 10+ iterations for statistical significance.
