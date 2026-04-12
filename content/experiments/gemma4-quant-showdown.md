---
title: "Gemma 4 Quant Showdown: All Sizes, Every Format"
date: 2026-04-12T00:00:00+0800
tags: [mlx, apple-silicon, inference, benchmarking, gemma, quantization, m3-ultra]
---

How do all of Gemma 4's quantization formats compare across all four model sizes on Apple Silicon? Running 33 variants — every instruction-tuned quant in the mlx-community namespace — on a single M3 Ultra.

Code: [pokgak/mlx-bench](https://github.com/pokgak/mlx-bench)

## The Question

Gemma 4 ships with an unusually wide range of quantization options: standard integer quants (4–8bit, bf16), MX-spec formats (mxfp4, mxfp8), NVIDIA-style FP4 (nvfp4), and calibration-optimized OptiQ. Across four model sizes — two small MoE models (e2b, e4b), a large sparse MoE (26b-a4b), and a dense 31b — does the format choice matter? And does the architecture change which format wins?

## Hardware & Setup

- **Machine:** Mac Studio (2025)
- **Chip:** Apple M3 Ultra
- **Memory:** 512 GB unified, 819 GB/s theoretical bandwidth
- **Framework:** mlx-lm 0.31.3 (git HEAD), MLX 0.31.1
- **Benchmark:** 3 prompt lengths (128 / 512 / 1024 tokens), 256 generation tokens, 1 warmup + 3 runs, median reported
- **Metric:** tokens/sec (generation), TTFT (ms), peak memory (GB)

---

## Model Families

Each Gemma 4 size targets a different point on the speed/quality curve:

| Family | Architecture | Active params | What it's for |
|---|---|---|---|
| `e2b` | MoE | ~2B | Max speed, edge deployment |
| `e4b` | MoE | ~4B | Speed + slightly more capability |
| `26b-a4b` | MoE | ~4B active / 26B total | Best quality-per-compute — large knowledge, cheap inference |
| `31b` | Dense | 31B | Raw quality, all params active every token |

## Quantization Formats

| Format | Goal | Trade-off |
|---|---|---|
| `4bit` | Speed + memory efficiency | Aggressive compression, some quality loss |
| `5bit` | Speed/quality balance | Rarely the sweet spot |
| `6bit` | Quality-leaning balance | Often best tok/s per quality point |
| `8bit` | Near-lossless compression | ~same quality as bf16, half the memory |
| `bf16` | Reference quality (training dtype) | Slowest, largest — the baseline |
| `mxfp4` | Hardware-aligned 4-bit (MX spec) | Block-level FP4 scaling; targets future accelerators |
| `mxfp8` | Hardware-aligned 8-bit (MX spec) | Better than INT8 for non-uniform distributions |
| `nvfp4` | NVIDIA Blackwell FP4 format | Different encoding from mxfp4, same idea |
| `OptiQ-4bit` | Calibration-optimized 4bit | Minimizes quant error via sample data; trades speed for quality-at-4bit |

---

## Results

### gemma-4-e2b (MoE, ~2B active)

| Quant | tok/s (128→1024 tok prompt) | Peak mem | Notes |
|---|---|---|---|
| 4bit | 134–140 | 2.6–3.2 GB | Fastest in entire benchmark |
| 5bit | 125–130 | 3.1–3.7 GB | |
| mxfp4 | 115–119 | 3.2–3.7 GB | Same speed as 6bit, hardware-aligned |
| 6bit | 115–119 | 3.6–4.2 GB | |
| mxfp8 | 106–110 | 4.6–5.1 GB | Tracks 8bit closely |
| 8bit | 108–112 | 4.7–5.3 GB | |
| bf16 | 79–81 | 8.8–9.1 GB | 43% slower than 4bit |
| nvfp4 | — | — | Failed: model files missing on HF |

### gemma-4-e4b (MoE, ~4B active)

| Quant | tok/s | Peak mem | Notes |
|---|---|---|---|
| 4bit | 94–100 | 4.1–4.6 GB | |
| OptiQ-4bit | 86–92 | 6.0–6.5 GB | Slower *and* heavier than plain 4bit |
| 5bit | 86–90 | 5.0–5.5 GB | |
| 6bit | 78–81 | 5.8–6.3 GB | |
| mxfp4 | 76–79 | 5.5–6.0 GB | |
| nvfp4 | 76–79 | 5.6–6.0 GB | Nearly identical to mxfp4 |
| mxfp8 | 70–73 | 7.3–7.8 GB | |
| 8bit | 71–74 | 7.5–8.0 GB | |
| bf16 | 48–50 | 14.1–14.4 GB | 2× slower than 4bit |

### gemma-4-26b-a4b (MoE, 26B total / ~4B active)

| Quant | tok/s | Peak mem | Notes |
|---|---|---|---|
| 4bit | 92–97 | 13.6–14.0 GB | Matches e4b-4bit speed — MoE efficiency |
| 5bit | 84–88 | 16.4–16.8 GB | |
| 6bit | 79–83 | 19.3–19.7 GB | |
| 8bit | 74–77 | 25.0–25.4 GB | |
| bf16 | 57–59 | 47.1–47.4 GB | 38% slower than 4bit at 3.5× the memory |
| mxfp4 | 92–97 | 12.8–13.3 GB | Ties 4bit speed, saves ~1 GB — best mxfp4 result in benchmark |
| mxfp8 | 73–76 | 24.3–24.7 GB | Tracks 8bit, saves ~0.7 GB |
| nvfp4 | 89–94 | 13.6–13.9 GB | Slightly behind mxfp4 at same memory |

### gemma-4-31b (Dense, 31B)

| Quant | tok/s | Peak mem | Notes |
|---|---|---|---|
| mxfp4 | 28–31 | 15.3–15.8 GB | Beats 4bit speed, saves ~1 GB — consistent mxfp4 win on larger models |
| 4bit | 27–30 | 16.2–16.7 GB | Dense tax: 3× slower than 26b-a4b-4bit |
| 5bit | 23–25 | 19.8–20.2 GB | |
| 6bit | 21–22 | 23.3–23.8 GB | |
| mxfp8 | 17–18 | 29.6–30.0 GB | Matches 8bit speed, saves ~0.8 GB |
| 8bit | 17–18 | 30.5–30.9 GB | Slower than e4b-bf16 — dense tax at full scale |
| nvfp4 | 27–30 | 16.2–16.6 GB | Matches 4bit speed at same memory — no advantage |
| bf16 | 9.8–10.2 | 57.2–57.5 GB | Slowest in the entire benchmark — 14× slower than e2b-4bit |

---

## Cross-Family Comparison

Best tok/s per family at the fastest and most memory-efficient configurations:

| Family | Best format | tok/s | Peak mem | Runner-up |
|---|---|---|---|---|
| e2b | `4bit` | 134–140 | 2.6–3.2 GB | `mxfp4` at 115–119 tok/s, same mem |
| e4b | `4bit` | 94–100 | 4.1–4.6 GB | `5bit` at 86–90 tok/s |
| 26b-a4b | `mxfp4` | 92–97 | 12.8–13.3 GB | `4bit` tied at 92–96 tok/s, +0.8 GB |
| 31b | `mxfp4` | 28–31 | 15.3–15.8 GB | `4bit` at 27–30 tok/s, +1 GB |

The 26b-a4b MoE model matches e4b on speed (92–97 vs 94–100 tok/s) while packing 26B parameters — you get dramatically more model capacity at essentially the same inference cost. That's the best performance-per-compute in the whole benchmark.

---

## Observations

**MoE speed is real.** `26b-a4b-it-4bit` hits 92–97 tok/s — nearly matching `e4b-it-4bit` (94–100 tok/s). You get 26B parameters of knowledge for roughly the same inference cost as a 4B dense model. That's the MoE promise delivered.

**mxfp4 wins on larger models.** For e2b it's roughly equivalent to 6bit (115–119 tok/s each). But on 26b-a4b and 31b, mxfp4 pulls ahead: it ties or beats 4bit on speed while using ~1 GB less memory. The compression efficiency of block-scaled FP4 pays off as model size grows.

**nvfp4 ≈ mxfp4 on 26b-a4b, falls behind on 31b.** At 26b-a4b they're essentially tied (92–97 vs 89–94 tok/s). On 31b, nvfp4 (27–30 tok/s) trails mxfp4 (28–31 tok/s) at the same memory footprint. Neither format has hardware acceleration on Apple Silicon — the difference is purely in encoding efficiency.

**OptiQ-4bit is not worth it here.** On e4b it's slower (86–92 vs 94–100 tok/s) *and* uses 50% more memory (6.0 GB vs 4.1 GB) compared to plain 4bit. The calibration-based quality improvement may matter on evals, but the speed and memory cost is steep.

**bf16 penalty scales with model size.** e2b-bf16 is 43% slower than e2b-4bit. e4b-bf16 is 51% slower. 26b-a4b-bf16 is 38% slower at 3.5× the memory. 31b-bf16 bottoms out at 9.8–10.2 tok/s — 14× slower than e2b-4bit, the widest gap in the entire benchmark.

**TTFT is almost flat across quants.** All e2b variants show ~32ms TTFT regardless of quantization. Prefill is fast enough that the quant format barely touches it — the difference is entirely in decode throughput.

**The dense tax is brutal.** `31b-it-4bit` hits only 27–30 tok/s at 16.2 GB — roughly **3× slower** than `26b-a4b-it-4bit` (92–97 tok/s, 13.6 GB) despite similar total parameter counts. Every weight in the 31b gets loaded every token; the 26b-a4b routes each token through only ~4B active params out of 26B. At every memory budget, the MoE variants win on throughput.

---

## Failures

| Model | Error |
|---|---|
| `gemma-4-e2b-it-nvfp4` | `FileNotFoundError` — model files not yet available on HuggingFace |

