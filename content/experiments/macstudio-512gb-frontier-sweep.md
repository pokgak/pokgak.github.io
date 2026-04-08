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
| Ultra-large | `mlx-community/MiniMax-M2-5bit` | MiniMax | 5-bit | Recent frontier-scale replacement after Kimi staging issues |

During the sweep I also attempted `mlx-community/Kimi-K2.5`, but on this setup it repeatedly stalled during staging/fetch without reaching a usable benchmark run. I replaced it with `MiniMax-M2-5bit` for the final frontier slot. That is itself a useful result: the practical local frontier is constrained not just by memory fit, but also by real compatibility and staging behavior.

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

The sweep is mostly complete at time of writing: 8 of the 9 selected models have finished. `MiniMax-M2-5bit` is currently running as the last replacement model after `Kimi-K2.5` repeatedly stalled during staging, so the table below should be read as a near-final snapshot rather than the very last word.

| Model | Prompt tokens | Generated | Prefill (s) | Decode (s) | TTFT (s) | Tokens/s | Peak Mem (GB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | 72 | 256 | 0.035 | 1.600 | 0.036 | 156.5 | 1.85 |
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | 225 | 256 | 0.079 | 1.514 | 0.079 | 160.6 | 2.11 |
| `mlx-community/Llama-3.2-3B-Instruct-4bit` | 396 | 256 | 0.124 | 1.521 | 0.125 | 155.6 | 2.28 |
| `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` | 71 | 256 | 0.071 | 2.417 | 0.072 | 102.9 | 4.35 |
| `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` | 224 | 256 | 0.153 | 2.426 | 0.154 | 99.2 | 4.53 |
| `mlx-community/Meta-Llama-3.1-8B-Instruct-4bit` | 395 | 256 | 0.272 | 2.432 | 0.273 | 94.7 | 4.75 |
| `mlx-community/Qwen3.5-9B-OptiQ-4bit` | 46 | 256 | 0.071 | 3.397 | 0.071 | 73.8 | 5.77 |
| `mlx-community/Qwen3.5-9B-OptiQ-4bit` | 199 | 256 | 0.188 | 3.327 | 0.188 | 72.8 | 6.07 |
| `mlx-community/Qwen3.5-9B-OptiQ-4bit` | 372 | 256 | 0.306 | 3.337 | 0.307 | 70.3 | 6.27 |
| `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit` | 65 | 256 | 0.134 | 4.258 | 0.134 | 58.3 | 7.86 |
| `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit` | 218 | 256 | 0.286 | 4.272 | 0.286 | 56.2 | 8.08 |
| `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit` | 391 | 256 | 0.511 | 4.271 | 0.512 | 53.5 | 8.22 |
| `mlx-community/gpt-oss-20b-MXFP4-Q8` | 103 | 256 | 0.089 | 2.673 | 0.090 | 92.7 | 11.41 |
| `mlx-community/gpt-oss-20b-MXFP4-Q8` | 255 | 256 | 0.144 | 2.641 | 0.145 | 91.9 | 11.55 |
| `mlx-community/gpt-oss-20b-MXFP4-Q8` | 422 | 256 | 0.204 | 2.652 | 0.204 | 89.6 | 11.75 |
| `mlx-community/Qwen3-30B-A3B-4bit` | 44 | 256 | 0.060 | 3.668 | 0.061 | 68.7 | 16.06 |
| `mlx-community/Qwen3-30B-A3B-4bit` | 197 | 256 | 0.127 | 3.705 | 0.127 | 66.8 | 16.26 |
| `mlx-community/Qwen3-30B-A3B-4bit` | 370 | 256 | 0.200 | 3.679 | 0.200 | 66.0 | 16.42 |
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | 72 | 256 | 0.601 | 16.986 | 0.602 | 14.6 | 37.06 |
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | 225 | 256 | 1.510 | 17.664 | 1.510 | 13.3 | 37.27 |
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | 396 | 256 | 2.415 | 17.806 | 2.415 | 12.7 | 37.35 |
| `mlx-community/gpt-oss-120b-MXFP4-Q8` | 103 | 256 | 1.788 | 509.252 | 1.790 | 0.5 | 59.16 |
| `mlx-community/gpt-oss-120b-MXFP4-Q8` | 255 | 256 | 1.829 | 507.443 | 1.830 | 0.5 | 59.34 |
| `mlx-community/gpt-oss-120b-MXFP4-Q8` | 422 | 256 | 1.819 | 511.312 | 1.820 | 0.5 | 59.54 |
| `mlx-community/MiniMax-M2-5bit` | pending | pending | pending | pending | pending | pending | pending |

**What this tells us:** The results separate into clear operating bands.

- `Llama-3.2-3B` is the speed ceiling on this machine at roughly 156-161 tok/s.
- `Meta-Llama-3.1-8B`, `gpt-oss-20b`, `Qwen3.5-9B`, and `Qwen2.5-Coder-14B` form the practical local-use tier.
- `Qwen3-30B-A3B` is especially interesting because it still delivers ~66-69 tok/s while staying under 17 GB peak memory.
- `Llama-3.3-70B` clearly fits and runs, but it enters a different latency regime.
- `gpt-oss-120b` is the strongest evidence that "fits" and "practical" are different frontiers: it completed, but at ~0.5 tok/s it is an experimentation result, not a daily-driver result.
- `Kimi-K2.5` never became a benchmark result at all on this setup, which is an important reminder that local usability includes staging reliability, not just theoretical fit.

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
| Interactive daily-use | `Llama-3.2-3B-Instruct-4bit`, `Meta-Llama-3.1-8B-Instruct-4bit`, `Qwen3.5-9B-OptiQ-4bit`, `Qwen2.5-Coder-14B-Instruct-4bit`, `gpt-oss-20b-MXFP4-Q8` | All stay in a sub-second to low-hundreds-of-milliseconds TTFT band and remain comfortably interactive at 56-158 tok/s. |
| Viable with patience | `Qwen3-30B-A3B-4bit`, `Llama-3.3-70B-Instruct-4bit` | They are still meaningfully usable, but the latency tradeoff becomes more obvious, especially for the 70B dense model. |
| Technically runnable | `gpt-oss-120b-MXFP4-Q8` | It fits and eventually completes, but ~0.5 tok/s decode throughput changes the usage pattern from "interactive model" to "machine capability demonstration." |

**What this tells us:** The practical frontier is well below the absolute fit frontier. The 512 GB machine absolutely expands what is possible locally, but the best day-to-day zone is still in the single-digit to low-tens-of-GB footprint range rather than at the extreme top end.

---

## Final Summary

The 512 GB M3 Ultra Mac Studio changes the local-model question from "can it run 70B?" to "how far up the frontier can you go before latency stops being worth it?" This experiment is measuring both the hard fit boundary and the softer usability boundary.

### Key Findings

| Question | Answer |
|---|---|
| Largest model that fit | `gpt-oss-120b-MXFP4-Q8` at ~59.5 GB peak memory, with `MiniMax-M2-5bit` still running |
| Fastest model tested | `Llama-3.2-3B-Instruct-4bit` at ~156-161 tok/s |
| Best practical daily-use tier | roughly 8B to 20B, especially `Meta-Llama-3.1-8B`, `Qwen3.5-9B`, `Qwen2.5-Coder-14B`, and `gpt-oss-20b` |
| Best large-model compromise | `Qwen3-30B-A3B-4bit`, because it keeps ~66-69 tok/s while staying under 17 GB peak memory |
| Most surprising result | `gpt-oss-120b` really does run locally on this machine, but its throughput is so low that it mostly proves a capability boundary, not a usability one |

### Follow-up Questions

1. How much do these rankings change with longer context windows?
2. How much of the large-model slowdown is TTFT vs steady-state decode?
3. Which of these models remain practical once quality is considered alongside speed?
4. Where does `MiniMax-M2-5bit` land on the fit-vs-usability curve once the sweep completes?
