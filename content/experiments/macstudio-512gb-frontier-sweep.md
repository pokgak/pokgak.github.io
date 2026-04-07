---
title: "What Can a 512 GB Mac Studio Run? MLX Frontier Model Sweep"
date: 2026-04-07T00:00:00+0800
tags: [mlx, apple-silicon, benchmarking, inference, mac-studio, m3-ultra, experiments]
---

Benchmarking a 512 GB M3 Ultra Mac Studio against a set of current frontier-scale MLX checkpoints to answer a practical question: not "what is most downloaded," but "what can this machine actually run locally, and how fast?" The runs use [`pokgak/mlx-bench`](https://github.com/pokgak/mlx-bench) on the Mac Studio itself with consistent prompt lengths and decode settings across models.

## The Question

If you buy a 512 GB Mac Studio to run local models, what is the real frontier you can reach today with MLX, and what performance do you get at each size tier?

## Hardware

- **Machine:** Mac Studio (2025)
- **Chip:** M3 Ultra
- **Memory:** 512 GB unified memory
- **Framework:** MLX / mlx-lm
- **Benchmark harness:** `pokgak/mlx-bench`

## Setup

- **Benchmark mode:** sequential model runs on the same machine
- **Prompt lengths:** 128, 512, 1024
- **Generation length:** 256 tokens
- **Warmup:** 1 run per model
- **Measured runs:** 3 runs per model, median selected

---

## Experiment 1: Candidate Selection

**Why this matters:** "Top 10 Hugging Face models" is not a meaningful benchmark set by itself. Download counts are polluted by tiny models, duplicates, test repos, and models that are technically available but not relevant to a 512 GB workstation. The population has to be defined before ranking anything inside it.

**Hypothesis:** A better benchmark set is "frontier MLX checkpoints that a 512 GB Mac Studio owner would plausibly try to run locally," not "highest-download text-generation repos."

**Method:** Start from current MLX-available text-generation checkpoints, then filter toward a diversified frontier set:

- small models that establish the speed ceiling
- mainstream 8B to 20B instruct/code models
- larger dense models
- large MoE models whose active footprint matters more than headline parameter count
- ultra-large checkpoints that may fit on 512 GB unified memory even if they are impractical on smaller machines

Exclude obvious duplicates, old superseded variants, tiny utility/testing models, and non-text-generation repos.

**Results:**

| Tier | Model | Family | Format | Why included |
|---|---|---|---|---|
| Small | `mlx-community/Llama-3.2-3B-Instruct-4bit` | Llama | 4-bit | Speed baseline |
| Mid | `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` | Llama | 4-bit | Mainstream local instruct model |
| Mid | `mlx-community/Qwen3.5-9B-OptiQ-4bit` | Qwen | 4-bit | Modern Qwen local baseline |
| Mid-large | `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit` | Qwen Coder | 4-bit | Code-focused checkpoint |
| Large | `mlx-community/gpt-oss-20b-MXFP4-Q8` | gpt-oss | MXFP4/Q8 | Open large-model baseline |
| Large MoE | `mlx-community/Qwen3-30B-A3B-4bit` | Qwen MoE | 4-bit | Active-parameter vs headline-size test |
| Very large dense | `mlx-community/Llama-3.3-70B-Instruct-4bit` | Llama | 4-bit | Dense frontier checkpoint |
| Ultra-large | `mlx-community/gpt-oss-120b-MXFP4-Q8` | gpt-oss | MXFP4/Q8 | 512 GB-only class |
| Ultra-large | `mlx-community/Kimi-K2.5` | Kimi | MLX | Frontier-scale checkpoint |

**What this tells us:** The benchmark set is intentionally shaped by machine-buying decisions, not by Hub popularity. That makes the results more useful to someone asking whether a 512 GB Mac Studio changes what is feasible locally.

---

## Experiment 2: Generation 0 Pilot

**Why this matters:** Before launching a multi-hour sweep, we need to verify that representative model families actually load and run under the current `mlx-lm` version and harness. Otherwise the "benchmark" is really a compatibility debugging session.

**Hypothesis:** Small, mid, and large representative models will all run cleanly through the same harness, but first-load cost will vary significantly depending on cache state and checkpoint size.

**Method:** Run a short pilot with one prompt length and short decode length on representative models from different families.

**Results:**

| Model | Prompt tokens | Generated | Tokens/s | Peak memory (GB) | Notes |
|---|---:|---:|---:|---:|---|
| `Llama-3.2-3B-Instruct-4bit` | 72 | 64 | 147.6 | 1.78 | Clean baseline |
| `Qwen3.5-9B-OptiQ-4bit` | 46 | 64 | 79.8 | 5.77 | Clean baseline |
| `gpt-oss-20b-MXFP4-Q8` | 103 | 64 | 67.9 | 11.42 | First uncached download was noticeable |
| `Qwen3-30B-A3B-4bit` | 44 | 32 | 52.7 | 16.06 | MoE working set stayed modest |

**What this tells us:** The harness is good enough to scale into a full sweep. More importantly, the pilot separates three different costs that are easy to conflate:

- **staging cost**: downloading/fetching model files
- **first-load cost**: loading and materializing model state
- **steady-state inference cost**: the actual throughput we care about

For a local workstation benchmark, only the third is the headline number, but the first two still matter for usability.

---

## Experiment 3: Full Sweep

**Why this matters:** A 512 GB unified-memory machine is interesting only if it expands the practical model frontier, not just because it can run the same 7B and 8B models faster.

**Hypothesis:** The Mac Studio will show three distinct regimes:

1. **Small models** are compute-limited and extremely fast.
2. **Mid and large models** are the practical sweet spot, with the best tradeoff between capability and latency.
3. **Ultra-large models** fit and run, but throughput and first-token latency become the real constraints.

**Method:** Run the selected models at prompt lengths 128, 512, and 1024 with 256 generated tokens, 1 warmup run, and 3 measured runs per model. Report the median run.

**Results:**

_To be filled from `mlx-bench` output once the sweep completes._

| Model | Prompt tokens | Generated | Prefill (s) | Decode (s) | TTFT (s) | Tokens/s | Peak Mem (GB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `Llama-3.2-3B-Instruct-4bit` | | | | | | | |
| `Meta-Llama-3.1-8B-Instruct-4bit` | | | | | | | |
| `Qwen3.5-9B-OptiQ-4bit` | | | | | | | |
| `Qwen2.5-Coder-14B-Instruct-4bit` | | | | | | | |
| `gpt-oss-20b-MXFP4-Q8` | | | | | | | |
| `Qwen3-30B-A3B-4bit` | | | | | | | |
| `Llama-3.3-70B-Instruct-4bit` | | | | | | | |
| `gpt-oss-120b-MXFP4-Q8` | | | | | | | |
| `Kimi-K2.5` | | | | | | | |

**What this tells us:** _To be filled after results land._

---

## Experiment 4: Usability Frontier

**Why this matters:** "Fits in memory" is a necessary condition, but not a sufficient one. A model that technically loads but has poor TTFT or single-digit decode throughput may be a valid engineering result while still being a questionable daily-driver choice.

**Hypothesis:** The machine's theoretical frontier and practical frontier will diverge. Some ultra-large checkpoints will be runnable, but the best daily-use zone will likely sit below the absolute maximum fit.

**Method:** Group results by real user experience:

- interactive daily-use
- viable but patience required
- technically runnable, mostly for experimentation

Use TTFT, decode tokens/sec, and peak memory as the main decision variables.

**Results:**

| Category | Candidate models | Why |
|---|---|---|
| Interactive daily-use | | |
| Viable with patience | | |
| Technically runnable | | |

**What this tells us:** _To be filled after final numbers are available._

---

## Final Summary

The 512 GB M3 Ultra Mac Studio changes the local-model question from "can it run 70B?" to "how far up the frontier can you go before latency stops being worth it?" This experiment is measuring both the hard fit boundary and the softer usability boundary.

### Key Findings

| Question | Answer |
|---|---|
| Largest model that fit | |
| Fastest model tested | |
| Best practical daily-use tier | |
| Best large-model compromise | |
| Most surprising result | |

### Follow-up Questions

1. How much do these rankings change with longer context windows?
2. How much of the large-model slowdown is TTFT vs steady-state decode?
3. Which of these models remain practical once quality is considered alongside speed?
