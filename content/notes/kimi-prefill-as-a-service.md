---
title: "Kimi Prefill-as-a-Service: Cross-Datacenter KV Cache"
date: 2026-04-26T23:54:38+0800
tags: [llm, inference, kv-cache, distributed-systems, attention]
---

Reading through the Kimi paper "Prefill-as-a-Service: KVCache of Next-Generation Models Could Go Cross-Datacenter." The core claim: you can split prefill and decode across geographically separate datacenters if the model is architected to make KV cache small enough to transfer over Ethernet. Working through the architecture and scheduling from first principles.

## Why is cross-DC KV transfer normally infeasible?

Standard attention (MHA/GQA) stores a Key and Value vector per token per attention head. A 128K context on a large model at 32K tokens produces ~60 Gbps of KV data. Transferring that across datacenters over commodity WAN links is a nonstarter — you'd need Tbps of egress at cluster scale.

## What makes Kimi's model different?

Two mechanisms combined:

**MLA (Multi-head Latent Attention)** — instead of caching full K/V vectors per token, project them down into a small latent vector `c` via a learned down-projection. Only `c` is cached. At query time, K and V are reconstructed from `c` on the fly. The latent dimension (~512) is much smaller than the full KV dimension, giving ~4.5× compression over GQA.

MLA is still full attention — every token attends to every previous token. The compression is in storage only, not the computation graph. KV cache still grows with sequence length.

**KDA (Kimi Delta Attention)** — a linear attention variant. Replaces softmax with a kernel approximation that allows the attention computation to be expressed as a recurrent state update:

```
S_t = S_{t-1} + φ(k_t)ᵀ · v_t   ← fixed-size state, O(1) update
output_t = φ(q_t) · S_t
```

What gets cached: a single fixed-size state matrix `S`, regardless of sequence length. No per-token storage at all.

The tradeoff: the recurrent state is lossy — it compresses all past tokens into a fixed-size matrix, so precise recall of specific tokens degrades over long contexts.

## Why not just use pure KDA then?

Quality. Pure linear attention degrades on tasks requiring exact recall of distant tokens. Full attention (MLA) is needed for that precision.

## So how do they combine them?

**3 KDA layers : 1 MLA layer** throughout the model. KDA handles most of the computation with zero growing cache. MLA handles 25% of layers with compressed but exact per-token cache.

Combined KV reduction vs standard GQA: **~36×**
- MLA vs GQA: ~4.5×
- Only 1 in 4 layers produces growing KV cache: ~8×
- Combined: ~36×

At 36× reduction, a 128K context that would've required 60 Gbps now needs under 2 Gbps — within WAN range.

## What's the actual system architecture?

**PrfaaS clusters** (H200 GPUs, compute-dense) — handle long-context prefill, can be anywhere geographically.  
**Local PD clusters** (H20 GPUs, memory-bandwidth-optimized) — handle decode and short prefills, near the user for latency.

Short requests stay local. Only requests above a length threshold `t` get offloaded to PrfaaS over commodity Ethernet.

## How is the threshold `t` determined?

Grid search over two equilibrium conditions:

```
Θ_prfaas / p  =  Θ_pd-p / (1-p)      # PrfaaS and local prefill balanced
Θ_prfaas + Θ_pd-p  =  Θ_pd-d         # total prefill balanced against decode
```

`p = P(L > t)` is the fraction of requests that exceed the threshold. The optimum is where all three pipeline stages (PrfaaS, local prefill, decode) hit their ceiling simultaneously. In the paper's case study: **t = 19.4K tokens**, routing ~50% of requests to PrfaaS.

## What does a naive approach get wrong?

Without the threshold, send all prefill to PrfaaS. Result: 1.16× throughput vs. homogeneous baseline (no specialization at all). PrfaaS-PD gets 1.54×.

Why the naive approach fails: short requests flood PrfaaS with trivial jobs, saturate the WAN link with low-value KV transfers, and starve decode nodes waiting for cache. The H200s — designed for compute-heavy long prefills — end up running 1K-token jobs.

## Does prefix caching change the routing decision?

Yes, and this is bandwidth-dependent.

The threshold applies to **incremental prefill length** (uncached tokens only), not total length. If a prefix is cached somewhere, you only prefill what's new.

Cache can exist at two places: local PD cluster (`l_pd`) or PrfaaS cluster (`l_prfaas`).

**When bandwidth is scarce** — only look at local cache:
```
if l_total - l_pd ≤ t  →  serve locally
else                   →  offload to PrfaaS
```

**When bandwidth is abundant** — shop across both:
```
if l_total - max(l_prfaas, l_pd) ≤ t  →  serve locally, transfer PrfaaS cache if bigger
else                                   →  offload to PrfaaS
```

Example: 30K token request, `t = 19.4K`, local cache = 10K, PrfaaS cache = 25K.  
- Scarce: `30K - 10K = 20K > t` → offload. PrfaaS uses its 25K cache, prefills 5K.  
- Abundant: `30K - 25K = 5K ≤ t` → serve locally. Transfer PrfaaS 25K cache over WAN, prefill 5K locally.

The scheduler monitors PrfaaS egress utilization and adjusts `t` upward when the link is congested.

## How does the cache pool handle two incompatible cache types?

MLA and KDA layers have fundamentally different cache shapes:

- **MLA** — per-token latent vectors, grows with length, supports partial prefix matching at block granularity (radix tree lookup on token hash)
- **KDA** — single fixed-size recurrent state matrix `S`, size independent of length, exact-match only

KDA can't support partial hits because `S_t` is a lossy compression of tokens 1..t — there's no way to reconstruct `S_40K` from `S_45K`. The state is non-invertible.

**Solution:** separate KVCache groups (one per layer type) but a single shared physical pool with aligned block sizes. One allocator, one free list, no fragmentation from size class differences. Reuse lookup logic is per-group.

Within the pool, blocks are tagged:
- **Prefix-cache blocks** — kept after prefill for future requests to hit
- **Transfer-cache blocks** — written at the tail of a prefill, transferred to decode node over network, then freed immediately

The tag is set by the scheduler at request time: PrfaaS-routed requests produce transfer-cache tail blocks; local requests produce prefix-cache blocks.

## What do the numbers look like in production?

Case study on the 1T hybrid model, 96 H20 + some H200 GPUs:
- Average PrfaaS egress: **13 Gbps** (13% of 100 Gbps link)
- Throughput: **54% improvement** vs homogeneous PD baseline
- P90 TTFT for long-context: **64% lower** (4.44s → 2.22s)

The key insight from the feasibility analysis: the bandwidth equation only applies to offloaded requests. Selective routing means most of your WAN headroom stays free even at scale.
