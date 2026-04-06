---
title: "Testing Agent Skills"
date: 2026-04-07T00:00:00+0800
tags: [llm, agents, testing, evals]
---

Notes on testing agent skills (Claude Code plugins that guide model behavior). Based on patterns from [Honeycomb's agent-skills](https://github.com/honeycombio/agent-skills) and applied to my own [LGTM skill](https://github.com/pokgak/agent-skills).

The core question: **does the skill text actually change how the model behaves?** Two testing layers address this at different speeds and costs.

## Layer 1: Skill-Pressure Tests

Fast, cheap tests that verify skill text steers model reasoning. No tools, no API calls — just text in, text out.

### How it works

1. Run Claude with a prompt + `--max-turns 1` + no tools allowed
2. Run again with the same prompt but skill content appended to system prompt
3. Check required patterns appear (and anti-patterns don't) in the response

```yaml
- id: aggregation-before-raw-fetch
  prompt: "There's an error spike in our checkout service. How would you investigate using Loki logs?"
  without_skill:
    expected_patterns:
      - "(?i)\\b(grep|search|query|fetch)\\b.*\\b(log|error)\\b"
  with_skill:
    required_patterns:
      - "(?i)count_over_time|aggregat|count.*first|overview.*first"
    anti_patterns: []
```

The `without_skill.expected_patterns` establishes a RED baseline — it confirms the model defaults to the "wrong" behavior without guidance. This matters because if the model already does the right thing without the skill, the test isn't measuring anything.

### What makes a good skill-pressure scenario

- **One behavioral axis per scenario** — test aggregation-first OR discovery-first, not both at once
- **Patterns should match intent, not exact syntax** — `(?i)count_over_time|aggregat` catches both the specific function and the general concept
- **Anti-patterns are optional** — only add them when you specifically want to verify the skill suppresses a bad behavior (e.g., using AVG for latency)

### Running

```bash
python tests/skill-pressure/run.py                  # all scenarios
python tests/skill-pressure/run.py lgtm             # one file
python tests/skill-pressure/run.py --skill-only     # skip baseline
python tests/skill-pressure/run.py --model opus     # override model
```

Takes ~2-3 minutes for 8 scenarios. No external services needed.

## Layer 2: Scenario Tests

End-to-end tests that run full multi-turn Claude conversations and evaluate the tool calls made.

### How it works

1. Run Claude with a prompt, `--output-format stream-json`, and `--allowedTools Bash,Read,Glob,Grep,Skill,Task` (with skill)
2. Run again with the same prompt but without `Skill,Task` in allowed tools (without skill)
3. Parse NDJSON output to extract all tool calls, their arguments, and text output
4. Score both runs against expected behavior using a weighted rubric
5. Compare scores — fail if the skill caused a regression

The skill is always installed in the repo. The with/without toggle is whether `Skill` and `Task` are in `--allowedTools`. Without those tools, Claude can't activate the skill even though it can see it.

### Scoring rubric

Five components, weighted:

| Component | Weight | What it checks |
|-----------|--------|---------------|
| Required tools | 30% | Did Claude call the expected tools? (e.g., `Task`) |
| Required patterns | 25% | Do tool arguments contain expected strings? (regex on args + text) |
| Anti-patterns | 20% | Are bad patterns absent? |
| Tool ordering | 15% | Were tools called in the right sequence? (e.g., Skill before Task) |
| Recommended tools | 10% | Optional bonus tools |

Empty categories score 1.0 (no penalty). Total score is the weighted sum.

### Pass criteria

**Comparison test:** `delta = with_skill_score - without_skill_score >= -0.1`

The -0.1 threshold accounts for LLM non-determinism. Verdicts:
- `delta > 0.05` → improved
- `delta < -0.1` → regressed (FAIL)
- in between → neutral (pass)

**Skill-only test:** `score >= 0.6`

Just checks "does the skill-enhanced run do a reasonable job?"

### Scenario definition

```yaml
- id: investigate-error-spike
  prompt: "We're seeing a spike in 500 errors from the checkout service. Can you investigate?"
  expected:
    required_tools: [Task]
    required_patterns:
      - "(?i)lgtm loki"
      - "(?i)count_over_time|aggregat"
    anti_patterns: []
    tool_ordering:
      - [Skill, Task]
    recommended_tools: [Skill]
  expected_skills: [lgtm]
  config:
    max_turns: 8
    timeout_ms: 180000
```

### Running

```bash
make test-scenarios                    # all (slow, ~30-60 min)
make test-scenarios-core               # core subset

# single scenario
uv run --group test pytest tests/scenarios/ -v -k "investigate-error-spike"

# inspect results
cat tests/scenarios/output/_comparison_results.json | python -m json.tool
cat tests/scenarios/output/investigate-error-spike/with-skill.ndjson
```

### Debugging failures

Raw NDJSON output is saved per-scenario at `tests/scenarios/output/<id>/{with-skill,without-skill}.ndjson`. The `_comparison_results.json` file has scoring breakdowns showing exactly which patterns matched/missed and which tools were found/missing.

## Results from LGTM skill

First run against the [LGTM skill](https://github.com/pokgak/agent-skills) using Claude Sonnet.

### Skill-pressure: 8/8 passed

All scenarios confirmed the skill text steers behavior correctly:

| Scenario | Baseline (no skill) | With Skill |
|----------|-------------------|------------|
| aggregation-before-raw-fetch | RED (defaults to raw fetch) | PASS (suggests count_over_time first) |
| discovery-before-querying | RED (queries blindly) | PASS (discovers labels first) |
| subagent-orchestrator-pattern | RED (no mention of subagents) | PASS (uses Task/subagent pattern) |
| percentiles-for-latency | not RED (model sometimes knows) | PASS (uses P95/P99/histogram_quantile) |
| jq-extraction | RED (returns raw output) | PASS (uses jq for extraction) |
| two-phase-investigation | RED (no phased approach) | PASS (discovery → investigation phases) |
| parallel-independent-queries | RED (sequential approach) | PASS (parallel/concurrent queries) |
| chart-for-trends | RED (generic visualization) | PASS (suggests lgtm chart) |

The `percentiles-for-latency` baseline was "not RED" — Sonnet already knows to suggest percentiles for latency without the skill. The skill still passes (reinforces the behavior), but this scenario is less valuable as a regression test since the model has this knowledge baked in.

### Scenario tests: 5/5 comparison tests passed

Comparison tests (with-skill vs without-skill) ran against real Claude conversations. Each test runs Claude twice with 8-12 max turns. Total runtime: ~33 minutes.

| Scenario | Result |
|----------|--------|
| investigate-error-spike | PASSED |
| service-health-check | PASSED |
| trace-slow-requests | PASSED |
| metrics-trend-with-chart | PASSED |
| cross-signal-investigation | PASSED |

### Lesson: skill-only absolute scoring doesn't work well

We initially had a second test class (`test_scenario_with_skill_only`) that ran Claude with the skill and checked `score >= 0.6`. All 5 failed.

The problem: each test runs a fresh Claude conversation, and Claude doesn't always activate the `Skill` tool — sometimes it just calls `Bash` directly to run `lgtm` commands. That's valid behavior, but our scoring expected `Task` as a required tool (30% weight). Without `Task`, the max possible score is 0.70, and with partial pattern matches it drops below 0.60.

The comparison test avoids this by measuring the *delta* between with-skill and without-skill runs. Both runs might score low in absolute terms, but the skill consistently doesn't make things worse (delta >= -0.1). This is the more meaningful question: "does the skill help?" rather than "does Claude do a good job in absolute terms?"

We removed the skill-only test class — comparison is the signal that matters.

## Design decisions

**Deterministic evaluation, no LLM-as-judge.** All scoring is regex pattern matching. This makes results reproducible and auditable. The trade-off is that patterns need careful tuning — too strict and you get false failures from LLM variance, too loose and you miss real regressions.

**Skill-pressure tests are the inner loop.** They run in minutes and catch most skill text issues. Scenario tests are the outer loop — they catch integration issues (skill activation, tool orchestration) but are slow and expensive.

**The baseline matters.** Skill-pressure tests explicitly verify the model does the "wrong" thing without the skill (RED baseline). Without this, a passing test might just mean the model already knows the right answer, and your skill text is dead weight.

## What to add next

- **HTML report generation** — Honeycomb generates interactive HTML reports with side-by-side timelines and scoring breakdowns. Currently we just have JSON output.
- **Canary tests** — fast, plugin-only verification that the skill actually activates before running full comparisons.
- **CI integration** — run skill-pressure tests on every commit, scenario tests on PRs.
