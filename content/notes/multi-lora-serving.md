---
title: "Multi-LoRA Serving: S-LoRA vs Cerebras"
date: 2026-05-07T00:00:00+0800
tags: [lora, inference, ml-infra, gpu, cerebras, vllm]
---

Notes on how LoRA adapters are served at scale, the tradeoffs involved, and how Cerebras's approach differs from vLLM's S-LoRA.

## What LoRA Is

LoRA (Low-Rank Adaptation) freezes base model weights and injects small trainable matrices alongside them:

```
Original:  output = W · x
With LoRA: output = W · x + (A·B) · x
```

Where A and B are low-rank matrices (e.g. rank 16 means A: 4096×16, B: 16×4096). This gives ~100× fewer trainable parameters than updating W directly. Training is fast and cheap; the adapter files are small (~30 MB for rank 16 on a 7B model).

The key serving property: **multiple adapters share one base model on the same GPU**. You don't need N GPU instances for N fine-tuned variants.

## S-LoRA (vLLM)

Paper: "S-LoRA: Serving Thousands of Concurrent LoRA Adapters" (Sheng et al., UC Berkeley 2023).

The problem S-LoRA solves: in a batch of requests, different requests may need different adapters. You can't naively batch them since each needs different ΔW applied.

**Three solutions:**

1. **Custom CUDA kernels for heterogeneous batching** — in a single forward pass, apply a different (A, B) pair per request. The kernel loops over adapter IDs in batch metadata, fetching the right matrices per sequence. GPU utilization is preserved.

2. **Unified paging** — extends vLLM's PagedAttention to also page adapter weights. Hot adapters (currently serving requests) stay in GPU HBM. Cold adapters live in CPU DRAM and are fetched over PCIe (~32 GB/s, ~1 ms per adapter). LRU eviction with prefetching during prior batch's compute.

3. **Rank heterogeneity** — different adapters can have different ranks (r=8, r=64, etc.). Handled by padding in the custom kernel.

**Why paging is needed:**

```
GPU HBM (80 GB):  base model (~16 GB for 8B) + active adapters
CPU DRAM:         cold adapters (30 MB × thousands = manageable)
PCIe bottleneck:  ~32 GB/s, ~1 ms cold fetch per adapter
```

S-LoRA's complexity is almost entirely a workaround for the GPU memory hierarchy.

## Cerebras Multi-LoRA

Cerebras uses a Wafer Scale Engine (WSE) — one giant chip — instead of discrete GPUs. The memory hierarchy is fundamentally different:

```
GPU:      L2 cache → HBM (3 TB/s) → CPU DRAM via PCIe (32 GB/s)
Cerebras: on-chip SRAM (44 GB, 21 PB/s) → off-chip DRAM (weight streaming)
```

With 44 GB of SRAM at 21 PB/s bandwidth, you can keep thousands of rank-16 adapters resident on-chip simultaneously — the cold-fetch problem S-LoRA works around largely doesn't exist. Adapter switching has no PCIe hop.

The tradeoff is that large base models exceed on-chip SRAM and require weight streaming from off-chip DRAM. Whether this affects adapter-switching latency in practice isn't publicly detailed.

Cerebras announced Multi-LoRA in private preview (May 2026) for dedicated endpoint customers, with no additional cost. Technical details are sparse — no published latency numbers or architecture diagrams.

## Tradeoffs of LoRA Serving Generally

**Latency overhead:** small. The extra A·B·x matmul adds ~1-3% per token when the adapter is already in memory.

**Expressiveness ceiling:** rank constrains behavioral change. r=16 is fine for domain steering; larger behavioral shifts need higher rank or full fine-tuning.

**Sequential training / stacking:**
```
Round 1: base + adapter_v1
Round 2: base + adapter_v1 + adapter_v2  (latency multiplies)
       OR merge v1 into base, train v2 on merged (loses clean base sharing)
       OR train v2 on base directly (loses accumulated learning)
```
No clean answer. Most teams do periodic merge-and-retrain to reset the base.

**Distribution drift:** as adapters diverge from the base model's distribution across training rounds, representations become misaligned. Practical limit before a new base is needed is around 5-10 rounds of significant RL training.

## A/B Testing with LoRA

For incremental model improvement (same base, iterating adapter), LoRA A/B testing works well:

```
Base model (shared)
  ├── adapter_v1  (90% traffic — current production)
  └── adapter_v2  (10% traffic — candidate)
```

Advantages over full-model A/B testing:
- Near-zero cost to add a variant (30 MB vs duplicating a full cluster)
- Clean comparisons — same base means behavioral differences are purely from adapter delta
- Fast cadence — train a new adapter in hours, deploy same day

The hard part is the reward signal: you need automated metrics (verifier pass rate, execution success, downstream task completion) that are cheap enough to run on every inference trace.

## Related Work: What Came After S-LoRA

S-LoRA left several problems unsolved. The research since has attacked them in different directions.

**KV cache invalidation on adapter switch** — [aLoRA (Dec 2024)](https://arxiv.org/abs/2512.17910)

S-LoRA ignores the KV cache: every time you switch adapters mid-sequence, the KV cache is invalidated and the full context must be recomputed. Activated LoRA fixes this with cross-model prefix cache reuse via base-aligned block hashing and activation-aware masking. Results: 58× end-to-end latency reduction, 100×+ TTFT improvement. This turns out to be a bigger latency source than memory paging for multi-turn or long-context workloads.

**Cold-start latency via CPU-GPU parallelism** — [CaraServe (Jan 2024)](https://arxiv.org/abs/2401.11240)

While a cold adapter loads from CPU→GPU over PCIe, start running it on CPU for prefilling in parallel. Hand off to GPU when ready. Also adds rank-aware scheduling — grouping requests by adapter rank to reduce heterogeneity overhead in batches. Results: 1.4× latency improvement, 99% SLO attainment.

**Scheduling fairness** — [Chameleon (Nov 2024)](https://arxiv.org/abs/2411.17741)

Focuses on the scheduler rather than memory. Multi-queue non-preemptive scheduling to prevent head-of-line blocking (a slow large-rank adapter request shouldn't stall everything). Evaluated on real production workload traces. Results: 80.7% P99 TTFT reduction, 1.5× throughput.

**Compression to eliminate paging entirely** — [Compress then Serve (Jul 2024)](https://arxiv.org/abs/2407.00066)

Instead of paging cold adapters in/out, compress thousands of adapters into a shared basis + per-adapter scaling matrices. The basis stays in GPU memory; the per-adapter scaling matrices are tiny enough to keep resident. Accepts a small quality loss from compression in exchange for no cold-fetch latency at all. Results: 80% of single-LoRA throughput across 1000 adapters.

**Disaggregating LoRA compute from the base model** — [InfiniLoRA (Apr 2026)](https://arxiv.org/abs/2604.07173)

Moves LoRA computation off the base model GPU entirely to a dedicated shared LoRA server, the same way prefill/decode disaggregation works. Adapter capacity scales independently from base model capacity. Results: 3× increase in serviceable request rate, 54% SLO improvement.

### How the papers map to problems

```
S-LoRA (2023):          heterogeneous batching + memory paging
CaraServe (2024):       cold-start latency via CPU prefilling
Chameleon (2024):       scheduling fairness, head-of-line blocking
Compress+Serve (2024):  paging eliminated via compression
aLoRA (2024):           KV cache invalidation on adapter switch
InfiniLoRA (2026):      LoRA compute disaggregated from base model
```

## Use Cases

S-LoRA's original use case is **multi-tenant serving**: one base model, many customers with their own adapters (Replicate, Together AI, fine-tuning API products). The adapter-per-customer model, served simultaneously on shared base weights.

For **continual learning loops** (Lab, Cursor-style reinforcement on production traces):
1. Train adapter via RL on collected traces
2. Deploy as new adapter version
3. Collect inference traces + reward signal
4. Feed back as next RL round

LoRA makes step 1 cheap and fast. S-LoRA / Cerebras Multi-LoRA make step 2 low-overhead. The bottleneck that remains is step 3: reward design. What signal tells you which inference traces were good?
