---
title: "MLX Inference Throughput Gap: Where Do the Missing Tokens/sec Go?"
date: 2026-04-07T00:00:00+0800
tags: [mlx, apple-silicon, inference, benchmarking, performance, m3-ultra]
---

Investigating why LLM inference on Apple Silicon achieves only 62-81% of the bandwidth-limited theoretical maximum. Running on an M3 Ultra Mac Studio (819 GB/s memory bandwidth) with 4-bit quantized models via mlx-lm.

Code: [pokgak/mlx-bench](https://github.com/pokgak/mlx-bench) (`experiments/` directory)

## The Question

A 4-bit Mistral-7B model has ~4.5 GB of weights. At 819 GB/s, the M3 Ultra should load those weights in ~5.5ms, giving ~182 tokens/sec. We measured ~110-120 tok/s. Where does the ~35% overhead come from?

## Hardware

- **Machine:** Mac Studio (2025)
- **Chip:** M3 Ultra
- **Memory:** Unified, 819 GB/s theoretical bandwidth
- **Framework:** mlx-lm 0.31.1, MLX 0.31.1

## Experiment 1: Raw Memory Bandwidth Baseline

**Goal:** Establish what bandwidth the M3 Ultra actually delivers for ML-relevant workloads.

| Operation | Bandwidth | % of Theoretical |
|-----------|-----------|-----------------|
| Array copy (2 GB float32) | 669 GB/s | 82% |
| MatVec (8192×8192 float32) | 464 GB/s | 57% |
| Quantized MatVec (8192×8192, 4-bit) | 179 GB/s | 22% |

**Takeaway:** Even the simplest operation (array copy) only hits 82% of spec. Quantized matmuls are much lower because they involve compute (dequantization) on top of data movement. The "819 GB/s" is a ceiling we'll never reach in practice.

## Experiment 2: mx.eval() Sync Overhead

**Goal:** MLX uses lazy evaluation — operations are queued and only execute when you call `mx.eval()`. How much does eval granularity matter?

Simulated a 7B model's weight loading (4-bit quantized matmuls for all layers) with different eval strategies:

| Strategy | Time/token | Tok/s | Evals/token |
|----------|-----------|-------|-------------|
| eval every matmul | 53.8 ms | 18.6 | 224 |
| eval per layer | 13.9 ms | 71.8 | 32 |
| eval once (all batched) | 6.5 ms | 153.5 | 1 |

**Takeaway:** Eval granularity is the single largest factor we can control. Each eval call is only 0.2µs of pure sync, but it creates a barrier that prevents MLX from fusing operations across boundaries. The "eval once" result (153 tok/s, 670 GB/s effective) matches the raw array copy bandwidth — confirming that the matmuls themselves aren't the bottleneck when properly fused.

The real model can't use "eval once" because layers have sequential dependencies (layer N's output feeds layer N+1), but it does much better than "eval every op" because MLX fuses operations within each eval boundary.

## Experiment 3: Real Model Component Breakdown

**Goal:** How fast is the actual model, and what do individual ops cost?

**Actual Mistral-7B-4bit decode:** 8.37 ms/token (119.5 tok/s)

Isolated operation costs (each measured with its own eval — inflated by sync overhead):

| Component | Per-layer | All 32 layers | % of isolated total |
|-----------|-----------|---------------|-------------------|
| Attention projections (Q/K/V/O) | 866 µs | 27.72 ms | 42.7% |
| MLP projections (gate/up/down) | 762 µs | 24.38 ms | 37.6% |
| RMSNorm (×2) | 399 µs | 12.76 ms | 19.7% |

**Isolated sum: 64.86 ms** vs **actual: 8.37 ms** — a 7.8× difference.

**Takeaway:** Isolated measurements are useless for absolute timing because each carries ~200µs of eval overhead. But the relative proportions are meaningful: attention and MLP projections dominate (~80%), with norms being surprisingly expensive in isolation.

The 7.8× gap between isolated and actual confirms that MLX's operation fusion is doing heavy lifting — it hides most compute costs behind memory transfers.

## Experiment 4: KV Cache Scaling

**Goal:** How much does throughput degrade as the context (and KV cache) grows?

| Context Length | Tok/s | Δ from baseline | Peak Memory |
|---------------|-------|-----------------|-------------|
| 67 | 119.2 | — | 3.86 GB |
| 163 | 120.7 | +1.3% | 4.02 GB |
| 547 | 109.1 | -8.5% | 4.32 GB |
| 1059 | 116.5 | -2.3% | 4.47 GB |
| 2083 | 111.4 | -6.5% | 4.54 GB |
| 4131 | 113.7 | -4.6% | 4.82 GB |

**Takeaway:** Remarkably flat on the M3 Ultra. Even at 4K context, throughput only drops ~5%. The 819 GB/s bandwidth has enough headroom to absorb the growing KV cache reads (1.07 GB at 4096 context). Memory usage scales linearly as expected (+0.25 MB per token per layer).

## Experiment 5: SDPA & Compute Op Costs

**Goal:** How much do individual compute operations cost, and does fused SDPA help?

### Fused vs Manual SDPA

| Context Length | Fused | Manual | Speedup |
|---------------|-------|--------|---------|
| 64 | 238 µs | 271 µs | 1.1× |
| 256 | 253 µs | 284 µs | 1.1× |
| 1024 | 219 µs | 235 µs | 1.1× |
| 4096 | 260 µs | 420 µs | 1.6× |

### Quantized matmul vs dequant+matmul

| Layer | quantized_matmul | dequant+matmul | Speedup |
|-------|-----------------|----------------|---------|
| Q/K/V proj (4096→4096) | 205 µs | 385 µs | 1.9× |
| MLP gate (4096→14336) | 231 µs | 908 µs | 3.9× |
| MLP down (14336→4096) | 233 µs | 900 µs | 3.9× |

**Takeaway:** `quantized_matmul` is the critical optimization — 2-4× faster than dequantize-then-multiply. Fused SDPA gives modest gains at short contexts but matters more at 4K+ where manual attention's memory traffic grows. These operations are well-optimized in mlx-lm; there's not much low-hanging fruit here.

## Experiment 6: Complete Bandwidth Accounting

**Goal:** Our initial "40-47% efficiency" only counted weight bytes. What happens when we account for ALL data movement?

Per-token data movement breakdown:

| Data | Bytes (256 ctx) | Bytes (4096 ctx) |
|------|----------------|-----------------|
| Model weights (4-bit) | 4.45 GB | 4.45 GB |
| KV cache reads | 67.1 MB | 1,073.7 MB |
| KV cache writes | 0.3 MB | 0.3 MB |
| **Total** | **4.51 GB** | **5.52 GB** |

Actual vs bandwidth-limited theoretical:

| Context | Actual | BW-limited max | Efficiency | Effective BW |
|---------|--------|----------------|------------|-------------|
| 64 | 119 tok/s | 184 tok/s | **65%** | 533 GB/s |
| 256 | 112 tok/s | 182 tok/s | **62%** | 505 GB/s |
| 1024 | 120 tok/s | 174 tok/s | **69%** | 566 GB/s |
| 4096 | 120 tok/s | 148 tok/s | **81%** | 660 GB/s |

**Takeaway:** Corrected efficiency is **62-81%**, not 40-47%. The original estimate was misleading because it ignored KV cache data movement. Efficiency *improves* at longer contexts because KV cache reads overlap well with weight loading — the hardware's memory subsystem can service both streams concurrently.

## Running Summary

The ~35% overhead (at short context) breaks down to:

| Source | Contribution | Evidence |
|--------|-------------|----------|
| Hardware bandwidth ceiling | ~18% | Raw array copy only reaches 82% of spec (669/819 GB/s) |
| Compute that can't hide behind transfers | ~10-20% | SDPA, RoPE, softmax, norms, activations — varies with context length |
| KV cache pressure | ~2-5% | Minimal on M3 Ultra due to high bandwidth headroom |

At longer contexts (4096+), efficiency climbs to 81% because the KV cache reads overlap better with weight loading, effectively amortizing the compute overhead.

**Bottom line:** mlx-lm on the M3 Ultra is well-optimized. The remaining gap is mostly physics (memory subsystem overhead) plus unavoidable compute that can't fully overlap with data movement.
