---
title: "AXI Principles Experiment: lgtm-cli Before & After"
date: 2026-04-06T00:00:00+0800
tags: [cli, llm, agents, experiments, observability]
---

Companion to [Agent-Friendly CLI Design](/notes/agent-friendly-cli-design/) — this documents experiments testing [AXI principles](https://axi.md/) applied to [lgtm-cli](https://github.com/pokgak/lgtm-cli), an observability CLI for Grafana's LGTM stack.

## What We Changed

We applied four AXI principles to lgtm-cli's `--envelope` mode ([PR #5](https://github.com/pokgak/lgtm-cli/pull/5)):

1. **Definitive empty states** — envelope includes `empty: true` and `message: "No results found"` when count is 0
2. **Contextual disclosure** — every command returns `hints[]` with concrete next-step command templates using `<placeholders>`
3. **Limit-reached warnings** — log/trace queries detect when results hit the limit and add a hint
4. **Errors to stdout in envelope mode** — structured errors go to stdout so agents always capture them

## Experiment Setup

Three investigation tasks, each run twice: once with raw JSON output (baseline) and once with envelope+hints. Each experiment ran in an isolated Sonnet agent with identical prompts except for the `--envelope` flag. A tracking wrapper logged every CLI call (command, output bytes, duration).

**Instance:** `primeintellect` on Grafana Cloud (Loki, Prometheus, Tempo)

### Tasks

1. **Error log discovery** — "Find what apps are logging errors and show example error logs from the top 2 most active apps"
2. **Cross-signal correlation** — "Find the slowest traces in the last 15 minutes and check if there are corresponding error logs"
3. **GPU metrics discovery** — "Check what Prometheus metrics are available for GPU monitoring and get current utilization values"

## Results

### Task 1: Error Log Discovery

| Metric | Raw | Envelope | Delta |
|---|---|---|---|
| CLI calls | 20 | 15 | **-25%** |
| Failed calls | 0 | 0 | — |
| Output tokens | 32,316 | 15,838 | **-51%** |
| Duration (ms) | 39,172 | 20,872 | **-47%** |
| Agent tool uses | 22 | 17 | **-23%** |

The envelope agent followed hints like `"get values → lgtm loki label-values <label>"` instead of spending calls on `--help` and trial-and-error. Both found the same top services (`inference-dynamo-frontend-main`, `coredns`/`pi-sandbox-gateway`).

### Task 2: Cross-Signal Correlation

| Metric | Raw | Envelope | Delta |
|---|---|---|---|
| CLI calls | 34 | 29 | **-15%** |
| Failed calls | 10 | 2 | **-80%** |
| Output tokens | 3,741,744 | 155,024 | **-96%** |
| Duration (ms) | 35,478 | 35,900 | ~same |
| Agent tool uses | 35 | 30 | **-14%** |

The biggest win here was **error reduction**: the raw agent made 10 failed calls due to CLI syntax confusion (wrong flags, wrong subcommand structure). The envelope agent only failed twice. The 96% token reduction is partly misleading — the raw agent happened to dump full trace payloads while the envelope agent was more targeted, but both explored similar traces.

The cross-signal hint was used directly: after `tempo trace <id>`, the envelope agent saw `"find logs → lgtm loki query '{traceID=\"<id>\"}'` and used it to correlate traces with logs.

### Task 3: GPU Metrics Discovery

| Metric | Raw | Envelope | Delta |
|---|---|---|---|
| CLI calls | 11 | 13 | +18% |
| Failed calls | 1 | 3 | +2 |
| Output tokens | 131,849,807 | 13,397,202 | **-90%** |
| Duration (ms) | 25,505 | 9,108 | **-64%** |
| Agent tool uses | 13 | 16 | +23% |

Hints didn't help here — both agents needed to figure out PromQL patterns like `{__name__=~".*DCGM.*"}` which is domain knowledge, not CLI discoverability. The envelope agent actually made more calls and had more failures. The token reduction is entirely because the raw agent ran `prom series` with a broad regex returning 500MB of JSON.

## What Worked

**Contextual hints reduce `--help` calls.** The raw agents consistently called `--help` on subcommands before using them. The envelope agents skipped this because hints after each command showed what to do next with concrete syntax.

**Cross-signal hints are the killer feature.** The `tempo trace` → `loki query` hint let the envelope agent correlate traces with logs without figuring out the relationship between backends. This is exactly AXI's "combined operations" principle — not literally combining commands, but showing the agent the logical next step across signal types.

**Error reduction matters more than token savings.** Going from 10 to 2 failed calls (Task 2) saved more real time than any output size reduction, because each failure triggers retry loops and `--help` lookups.

## What Didn't Work

**Hints can't teach domain expertise.** PromQL, LogQL, and TraceQL patterns need to be known upfront. Hints like `"query metric → lgtm prom query '<metric_name>'"` don't help when the agent doesn't know which metric name to use. A `prom suggest` command that returns common queries for discovered metrics would help more.

**Output truncation is the missing piece.** The single biggest token cost across all experiments was dumping massive API responses — 500MB from `prom series`, multi-MB trace payloads. Our AXI changes didn't address this. Adding auto-truncation with size hints (the AXI "content truncation" principle) would have the highest impact per line of code.

**Envelope overhead on small responses.** For quick commands like `labels` or `label-values`, the envelope and hints add ~30% more tokens to already-small responses. The hints are most valuable on responses where the agent doesn't know what to do next — for simple list/get commands, they're just noise.

## Next Steps

1. **Content truncation** — Auto-truncate responses over N tokens in envelope mode with `"(truncated, showing 50 of 1120 results — use --limit to control)"`. This would address the biggest cost driver.
2. **Domain-specific suggestions** — After `prom labels`, suggest common PromQL patterns for discovered metrics (e.g., if `DCGM_*` metrics exist, suggest GPU monitoring queries).
3. **Adaptive hints** — Only include hints when the response is ambiguous or the agent likely needs guidance. Skip hints on terminal commands like `silence-delete` where there's an obvious single next action.
4. **Run at scale** — These experiments are n=1. Running 10+ iterations per task with different models would give statistical significance.
