---
title: "Testing Agent Skills"
date: 2026-04-07T00:00:00+0800
tags: [llm, agents, testing, evals]
---

Testing agent skills (Claude Code plugins that guide model behavior). Based on [Honeycomb's agent-skills](https://github.com/honeycombio/agent-skills), applied to my [LGTM skill](https://github.com/pokgak/agent-skills).

Core question: **does the skill text actually change how the model behaves?** Two testing layers at different speeds and costs.

## Layer 1: Skill-Pressure Tests

Fast, cheap. Verify skill text steers model reasoning. No tools, no API calls — text in, text out.

**How it works:**
1. Run Claude with prompt + `--max-turns 1` + no tools
2. Run again with skill content in system prompt
3. Check required patterns appear (anti-patterns don't)

```yaml
- id: aggregation-before-raw-fetch
  prompt: "Error spike in checkout service. How investigate using Loki?"
  without_skill:
    expected_patterns:
      - "(?i)\\b(grep|search|query|fetch)\\b.*\\b(log|error)\\b"
  with_skill:
    required_patterns:
      - "(?i)count_over_time|aggregat|count.*first|overview.*first"
```

The `without_skill.expected_patterns` establishes a RED baseline — confirms the model defaults to "wrong" behavior without guidance. If the model already does the right thing, the test isn't measuring anything.

**Good scenario design:**
- One behavioral axis per scenario
- Patterns match intent, not exact syntax — `(?i)count_over_time|aggregat` catches both specific function and general concept
- Anti-patterns optional — only when verifying skill suppresses a specific bad behavior

**Running:** `python tests/skill-pressure/run.py` — ~2-3 min for 8 scenarios, no external services.

## Layer 2: Scenario Tests

End-to-end, full multi-turn Claude conversations. Evaluates tool calls made.

**How it works:**
1. Run Claude with prompt + `--output-format stream-json` + allowed tools including `Skill,Task`
2. Run again without `Skill,Task` in allowed tools
3. Parse NDJSON output for all tool calls and arguments
4. Score both runs against rubric, compare

**Scoring rubric:**

| Component | Weight | What |
|-----------|--------|------|
| Required tools | 30% | Expected tools called? |
| Required patterns | 25% | Expected strings in tool args? |
| Anti-patterns | 20% | Bad patterns absent? |
| Tool ordering | 15% | Right sequence? |
| Recommended tools | 10% | Optional bonus |

**Pass criteria:**
- Comparison: `delta = with - without >= -0.1` (accounts for LLM non-determinism)
- Skill-only: `score >= 0.6`

**Running:** `make test-scenarios` — ~20-40 min. Raw output at `tests/scenarios/output/`.

## Results from LGTM Skill

### Skill-pressure: 8/8 passed

All scenarios confirmed steering. One notable finding: `percentiles-for-latency` baseline was "not RED" — Sonnet already knows to suggest percentiles without the skill. Less valuable as regression test.

### Scenario tests: comparison tests are inherently flaky

Skill-only tests pass 100% consistently. Comparison tests randomly fail 1-2 scenarios per run:

| Scenario | Run 1 | Run 2 | Run 3 |
|----------|-------|-------|-------|
| investigate-error-spike | PASSED | PASSED | PASSED |
| service-health-check | PASSED | FAILED | PASSED |
| trace-slow-requests | PASSED | FAILED | PASSED |
| metrics-trend-with-chart | PASSED | PASSED | FAILED |
| cross-signal-investigation | PASSED | PASSED | PASSED |
| **skill-only (all 5)** | **PASSED** | **PASSED** | **PASSED** |

**Why:** two independent Claude conversations produce wildly different scores for reasons unrelated to the skill. Delta between two stochastic runs isn't reliable at n=1.

**What would fix it:** run K times and compare averages, use skill-only as primary signal, use cheaper models for more repetitions.

### Key lesson: test patterns, not tool names

Initially all 5 skill-only tests failed. Claude used `Agent` instead of `Task` for subagent calls, and sometimes ran `lgtm` via `Bash` directly. Both valid — just different tools.

Fix: remove `Task` from `required_tools`, rely on `required_patterns` matching `lgtm loki`, `lgtm tempo` etc. All 5 passed after.

**Takeaway:** `required_patterns` (what the agent *says*) > `required_tools` (which tool wrapper it picks). Claude has multiple equivalent paths.

## Design Decisions

- **Deterministic evaluation, no LLM-as-judge** — all scoring is regex. Reproducible, auditable. Trade-off: patterns need careful tuning.
- **Skill-pressure = inner loop** — minutes, catches most skill text issues
- **Scenario tests = outer loop** — catches integration issues, slow and expensive
- **Baseline matters** — RED baseline verifies model does the wrong thing without skill. Without it, passing test might just mean model already knows the answer.
