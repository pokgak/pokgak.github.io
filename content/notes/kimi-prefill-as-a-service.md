---
title: "Kimi Prefill-as-a-Service: Cross-Datacenter KV Cache"
date: 2026-04-26T23:54:38+0800
tags: [llm, inference, kv-cache, distributed-systems, attention, papers]
---

Reading through the Kimi paper "Prefill-as-a-Service: KVCache of Next-Generation Models Could Go Cross-Datacenter." The core claim: you can split prefill and decode across geographically separate datacenters if the model is architected to make KV cache small enough to transfer over Ethernet. Working through the architecture and scheduling from first principles.

## Why is cross-DC KV transfer normally infeasible?

Standard attention (MHA/GQA) stores a Key and Value vector per token per attention head. A 128K context on a large model at 32K tokens produces ~60 Gbps of KV data. Transferring that across datacenters over commodity WAN links is a nonstarter — you'd need Tbps of egress at cluster scale.

## What makes Kimi's model different?

Two mechanisms combined:

**MLA (Multi-head Latent Attention)** — instead of caching full K/V vectors per token, project them down into a small latent vector `c` via a learned down-projection. Only `c` is cached. At query time, K and V are reconstructed from `c` on the fly. The latent dimension (~512) is much smaller than the full KV dimension, giving ~4.5× compression over GQA.

MLA is still full attention — every token attends to every previous token. The compression is in storage only, not the computation graph. KV cache still grows with sequence length.

**KDA (Kimi Delta Attention)** — a linear attention variant. Instead of storing per-token K/V vectors, it maintains a single fixed-size summary matrix `S` that gets updated as each new token arrives. Processing a new token means: fold that token's information into `S`, then read out from `S` to produce the output. The matrix size never changes no matter how many tokens you've seen.

What gets cached: just `S` — one fixed matrix, regardless of sequence length. No per-token storage at all.

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

The goal is to find the `t` where no stage is idle while another is saturated — PrfaaS, local prefill, and decode all hit their ceiling at the same time. Too low a threshold and you flood PrfaaS with short requests it doesn't need to handle. Too high and PrfaaS sits underutilised while local prefill is the bottleneck.

They grid-search over `t` (and the prefill/decode node split) until the throughput of each stage matches up. In the paper's case study: **t = 19.4K tokens**, routing ~50% of requests to PrfaaS.

## What does a naive approach get wrong?

Without the threshold, send all prefill to PrfaaS. Result: 1.16× throughput vs. homogeneous baseline (no specialization at all). PrfaaS-PD gets 1.54×.

Why the naive approach fails: short requests flood PrfaaS with trivial jobs, saturate the WAN link with low-value KV transfers, and starve decode nodes waiting for cache. The H200s — designed for compute-heavy long prefills — end up running 1K-token jobs.

## Does prefix caching change the routing decision?

Yes, and this is bandwidth-dependent.

The threshold applies to **incremental prefill length** (uncached tokens only), not total length. If a prefix is cached somewhere, you only prefill what's new.

Cache can exist at two places: local PD cluster or PrfaaS cluster.

**When bandwidth is scarce** — only look at local cache. Subtract whatever is cached locally from the total, check if the remaining work fits under `t`.

**When bandwidth is abundant** — look at whichever cache (local or PrfaaS) has more tokens cached. Use that as your starting point, subtract from total, check against `t`. If the PrfaaS cache was bigger, transfer it over the WAN and prefill the remainder locally.

Example: 30K token request, `t = 19.4K`, local cache = 10K, PrfaaS cache = 25K.
- Scarce: remaining work = 30K - 10K = 20K, which is over `t` → offload. PrfaaS uses its own 25K cache, only prefills 5K new tokens.
- Abundant: best cache = 25K (PrfaaS wins), remaining work = 30K - 25K = 5K, under `t` → serve locally. Transfer the 25K PrfaaS cache over WAN, prefill 5K locally.

The scheduler monitors PrfaaS egress utilization and adjusts `t` upward when the link is congested.

## How does the cache pool handle two incompatible cache types?

MLA and KDA layers have fundamentally different cache shapes:

- **MLA** — per-token latent vectors, grows with length, supports partial prefix matching at block granularity (radix tree lookup on token hash)
- **KDA** — single fixed-size recurrent state matrix `S`, size independent of length, exact-match only

KDA can't support partial hits because the summary matrix is lossy — folding in 45K tokens produces a different matrix than folding in 40K, and there's no way to "undo" the last 5K tokens to recover the earlier state. So a cache hit only works if the cached prefix is exactly the same length.

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
