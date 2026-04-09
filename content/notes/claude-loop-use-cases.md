---
title: "Claude /loop: my use cases"
date: 2026-04-09T12:45:27+0800
tags: [llm, agents, claude-code]
---

Claude Code's `/loop` runs a prompt or slash command on a recurring interval. Once you have slash commands for common ops tasks, it composes into something useful.

## GPU Cluster Monitoring

```
/loop every 5m and /check-cluster-health and /check-training-status and DM me on slack for errors
```

- Runs every 5 min, calls health + training status commands, Slack DM only on errors
- No noise when everything's fine
- Slash commands are the key: `/check-cluster-health` knows to check node status, GPU util, job queues

## Periodic Training Status Reports

```
/loop every 1h to /check-training-status and report on slack #training-status channel
```

- Regular status updates for team visibility
- Channel becomes a timeline of the run

## Production Release Monitoring

```
get a baseline from /monitor-prod-services, then make the release, after that /loop every 3m to /monitor-prod-services and report if any new issues pop up from the release
```

- Capture pre-release state (error rates, latency, existing alerts)
- Loop diffs each report against baseline, only flags *new* issues
- Filters out pre-existing noise

## Overnight Experiment Runner

```
plan experiments for me, then /loop every 1h to invoke the mlx-bench command, analyze each result and decide what to test next based on Darwinian selection
```

- Claude plans initial candidate set, runs experiments, reads results, decides what to keep/discard, queues next run
- Small wrapper around [mlx-bench](https://github.com/pokgak/mlx-bench) reads from experiment list, picks up next one each invocation
- Wake up to completed sweep with analysis

## What Makes This Work

1. **Slash commands for common tasks** — `/loop` is just a scheduler. Value comes from composing it with commands that know your systems.
2. **Structured output** — Claude needs to parse results and make decisions. Machine-readable summaries > raw log dumps.
3. **Clear continuation condition** — for experiment loops, need a way to pick up state between invocations (e.g., mlx-bench wrapper maintains a queue file).

## Related Work

**[autoresearch](https://github.com/karpathy/autoresearch)** (Karpathy)
- Most direct parallel to overnight experiment runner
- Give agent a `train.py` + fixed 5-min budget per run, let it modify/train/measure/keep-or-discard, repeat ~100 experiments
- Single session — context accumulates across experiments
- Key difference: fixed time budget makes every experiment comparable. My `/loop` approach is less structured — Claude decides via Darwinian selection. autoresearch is tighter by design.

**[The ralph loop](https://ghuntley.com/loop/)** (Geoffrey Huntley)
- Broader: monolithic autonomous process for full software dev cycle (allocate specs, execute, verify, repeat)
- Parallel to my ops monitoring loops — continuous observe/evaluate/act without human intervention
- Difference: scope and trust. I use `/loop` for bounded tasks where I've scripted what "good" looks like; ralph loop owns the entire lifecycle.

**Structural difference:** `/loop` and autoresearch run in a single session (context accumulates). Ralph loop starts fresh each iteration (relies on spec for context). Fresh = more robust (no context exhaustion). Accumulated = agent notices trends across iterations.
