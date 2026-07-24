---
title: "Telemetry Query CLI for AI Agents: gcx vs a Custom CLI"
date: 2026-07-24T16:00:00+0800
tags: [cli, llm, agents, experiments, observability]
---

This experiment compares two command-line tools that query telemetry data. The first tool is [`gcx`](https://github.com/grafana/gcx), the official Grafana CLI. The second tool is [`lgtm`](https://github.com/pokgak/lgtm-cli), a custom CLI. An AI agent uses each tool to investigate incidents on a GPU compute cluster. The agent reads metrics, logs, and traces from a Grafana Cloud stack. This experiment measures which tool serves the agent better.

This experiment follows the [AXI Principles Experiment](/experiments/axi-principles-lgtm-cli-experiments/), which added structured output to the custom CLI. Here a stronger reference is available: the official Grafana CLI.

## The Question

When an AI agent drives a telemetry query CLI, which design properties reduce token cost and errors? Does the official `gcx` do better than the custom `lgtm`?

## Setup

- **Tools:** `gcx` v0.5.0 (official, public preview) and `lgtm` v1.5.0 (custom, Python).
- **Backends:** Prometheus, Loki, and Tempo on a Grafana Cloud stack.
- **Time window:** one fixed window in the past. The data does not change. Both tools read the same data.
- **Ground truth:** a direct HTTPS call to each backend API with the same token. This call is the reference. It is not either CLI. It decides which tool is correct.
- **Token counts:** measured on stdout with the `tiktoken` `cl100k_base` encoder. Tokens are the true cost for an agent, not bytes.
- **Two tracks:** Track A is a scripted harness. It measures tokens, latency, exit codes, and correctness. Track B is an agent-in-the-loop test. An isolated agent uses one CLI to solve a task in plain language.

The score uses eight weighted dimensions. Correctness and token cost have the largest weights, because they decide whether an agent investigation succeeds.

| Dimension | Weight |
|---|---|
| D1 Correctness / parity | 0.25 |
| D2 Token efficiency | 0.20 |
| D3 Error-message quality | 0.15 |
| D4 Discovery workflow | 0.15 |
| D5 Invocation ergonomics | 0.10 |
| D6 Authentication friction | 0.07 |
| D7 Latency | 0.05 |
| D8 Capability breadth | 0.03 |

---

## Experiment 1: Output token cost

### **Why this matters**

The agent pays for every output token. Small output costs less. Small output also fills the context window more slowly. This lets the agent do more work before it runs out of space.

### **Hypothesis**

Compact JSON costs fewer tokens than indented JSON. `gcx` prints compact output. The custom `lgtm` prints indented output. The prediction is that `gcx` uses 20% to 40% fewer tokens for the same query.

### **Method**

Run six normal queries with each tool. Use the same query text and the same time window for both tools. Count the tokens on stdout.

### **Results**

| Query | lgtm tokens | gcx tokens | Reduction |
|---|---|---|---|
| Instant vector (one node) | 1,167 | 807 | 31% |
| Range, 8 nodes, 5-minute step | 6,252 | 3,602 | 42% |
| Top-K aggregation | 744 | 523 | 30% |
| Counter-rate, top 10 | 911 | 575 | 37% |
| Empty result | 29 | 16 | 45% |
| Log lines, 50 entries | 7,841 | 3,301 | 58% |

### **What this tells us**

The hypothesis is correct. The two tools return the same data. Only the format differs. `gcx` prints one compact JSON line. `lgtm` prints indented JSON. `gcx` also sends its hint text to stderr, so the hint does not add to the stdout tokens. A default of compact JSON is a simple change that saves tokens on every query.

---

## Experiment 2: The large-result problem

### **Why this matters**

A broad query can return a very large result. A large result can fill the whole context window in one call. This can stop the agent. A safe CLI must protect the agent from this.

### **Hypothesis**

Both tools print the full result on stdout. The prediction is that both tools return a very large token count for a broad query.

### **Method**

Query all GPU temperatures over six hours at a one-minute step. This returns hundreds of time series. Count the tokens on stdout for each tool.

### **Results**

| Tool | stdout tokens | Behavior |
|---|---|---|
| lgtm | 2,966,503 | Prints the full result |
| gcx | 128 | Writes a file, prints a pointer |

### **What this tells us**

The hypothesis is wrong for `gcx`. `gcx` measures the response size first. If the response is too large, `gcx` writes the full result to a temporary file. `gcx` then prints a short message with the file path and an option to force inline output. The custom `lgtm` has no size guard. It prints the full result. The `lgtm` output is large enough to stop an agent in one call. This is the most important safety difference in the experiment. A size guard is more valuable than any token saving in Experiment 1.

---

## Experiment 3: Error messages and self-correction

### **Why this matters**

An agent must recover from a bad query without help from a human. The error message is the only signal the agent has. A clear message lets the agent fix the query. A poor message wastes turns.

### **Hypothesis**

A structured error with a cause and a suggestion helps the agent recover. `gcx` returns structured errors. The prediction is that `gcx` gives a clear, actionable message, and the custom `lgtm` does not.

### **Method**

Send a malformed query with a missing bracket. Send a query to a target that the tool cannot reach. Record stdout, stderr, and the exit code for each tool.

### **Results**

| Behavior | lgtm | gcx |
|---|---|---|
| Error on stdout | Empty | Structured JSON |
| Names the cause | No | Yes (parse position) |
| Gives a suggestion | No | Yes |
| Exit code | Always 1 | Distinct per error type |
| Extra noise | Repeated warning lines | None |

### **What this tells us**

The hypothesis is correct. `gcx` prints a JSON error on stdout. The error names the exact parse position. The error gives a next step. The exit code shows the error type. The custom `lgtm` prints nothing on stdout for a failed query. The real cause is hidden under repeated warning lines on stderr. These warnings come from unset environment variables for backends that the query does not use. The agent gets almost no useful signal. Two rules follow: print the error where the agent reads it, and never let noise hide the cause.

---

## Experiment 4: Result correctness (parity)

### **Why this matters**

A fast, cheap answer has no value if it is wrong. The result must match the backend exactly. This dimension has the largest weight for that reason.

### **Hypothesis**

Both tools return the same data as the backend. The prediction is an exact match from both tools on every query.

### **Method**

Run eight query types with each tool. Compare each result to the direct HTTPS call to the backend API. Check the series count and the values.

### **Results**

| Tool | Exact matches | Notes |
|---|---|---|
| lgtm | 8 of 8 | Matches the backend on every query |
| gcx | 6 of 8 | Two differences (see below) |

The two `gcx` differences:

1. On the large range query, `gcx` returned 744 of 768 series. This is a silent shortfall of about 3%.
2. `gcx` has no instant query mode for logs. A point-in-time log count returned a range result instead of a single snapshot.

### **What this tells us**

The hypothesis is wrong for `gcx`. `gcx` sends its queries through the Grafana proxy. The proxy applies a series cap and a data-point cap. The custom `lgtm` calls the backend API directly, so it returns every series. This is the one dimension where the custom tool is clearly better. Correctness has the highest weight, so this result matters. A tool that is easy for an agent must still return complete and correct data.

---

## Experiment 5: Agent-in-the-loop, and why one run lies

### **Why this matters**

A scripted test measures the tool. It does not measure how an agent uses the tool. An agent test shows real behavior: how many calls the agent makes, and whether it reaches the correct answer.

### **Hypothesis**

The tool with easier commands needs fewer tool calls. The custom `lgtm` uses short instance names and has a direct instant mode. The prediction is that the custom tool needs fewer calls.

### **Method**

Give an isolated agent one CLI and a task in plain language. Use three tasks: find the hottest GPU, find the pod with the most error logs, and fix a broken query. Judge each answer against the ground truth. First run each task one time. Then run each task three times to reduce noise.

### **Results**

| Measure | One run (n=1) | Three runs (n=3) |
|---|---|---|
| Call-count winner | Custom `lgtm` looked leaner | A tie; result depends on the task |
| Correctness (gcx) | 3 of 3 | 9 of 9 |
| Correctness (lgtm) | 3 of 3 | 8 of 9 |
| Mean calls per task | — | gcx 2.22, lgtm 1.89 |

### **What this tells us**

The hypothesis is not supported after the repeats. The single-run result was noise. The call-count advantage did not hold across three runs. The clear signal was correctness. `gcx` answered correctly every time. The custom `lgtm` made one mistake: it picked the wrong pod on the log task, because some log streams have no pod label. The lesson is general: do not trust a single agent run. Repeat each task, then compare.

---

## Final Summary

The official `gcx` wins overall. It is much cheaper in tokens, and its errors help the agent recover. The custom `lgtm` wins on correctness and on unattended authentication.

| Dimension | Weight | lgtm | gcx |
|---|---|---|---|
| D1 Correctness / parity | 0.25 | **1.00** | 0.88 |
| D2 Token efficiency | 0.20 | 0.45 | **1.00** |
| D3 Error-message quality | 0.15 | 0.35 | **0.95** |
| D4 Discovery workflow | 0.15 | 0.80 | **0.85** |
| D5 Invocation ergonomics | 0.10 | **0.85** | 0.80 |
| D6 Authentication friction | 0.07 | **0.90** | 0.60 |
| D7 Latency | 0.05 | 1.00 | 1.00 |
| D8 Capability breadth | 0.03 | 0.50 | **1.00** |
| **Total** | **1.00** | **0.73** | **0.89** |

### Key findings

| Finding | Evidence |
|---|---|
| Compact output saves 30% to 58% of tokens | Experiment 1 |
| A size guard prevents a context crash | Experiment 2 (2.97M tokens vs 128) |
| Structured errors let the agent recover | Experiment 3 |
| A direct API call returns complete data | Experiment 4 (lgtm 8/8; gcx 6/8) |
| One agent run is not enough | Experiment 5 (n=1 result did not hold at n=3) |

### Design rules for an agent CLI

These rules apply to any command-line tool that an AI agent will drive:

1. Print compact JSON when the output is not a terminal. Keep indented output for a human.
2. Measure the response size. Write a large result to a file. Return a short pointer with the path.
3. Print structured errors on stdout. Give the cause and a suggestion. Use a distinct exit code for each error type.
4. Do not print repeated warnings. Never let noise hide the real error.
5. Keep results correct and complete. A proxy can drop data. A direct API call is safer.
6. Test with repeats, not one run. A single run gives a noisy signal.

### Next steps

The custom tool can adopt the first four `gcx` behaviors while it keeps its correctness advantage. These are output-layer changes, not query-layer changes, so they do not touch the direct API path that wins Experiment 4. A re-run of this harness after the changes will show whether the custom tool reaches parity with `gcx`.
