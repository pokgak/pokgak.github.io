---
title: "Claude /loop: my use cases"
date: 2026-04-09T12:45:27+0800
tags: [llm, agents, claude-code]
---

Claude Code's `/loop` skill runs a prompt or slash command on a recurring interval. You give it a cadence and a command, it keeps running until you stop it. Simple idea, but once you have slash commands for your common ops tasks, it composes into something surprisingly useful.

Here's how I've been using it.

## GPU cluster monitoring

The first thing I reached for. GPU training runs take hours — I don't want to babysit a terminal, I want to be notified when something breaks.

```
/loop every 5m and /check-cluster-health and /check-training-status and DM me on slack for errors
```

This runs every 5 minutes, calls my `/check-cluster-health` and `/check-training-status` slash commands in sequence, and sends a Slack DM only when something needs attention. No noise when everything's fine.

The slash commands are the key piece. `/check-cluster-health` knows to look at node status, GPU utilization, and job queues. `/check-training-status` knows to tail the training logs and parse loss curves. `/loop` just orchestrates the cadence and the alerting.

## Periodic training status reports

A softer version — instead of error-only alerts, post a regular status update to a channel:

```
/loop every 1h to /check-training-status and report on slack #training-status channel
```

Useful for longer runs where you want a paper trail and team visibility. The channel becomes a timeline of the run.

## Production release monitoring

This one has a specific shape: establish a baseline *before* you change anything, then start the loop *after* the change.

```
get a baseline from /monitor-prod-services, then make the release, after that /loop every 3m to /monitor-prod-services and report if any new issues pop up from the release
```

Claude captures the pre-release state of error rates, latency, and any existing alerts. After the release, the loop diffs each report against that baseline and only flags things that are *new*. This filters out pre-existing noise that would otherwise drown out release-caused regressions.

## Overnight experiment runner

This is the one I find most interesting. The idea: instead of running one big exhaustive benchmark, use Claude to drive an iterative experiment loop using Darwinian natural selection — run a diverse generation of candidates, pick the most promising based on early signal, then breed the next round from those survivors.

I wrote a small wrapper around [mlx-bench](https://github.com/pokgak/mlx-bench) that reads from a list of experiments and can pick up the next one each time it's invoked. Then:

```
plan experiments for me, then /loop every 1h to invoke the mlx-bench command, analyze each result and decide what to test next based on Darwinian selection
```

Claude plans the initial candidate set, runs the first experiment, reads the results, decides what to keep or discard, and queues the next run. I wake up to a completed sweep with analysis. The loop is the thing that turns "one benchmark" into "a research loop."

## What makes this pattern work

Three things need to be in place:

1. **Slash commands for your common tasks** — `/loop` is just a scheduler. The value comes from composing it with commands that already know your systems, your log formats, your alerting channels.

2. **Structured output from those commands** — Claude needs to parse results and make decisions. Commands that return consistent, machine-readable summaries are easier to reason over than raw log dumps.

3. **A clear continuation condition** — for experiment loops especially, you need a way for Claude to pick up state between invocations. The mlx-bench wrapper solves this by maintaining a queue file; each invocation reads the next item, runs it, and appends results.

Once those are in place, `/loop` turns Claude from a one-shot assistant into something closer to an autonomous operator for the things you've already scripted.

## Related work

Two projects explore similar territory from different angles.

**[autoresearch](https://github.com/karpathy/autoresearch)** by Karpathy is the most direct parallel to the overnight experiment runner use case. The setup: give an agent a single training file (`train.py`) and a fixed 5-minute budget per run, let it modify the code, train, measure val loss, keep or discard, and repeat. ~100 experiments while you sleep. The key design choice is the fixed time budget — it makes every experiment directly comparable regardless of what the agent changes (architecture, optimizer, batch size). My `/loop` approach is less structured: Claude decides what to test next based on Darwinian selection rather than modifying a single canonical file. autoresearch is tighter by design; `/loop` trades that tightness for flexibility across different experiment types.

**[The ralph loop](https://ghuntley.com/loop/)** by Geoffrey Huntley is a broader philosophical take. His "ralph loop" is a monolithic autonomous process that runs a full software development cycle — allocate specs, execute, verify, repeat — replacing the sequential brick-by-brick model of software construction. The parallel to my use cases is the ops monitoring loops: a process that continuously observes, evaluates, and acts without human intervention between cycles. Where my loops are narrow (monitor this cluster, check these metrics), Huntley's vision is a single loop that owns the entire development lifecycle. The difference is scope and trust — I use `/loop` for well-defined, bounded tasks where I've already scripted what "good" looks like; his loop is meant to reason about the whole problem from scratch each cycle.

One structural difference worth noting: `/loop` runs inside a single Claude session, so context accumulates across iterations — Claude remembers what it saw in the previous run, what it decided, and why. The ralph loop starts a fresh session each iteration, so it relies on the spec (`program.md`) to carry all the context it needs. Both are valid designs. Fresh sessions are more robust (no risk of context window exhaustion on long runs, decisions stay grounded in the spec rather than drifting from accumulated state); accumulated context lets Claude reason across iterations without writing everything down — useful when the signal from each run is rich and you want the agent to notice trends over time.
