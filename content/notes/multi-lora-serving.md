---
title: "Multi-LoRA Serving: S-LoRA vs Cerebras"
date: 2026-05-07T00:00:00+0800
tags: [lora, inference, ml-infra, gpu, cerebras, vllm]
---

Notes on how LoRA adapters are served at scale, the tradeoffs involved, and how Cerebras's approach differs from vLLM's S-LoRA.

## What LoRA Is

### Background: the fine-tuning problem before LoRA

The standard way to adapt a pretrained model to a new task was full fine-tuning: load the weights, compute gradients for all parameters, run an optimizer. This works, but the costs scale with model size:

```
GPT-2 (2019, 1.5B params):  full fine-tune fits on a single GPU, fine
GPT-3 (2020, 175B params):  full fine-tune needs ~1.2 TB GPU memory
                             (fp32 weights + gradients + Adam optimizer state)
```

By 2020–2021 it was clear that "just fine-tune the whole thing" wasn't viable for large models unless you had significant cluster access. Several approaches tried to solve this:

**Adapter layers** (Houlsby et al., 2019) — insert small bottleneck MLP layers between transformer sub-layers. Only the adapters are trained. Parameter-efficient, but adds sequential compute in the forward pass. Every request pays the adapter latency even after training.

**Prefix tuning** (Li & Liang, 2021) — prepend learned "virtual tokens" to the KV cache of every layer. No architecture change, but training is unstable and every prefix token consumes context window space.

**Prompt tuning** (Lester et al., 2021) — similar idea but only at the input embedding layer. Simpler but less expressive than prefix tuning.

**BitFit** (Ben-Zaken et al., 2021) — only train the bias terms. Extremely lightweight (~0.1% of parameters) but very limited expressiveness; works only for simple task shifts.

All of these had tradeoffs: inference overhead, training instability, or limited expressiveness. LoRA was introduced to address all three at once.

### The LoRA paper

"LoRA: Low-Rank Adaptation of Large Language Models" — Hu et al. (Microsoft Research)
- Submitted to arxiv: June 2021 ([arXiv:2106.09685](https://arxiv.org/abs/2106.09685))
- Accepted at ICLR 2022

The key insight from the paper: empirically, the weight updates during fine-tuning are low-rank. They tested this by training full fine-tunes and measuring the rank of ΔW — it was consistently much lower than the full matrix rank. If the update is intrinsically low-rank, you can parameterize it directly as a low-rank product B·A and never materialize the full ΔW.

Advantages over prior PEFT methods:
- **No inference overhead** — adapters can be merged into W before serving
- **No context window cost** — unlike prefix tuning
- **Stable training** — random + zero initialization means you start from the base model
- **Parallelizes with base compute** — B·A·x can run in parallel with W·x, unlike serial adapter layers

LoRA became the dominant PEFT method by 2022–2023. By 2023 the question shifted from "how do we train efficiently" to "how do we *serve* many LoRA adapters efficiently" — which is what S-LoRA and the papers below address.

### The core idea

Full fine-tuning updates every parameter in a model. For a 7B model in bf16 that's ~14 GB of gradient state, optimizer state (Adam needs 2× that), and activations — just to train, before inference. For most fine-tuning tasks this is wasteful: the weight changes are empirically low-rank. You don't need to move all ~4096×4096 directions in a weight matrix; the task-relevant update lives in a small subspace.

LoRA (Hu et al., 2021) exploits this. It freezes all base model weights and injects a pair of small matrices alongside each target weight:

```
Original:  h = W · x              W ∈ R^{d_out × d_in}  (frozen)
With LoRA: h = W · x + (B·A) · x
                         └──┘
                    B ∈ R^{d_out × r}
                    A ∈ R^{r × d_in}
                    r << min(d_out, d_in)
```

A is initialized with random Gaussian, B is initialized to zero — so at training start the adapter contributes nothing, and the model starts from the base weights. During training only A and B are updated; W is frozen.

The rank r is the key hyperparameter. For a 4096×4096 attention weight matrix:

```
Full fine-tune:  4096 × 4096 = 16.8M parameters
LoRA r=8:        4096×8 + 8×4096 = 65K parameters    (~256× smaller)
LoRA r=16:       4096×16 + 16×4096 = 131K parameters (~128× smaller)
LoRA r=64:       4096×64 + 64×4096 = 524K parameters (~32× smaller)
```

### Where LoRA is applied

A transformer has many weight matrices per layer: Q, K, V, O projections in attention, and up/gate/down projections in the MLP. LoRA can target any subset. The original paper targeted Q and V only; in practice most fine-tuning applies it to all attention projections and sometimes the MLP weights too.

```
Attention:  W_q, W_k, W_v, W_o  ← most commonly targeted
MLP:        W_up, W_gate, W_down ← often included for larger behavioral changes
Embeddings: less common, larger adapters
```

More targets = more expressiveness but larger adapter files and more compute per forward pass.

### The scaling factor α

In practice the update is scaled:

```
h = W · x + (α/r) · B·A · x
```

α is a fixed hyperparameter (often set equal to r, making the scale factor 1). The reason: as you increase rank, you want the initialization to remain consistent in magnitude. Setting α=r means the effective learning rate doesn't change when you sweep ranks.

### Rank selection intuition

Low rank works because fine-tuning tasks are low-dimensional. Adapting a general model to answer medical questions, write in a specific style, or solve math problems requires shifting representations in a relatively small number of directions. Empirically:

- **r=4–8**: lightweight steering, prompt style, simple domain adaptation
- **r=16–32**: standard fine-tuning, instruction following, moderate task specialization
- **r=64–128**: significant behavioral change, complex task domains
- **r=256+**: approaching full fine-tune expressiveness; usually just do full fine-tune

One signal that rank is too low: the adapter weights saturate during training (norms grow very large relative to base weights). The adapter is trying to express more than its rank allows.

### Merged vs unmerged at inference

At inference time you have two options:

**Merged** — add the adapter directly into the base weights before serving:
```
W_merged = W + (α/r) · B·A
```
Zero inference overhead. The model is now a new set of weights indistinguishable from a full fine-tune. Downside: you've lost the separate adapter; you can't serve multiple variants from the same base.

**Unmerged** — keep W and (B, A) separate, compute both at inference:
```
h = W·x + (α/r)·B·A·x
```
Small compute overhead (~1-3%), but you can hot-swap adapters and share the base model across many fine-tunes. This is the multi-LoRA serving model.

### Variants worth knowing

**QLoRA** — quantize the base model to 4-bit (NF4), keep LoRA adapters in bf16. Reduces base model memory 4×, enabling fine-tuning 70B models on a single GPU. The gradient path still flows through bf16 adapters; quantization is only for the frozen weights.

**DoRA** (Weight-Decomposed LoRA) — decomposes W into magnitude and direction, applies LoRA only to the directional component. Empirically better than LoRA on many tasks at the same rank, but slightly more compute.

**LoRA+** — uses different learning rates for A and B matrices (B gets a higher lr). Simple change that consistently improves convergence speed.

**rsLoRA** — scales by α/√r instead of α/r. More stable at high ranks.

These variants are mostly drop-in: same serving infrastructure, slightly different training dynamics.

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
