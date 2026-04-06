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

## Experiment 7: Model Size Scaling

**Goal:** Does the efficiency pattern hold across model sizes, or is it specific to 7B?

**Hypothesis:** Smaller models should be *less* bandwidth-efficient because compute overhead is a larger fraction of total time when weight loading is faster.

| Model | Weights | Tok/s | BW-limited max | Efficiency | Effective BW |
|-------|---------|-------|----------------|------------|-------------|
| Qwen 0.8B | 0.60 GB | 238 | 1,370 | **17%** | 142 GB/s |
| Qwen 4B | 2.37 GB | 123 | 346 | **36%** | 291 GB/s |
| Mistral 7B | 4.08 GB | 114 | 198 | **58%** | 472 GB/s |
| Qwen 9B | 6.04 GB | 83 | 136 | **61%** | 503 GB/s |

**Hypothesis strongly confirmed.** The 0.8B model achieves only 17% bandwidth efficiency — weights load in 0.73ms but the decode step takes 4.21ms, meaning 83% of the time is spent on compute.

Prefill throughput also shows clear scaling: 0.8B does 7,412-10,274 tok/s vs 9B at 1,091-1,279 tok/s.

## Experiment 8: Actual Weight Sizes & Compute/Memory Crossover

**Goal:** Previous experiments used peak memory as a proxy for weight size (wrong — includes KV cache and activations). Get real numbers and find the crossover point.

Actual weight sizes measured from model parameters:

| Model | Actual Weights | Weight Load Time | Compute Overhead | Total |
|-------|---------------|-----------------|-----------------|-------|
| Qwen 0.8B | 0.598 GB | 0.73 ms | 3.48 ms | 4.21 ms |
| Qwen 4B | 2.367 GB | 2.89 ms | 5.24 ms | 8.13 ms |
| Mistral 7B | 4.077 GB | 4.98 ms | 3.81 ms | 8.79 ms |
| Qwen 9B | 6.043 GB | 7.38 ms | 4.64 ms | 12.02 ms |

**Key finding: compute overhead is roughly constant at 3.5-5.2ms regardless of model size.** This is the time spent on SDPA, RoPE, norms, activations, and other non-bandwidth-bound operations that can't fully overlap with weight loading.

For the 0.8B model, weight loading (0.73ms) finishes almost instantly, leaving 3.48ms of pure compute — the GPU sits idle waiting for compute to finish. For the 9B model, weight loading takes 7.38ms, giving compute 7+ ms to run concurrently — most of it hides behind the memory transfers.

**Crossover point:** Models need roughly **3-4 GB of weights** (at 819 GB/s bandwidth) for the decode step to become memory-bandwidth-bound rather than compute-bound. Below that, you're leaving bandwidth on the table.

**Implication for hardware choice:** On lower-bandwidth hardware (e.g., M5 Pro at 307 GB/s), the crossover point would be lower (~1-1.5 GB), meaning even small models would be more bandwidth-efficient. The M3 Ultra's massive bandwidth is actually "wasted" on small models.

## Experiment 9: Compute Breakdown via Ablation

**Goal:** What specifically makes up the ~3.5-5ms compute overhead? Previous isolated measurements were inflated by eval sync. This time we ablate (remove) one component at a time from the real model and measure the difference.

| Ablation | Decode time | Δ from baseline | % of decode |
|----------|-----------|-----------------|-------------|
| Baseline (full) | 8.94 ms | — | 100% |
| Remove RoPE | 8.75 ms | -0.19 ms | 2.1% |
| Remove RMSNorm | 8.01 ms | -0.93 ms | 10.4% |
| Remove MLP compute | 3.34 ms | -5.60 ms | 62.6% |
| Remove SDPA + KV cache | 1.92 ms | -7.02 ms | 78.5% |

The sum exceeds 100% because removing a component changes how MLX fuses remaining ops. But the ranking is clear:

1. **SDPA + KV cache** and **MLP compute** dominate — they're the big matrix multiplications
2. **RMSNorm** is ~10% — surprisingly significant for a "simple" operation
3. **RoPE** is negligible at 2%

Without MLP compute, the model runs in 3.34ms — that's essentially just attention projections + SDPA + norms + weight loading. Without SDPA+cache (but keeping Q/K/V/O projections), it drops to 1.92ms — close to the pure weight loading time.

## Experiment 10: Batch Decode & Roofline Model

**Goal:** Decode processes one token at a time. What happens with batching, and where does the M3 Ultra transition from memory-bound to compute-bound?

### Prefill throughput scaling

| Tokens | Time | Tok/s | ms/tok |
|--------|------|-------|--------|
| 1 | 8.17 ms | 122 | 8.171 |
| 4 | 11.97 ms | 334 | 2.993 |
| 32 | 33.84 ms | 946 | 1.057 |
| 128 | 86.21 ms | 1,485 | 0.673 |
| 1024 | 623.32 ms | 1,643 | 0.609 |

Processing 1024 tokens takes only 76x longer than processing 1 token — a **13x throughput improvement** (122 → 1,643 tok/s). The amortization of weight loading across tokens is massive.

### Batch decode (simulating speculative decoding verification)

| Batch size | Time | Tok/s | vs single |
|-----------|------|-------|-----------|
| 1 | 8.84 ms | 113 | 1.0x |
| 4 | 13.02 ms | 307 | 2.7x |
| 16 | 38.08 ms | 420 | 3.7x |
| 32 | 36.72 ms | 871 | 7.7x |
| 128 | 87.46 ms | 1,464 | 12.9x |

### Roofline analysis

The roofline model defines the **ridge point** — the arithmetic intensity where a workload transitions from memory-bound to compute-bound:

```
Ridge point = Peak FLOPS / Peak Bandwidth = 30 TFLOPS / 819 GB/s ≈ 36.6 FLOPs/byte
```

For single-token decode, the arithmetic intensity is:
```
AI = 2 × 7B params FLOPs / 4.1 GB weights = 3.43 FLOPs/byte
```

That's 10x below the ridge point — deeply memory-bound, as expected.

**At ~11 tokens per batch, we hit the ridge point.** Beyond that, compute saturates the GPU and adding more tokens doesn't amortize weight loading further — it just adds compute time linearly.

This is exactly why speculative decoding works: verifying 8 draft tokens barely costs more than generating 1 (3.1x time for 8x tokens), because the weight loading is amortized and we haven't hit the compute ceiling yet.
