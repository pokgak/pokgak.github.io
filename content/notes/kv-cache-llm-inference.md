---
title: "KV Cache in LLM Inference"
date: 2026-05-19T19:39:48+0800
tags: [llm, inference, systems]
---

Exploring KV cache in LLM inference — what it is, how it's been optimized over time, and how it maps to concepts from systems and databases.

---

**What is KV cache and why does it exist?**

When a transformer generates tokens autoregressively, it computes Keys and Values for every previous token at each step. Without caching, generating token #100 means recomputing K and V for tokens 1–99. Token #101 repeats that plus one more — cost grows quadratically.

KV cache stores K and V after computing them. Next token generation, load from memory instead of recompute. Only the new token needs fresh work.

The tradeoff: speed for memory. Cache size = `2 × layers × heads × head_dim × sequence_length × batch_size × bytes_per_element`. For a 70B model at 128k context, tens of gigabytes per request. This makes inference memory-bandwidth bound — the GPU spends most time waiting to read KV cache from HBM (GPU high-bandwidth memory), not doing matrix multiplications.

---

**What are MHA, MQA, and GQA? Why do they matter for KV cache size?**

In **Multi-Head Attention (MHA)**[^1], each head has its own K and V matrices. 32 heads = 32 K matrices + 32 V matrices in cache.

**Multi-Query Attention (MQA)**[^2] (Shazeer, 2019) keeps 32 separate Q heads but shares a single K and V across all of them. Cache shrinks ~32x. Slight quality degradation — all heads look up from the same K/V pool.

**Grouped Query Attention (GQA)**[^3] (Ainslie et al., 2023) is the middle ground — groups of heads share K/V (e.g. 8 KV heads for 32 Q heads). ~4x cache reduction, minimal quality loss. Now the default in most open models (Llama 2/3, Mistral).

*Intuition: heads diverge in what they ask (Q), not in what they look up (K/V) — so sharing K/V is mostly fine.*

---

**What is MLA (Multi-head Latent Attention) and how does it go further than GQA?**

MHA → MQA → GQA all reduce KV cache by sharing K/V across heads. MLA[^4] (DeepSeek-V2, 2024) takes a different approach: instead of sharing, it *compresses* K and V into a small latent vector using low-rank projection, then decompresses back to full K/V at attention time.

Concretely: instead of storing `num_heads × head_dim` K and V vectors per token, MLA stores a single compressed latent of dimension `d_c` where `d_c << num_heads × head_dim`. At attention time, project the latent back up to full K/V. The latent is what gets cached — much smaller.

Why this works: K and V matrices across heads are not independent — they lie in a low-dimensional subspace. Low-rank projection captures that structure, same idea as PCA or SVD compression.

Cache reduction: DeepSeek-V2 reports ~5–13x reduction vs standard MHA depending on configuration, with minimal quality loss. Outperforms GQA on the cache-size-to-quality tradeoff.

Tradeoff: the decompression adds compute at attention time. You're trading cache memory for a small amount of extra matrix multiplication per decode step — a good trade when memory bandwidth is the bottleneck.

*Intuition: GQA shares K/V across heads like giving multiple workers the same filing cabinet. MLA compresses the filing cabinet itself into a summary, then reconstructs the full cabinet only when needed.*

---

**Can you reduce KV cache size without changing the attention architecture — just make each entry smaller?**

Yes — KV cache quantization. Store K and V in lower precision instead of the default float16 or bfloat16.

- **INT8**: halves memory vs float16. Quality loss typically <0.5% perplexity on most benchmarks. Standard in vLLM, TensorRT-LLM since 2024.
- **INT4**: quarters memory vs float16. More quality loss, workload-dependent — fine for long context summarization, noticeable on reasoning tasks.

Why K and V tolerate quantization better than weights: the attention computation averages over many tokens. Quantization error in one K/V entry gets washed out by the softmax weighting. Errors don't accumulate the way they would in a weight matrix multiply.

This is orthogonal to MHA/MQA/GQA/MLA — you can combine them. A model using GQA + INT8 KV cache gets both the sharing reduction and the precision reduction.

*Intuition: instead of fewer files in the cabinet (MQA/GQA) or a compressed summary (MLA), you're just using smaller handwriting. Each entry takes less space, with acceptable loss of precision.*

---

**How do you measure quality loss from architectural changes like MQA/GQA?**

**Perplexity** is the primary proxy — how surprised the model is by real text. Low = predicted well, high = confused. Interpretable: perplexity of 10 means the model is as uncertain as picking uniformly from 10 options at each step. Cheap to compute on any corpus, sensitive to small architectural changes.

Downstream task benchmarks confirm: MMLU, HellaSwag, WinoGrande, GSM8K, HumanEval.

GQA paper finding: GQA (8 groups) recovered almost all MHA quality; MQA had noticeable drops on reasoning. Caveat: models trained from scratch with GQA recover more than models converted post-hoc.

Limit: perplexity doesn't always correlate with task performance — use both.

---

**What is FlashAttention and how does it address the memory problem?**

Standard attention writes the full Q×K^T matrix to HBM, runs softmax (round trip to HBM), multiplies by V (another round trip). Every intermediate result is a HBM read/write. For a 4096-token sequence that's a 4096×4096 matrix being written and read repeatedly — bandwidth-bound, not compute-bound.

FlashAttention[^5] tiles input into blocks that fit GPU SRAM (~20MB, ~10x faster than HBM). Uses a running rescaling trick for softmax — as each tile is processed, a running max and normalization factor corrects partial results. Never materializes the full matrix. Mathematically identical to standard attention.

*Intuition: standard attention does its work on a whiteboard (HBM) — slow but big. FlashAttention keeps everything on a notepad (SRAM) — fast but small — only writes the final answer to the whiteboard.*

---

**FlashAttention's tiling reminds me of vectorized execution in databases (X100/ClickHouse). How similar is it?**

The shape is the same — batch work into chunks, accumulate partial results, avoid materializing the full intermediate. But the bottleneck differs:

| | Vectorized execution (X100) | FlashAttention |
|---|---|---|
| Problem | per-row interpreter overhead (Volcano model) | per-element HBM round trips |
| Fix | batch 1024–4096 rows per call | batch into SRAM-sized tiles |
| Primary bottleneck | CPU function-call overhead | GPU memory bus |

X100's main win is amortizing interpreter overhead — you'd get most of the speedup even with infinite L1 cache. FlashAttention's main win is reducing HBM traffic — if HBM were as fast as SRAM the paper is pointless.

Deepest similarity: both only work because the operations are algebraically decomposable. Aggregations are associative; softmax can be incrementally rescaled. Same insight, different hardware layer.

Reference: *MonetDB/X100: Hyper-Pipelining Query Execution*[^6] (Boncz, Zukowski, Nes — CIDR 2005).

---

**What is PagedAttention and how does it map to OS virtual memory?**

Without it, KV cache is pre-allocated as a contiguous buffer per request. This causes internal fragmentation (reserved 2048 tokens, used 1000) and external fragmentation (enough total free memory but no contiguous block large enough). The same problem virtual memory was invented to solve.

PagedAttention[^7] breaks KV cache into fixed-size blocks (~16–32 tokens of K+V). Each request has a block table mapping logical sequence positions to physical HBM blocks — same indirection as a page table.

| OS Virtual Memory | PagedAttention |
|---|---|
| Physical RAM | GPU HBM |
| Virtual address space | Logical KV sequence |
| Page (4KB) | KV block (~16–32 tokens) |
| Page table | Block table (logical→physical) |
| Page fault → allocate | New tokens → allocate block on demand |
| Free page on process exit | Free blocks when request finishes |
| Copy-on-write | Shared prefix blocks across requests |

PostgreSQL analogy: shared_buffers is a pool of 8KB pages — queries don't care about physical location, buffer manager handles translation. Same pattern. NFS analogy: rsize chunks are the unit of transfer, not bytes — KV blocks are the unit of allocation.

*Intuition: attention kernel sees a clean logical sequence. Block manager hides fragmented, shared, dynamically allocated HBM behind a block table — same abstraction as a page table.*

What's different: no transparent swap to disk — if HBM runs out, preempt the request to CPU DRAM or reject. Latency too strict. Block size is also fixed by model architecture, not hardware page size.

---

**What are prefill and decode — and why do they behave differently?**

LLM inference has two distinct phases:

**Prefill**: process the entire input prompt in one forward pass. All input tokens are known upfront, so their K/V can be computed in parallel. Highly parallelizable — the GPU does a large matrix multiplication over all input tokens simultaneously. Compute-bound.

**Decode**: generate output tokens one at a time. Each step produces one new token, computes its K/V, appends to cache, then reads the entire cache to generate the next token. Cannot be parallelized across tokens — each token depends on the previous. Memory-bandwidth-bound — mostly waiting to read the growing KV cache from HBM.

This asymmetry matters for system design:
- Prefill latency scales with prompt length. Decode latency scales with output length × KV cache size.
- A request with a 10k-token prompt but 50-token output is prefill-dominated. A chatbot reply is decode-dominated.
- Disaggregated prefill/decode[^8] (Splitwise, Sarathi-Serve, 2024) routes these phases to different hardware because they have different bottlenecks. Prefill wants compute (matrix multiply throughput). Decode wants memory bandwidth (HBM read speed).

*Intuition: prefill is like reading a whole book at once — fast because you can parallelize. Decode is like writing a book one word at a time, checking everything you've written before each new word — fundamentally sequential.*

---

**How does PagedAttention enable continuous batching?**

Static batching groups N requests and runs until all N finish. Short requests sit idle waiting for the longest — GPU utilization ~30-40%.

Adding a request mid-flight previously required finding a contiguous free block large enough for its KV cache — may not exist even with sufficient total free memory. Too hard, nobody bothered.

With PagedAttention, adding a request mid-batch = allocate a few free blocks. No contiguity needed. When a request finishes, blocks return immediately. Scheduler runs every decode step: free finished blocks → admit waiting requests → run next step.

*Intuition: static batching = bus waits at depot until full, no stops until the end. Continuous batching = bus picks up and drops off at every stop — always full, always moving.*

Result: ~70-90% GPU utilization vs ~30-40%. Main reason vLLM was a step change in inference throughput.

---

**What is RadixAttention (SGLang) and how does it improve prefix caching?**

Flat prefix caching (original vLLM) hashes a block's token sequence — on match, reuse. One level only. Misses tree-shaped sharing: same system prompt + different few-shot examples + different questions all share the system prompt but diverge after.

RadixAttention[^9] uses a radix tree where each node is a shared token segment with a pointer to its KV blocks. New request walks the tree: matched nodes reuse existing KV blocks, unmatched suffix is computed and inserted as a new leaf. Tree grows organically from traffic — topology stabilizes after warmup.

Node splitting handles partial matches: if [system_prompt | question_A] is one node and [system_prompt | question_B] arrives, split at divergence — system_prompt becomes parent, question_A/B become children. Reference counting prevents eviction of blocks in active use.

**Overhead:** tree walking is O(sequence length) once per request at schedule time, not per decode step. CPU bookkeeping happens while GPU runs decode — different time domains, effectively invisible. Real cost is memory fragmentation from fine-grained nodes, mitigated by minimum block size.

**Adoption:** SGLang formalized the technique early 2024. vLLM v0.4+ added multi-level automatic prefix caching shortly after. Now table stakes in production inference servers.

*Intuition: prompts have tree-shaped sharing — system prompt is trunk, conversation history is branches, individual turns are leaves. RadixAttention caches the tree so you only compute KV for the genuinely new part.*

PostgreSQL analogy: radix tree = B-tree index, KV blocks = buffer pool pages. Walking tree = index scan. Cache miss = page fault, compute and insert.

---

**Does cross-request KV cache sharing work for requests from the same client with the same system prompt?**

Yes — this is the best case. PagedAttention provides the mechanism (block table indirection + CoW), RadixAttention provides the detection. Together: RadixAttention finds the match, PagedAttention does the sharing.

1000 requests with the same 2048-token system prompt: first request computes KV cache, blocks enter radix tree. Requests 2–1000 have their block tables pointed at the same physical blocks — system prompt KV becomes a global read-only cache, computed once, reused indefinitely.

This extends cross-session: blocks persist in the radix tree until evicted. New session the next day hits the same cached blocks if not evicted. This is what prompt caching APIs (Anthropic, OpenAI, Google) expose — pay compute cost once, reuse within cache TTL.

Limits:
- One token difference anywhere in the shared prefix = cache miss at that point. Exact match required.
- Decode phase is always private — generated tokens diverge per request immediately.

*Intuition: shared system prompts = a shared library loaded into multiple processes. PagedAttention = virtual memory making shared mappings possible. RadixAttention = the dynamic linker that maps the already-loaded library instead of reloading it.*

---

**Does cross-tenant KV cache sharing raise privacy concerns?**

Mostly overstated. KV cache is the result of matrix multiplications on token embeddings — not raw text. Doesn't directly contain user data.

The theoretical concern is a reconstruction attack: infer input tokens from cached representations by probing model outputs. Not demonstrated in practice, requires significant sustained access.

For identical system prompts: both tenants already know exactly what's in the prefix — they sent the same tokens. Nothing to reconstruct.

The real risk would be accidental prefix matching across tenants with *different* private content — but block granularity ensures sharing stops exactly at the divergence point. Private suffix blocks are never shared.

Production tenant scoping (sharing only within API key boundary) is mostly regulatory conservatism — SOC2, HIPAA auditors ask "can tenant A ever touch tenant B's memory?" Practical risk is low.

---

**Why is KV cache offloading to CPU/NVMe viable for long context workloads despite the ~80x bandwidth gap (PCIe vs HBM)?**

The bandwidth gap is real — PCIe ~40GB/s vs HBM ~3.35TB/s on H100. Per-token decode paying that cost on every step is too slow for interactive use.

What makes it viable: attention is sparse. In a 1M token context, the model heavily attends to recent tokens and a few important tokens. Most of the middle is rarely touched. You don't need all KV cache every decode step — only the hot fraction.

Approaches that make it work:
- **Tiered caching**: hot tokens (recent + high attention score) in HBM, cold tokens on CPU DRAM. Prefetch blocks before attention needs them.
- **Prefill/decode asymmetry**: long context prefill is a one-time cost — you can afford latency there. Offload during prefill, stream back during decode.
- **Use case tolerance**: "summarize this 500 page document" tolerates 10s latency. Chat does not.
- **NVMe**: 12–14GB/s sequential read + aggressive prefetching = viable when you don't need everything at once.

*Intuition: same as PostgreSQL buffer pool — you don't need all pages in RAM, just the hot ones. Trick is predicting which ones are hot. Attention scores are the signal.*

---

**How do attention scores work as an eviction signal?**

For each generated token, attention computes:

```
score(i) = dot(Q_current, K_i) / sqrt(head_dim)
```

After softmax, scores sum to 1. Near-zero score = token barely contributes = safe to offload. These scores are computed anyway during every attention step — using them as an eviction signal is free.

**Attention sink phenomenon**[^10] (StreamingLLM): the first few tokens almost always get high attention scores even when semantically irrelevant. The model uses them as a probability dump when nothing else is relevant. Evict them and outputs degrade badly — always keep in HBM regardless.

*Intuition: attention scores are a free readout of which memories the model is actually using. Near-zero score = cold page in a buffer pool.*

---

**Does the workload type affect which tokens stay hot — similar to how query patterns affect Redis/PostgreSQL cache hotness?**

Yes, and the analogy holds well but breaks in an important way.

**Where it holds:** shared system prompts behave like a hot table every query hits — attention scores for those tokens are reliably high across all requests.

**Where it diverges:** in Redis/PostgreSQL, hotness is a property of the *data*. KV cache hotness is a property of *data + current generation state + query*. Two requests with identical prompts can have different attention patterns depending on what tokens they've already generated.

Workload patterns:
- **RAG/document QA**: attention concentrates on passages relevant to the current question. Diverse queries = different hot regions = bad for offloading.
- **Code completion**: strong recency bias + attends to function signatures. Relatively predictable.
- **Long conversation**: early turns go cold naturally. Good offloading candidate.
- **Multi-document reasoning**: attention hops between documents unpredictably. Worst case — hard to prefetch.

*Intuition: PostgreSQL cache hotness is a property of the data. KV cache hotness is context-dependent — it shifts as generation proceeds and the query changes what it's looking for.*

---

**Who decides which tokens to evict — do systems implement their own heuristics?**

No standard exists. Active research area. What systems actually do:

- **vLLM**: block-level LRU. No attention-score peeking. CPU offload used for whole-request preemption under memory pressure, not fine-grained tiering.
- **H2O**[^11] (research): accumulates per-token importance scores (sum of attention weights across heads/steps), evicts bottom-k. Not widely deployed.
- **SnapKV**[^12] (research): identifies important tokens during prefill by examining attention on the last few query tokens, keeps those throughout decode. Prefill-time prediction rather than online tracking.
- **InfiniGen / FastDecode** (research): predict which blocks will be needed using lightweight speculative models. More prefetch predictor than eviction policy.
- **Production (vLLM, TensorRT-LLM)**: prefix caching + whole-request preemption + position-based proxy (recent = hot). Attention-score approaches remain mostly research — tracking per-token per-head per-step adds up.

*Intuition: like PostgreSQL before pg_buffercache gave visibility into what was hot. Systems evict on cheap proxies (position, recency). True attention-score hotness is expensive to track. Research is ahead of production.*

---

## Appendix: Timeline

- **2017** — Transformers (*Attention is All You Need*, Vaswani et al.[^1]). K/V/Q defined. KV cache implicit in autoregressive decoding.
- **2019** — MQA (Shazeer[^2]). First paper to treat KV cache size as the primary problem.
- **2020** — Longformer (Beltagy et al.) — sliding window attention to bound cache for long contexts.
- **2022** — FlashAttention (Dao et al.[^5]) — HBM-bandwidth-aware attention. Made memory bottleneck explicit.
- **2023** — GQA (Ainslie et al.[^3]); PagedAttention/vLLM (Kwon et al.[^7]); StreamingLLM/attention sinks (Xiao et al.[^10]); H2O eviction (Zhang et al.[^11]); speculative decoding.
- **2024** — DeepSeek-V2 MLA[^4] (low-rank compressed KV); SGLang RadixAttention[^9]; disaggregated prefill/decode[^8] (Splitwise, Sarathi-Serve); prompt caching APIs (Anthropic, OpenAI, Google); KV quantization (INT8/INT4) standard in vLLM/TensorRT-LLM.
- **2025** — 1M+ context windows make KV cache a systems-architecture problem. CPU/NVMe offloading matures. Cross-request persistent cache emerges.
- **2026** — KV cache as distributed resource. MLA adoption spreading. Debate: solve decode bottleneck via hardware (HBM bandwidth) or architecture (MLA, sparse attention)?

---

## References

[^1]: Vaswani et al., "Attention is All You Need" (2017). https://arxiv.org/abs/1706.03762
[^2]: Shazeer, "Fast Transformer Decoding: One Write-Head is All You Need" (2019). https://arxiv.org/abs/1911.02150
[^3]: Ainslie et al., "GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints" (2023). https://arxiv.org/abs/2305.13245
[^4]: DeepSeek-AI, "DeepSeek-V2: A Strong, Economical, and Efficient Mixture-of-Experts Language Model" (2024). https://arxiv.org/abs/2405.04434
[^5]: Dao et al., "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness" (2022). https://arxiv.org/abs/2205.14135
[^6]: Boncz, Zukowski, Nes, "MonetDB/X100: Hyper-Pipelining Query Execution" (CIDR 2005). https://www.cidrdb.org/cidr2005/papers/P19.pdf
[^7]: Kwon et al., "Efficient Memory Management for Large Language Model Serving with PagedAttention" (2023). https://arxiv.org/abs/2309.06180
[^8]: Splitwise: Patel et al., "Splitwise: Efficient Generative LLM Inference Using Phase Splitting" (2024). https://arxiv.org/abs/2311.18677
[^9]: Zheng et al., "SGLang: Efficient Execution of Structured Language Model Programs" (2023). https://arxiv.org/abs/2312.07104
[^10]: Xiao et al., "Efficient Streaming Language Models with Attention Sinks" (2023). https://arxiv.org/abs/2309.17453
[^11]: Zhang et al., "H2O: Heavy-Hitter Oracle for Efficient Generative Inference of Large Language Models" (2023). https://arxiv.org/abs/2306.14048
[^12]: Li et al., "SnapKV: LLM Knows What You are Looking for Before Generation" (2024). https://arxiv.org/abs/2404.14469
