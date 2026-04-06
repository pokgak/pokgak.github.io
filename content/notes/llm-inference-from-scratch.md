---
title: "LLM Inference From Scratch: Basics to MLX Serving"
date: 2026-04-07T00:00:00+0800
tags: [llm, inference, mlx, apple-silicon, fundamentals]
---

Building up from basic concepts to understanding what happens when you run a model with mlx-lm on Apple Silicon. Each section builds on the previous one.

## 1. Tensors: The Data Structure

Everything in an LLM is a **tensor** — a multi-dimensional array of numbers. Think of it as:

- 1D tensor = a list: `[1.0, 2.0, 3.0]`
- 2D tensor = a table/matrix: rows × columns
- 3D tensor = a stack of tables: batch × rows × columns

Model weights are tensors. Inputs are tensors. Outputs are tensors. The entire computation is tensor math.

## 2. The Forward Pass: Input → Output

Running a model = executing a sequence of math operations on tensors. This is called the **forward pass**.

For an LLM, the simplified forward pass is:

```
"Hello world" → tokenize → [15496, 995] → embed → tensor(2, 768) → 
  [transformer layers × N] → tensor(2, 768) → project to vocab → 
  tensor(2, 50257) → pick highest → next token ID → "!"
```

Step by step:

1. **Tokenize** — convert text to token IDs (integers). "Hello" might be token 15496.
2. **Embed** — look up each token ID in a big table to get a vector of numbers (e.g., 768 floats). Now you have a tensor of shape (num_tokens, hidden_size).
3. **Transformer layers** — run the tensor through N layers (24, 32, 80... depends on model size). Each layer modifies the tensor. This is where the "intelligence" lives.
4. **Project** — multiply by vocabulary matrix to get a score for every possible next token.
5. **Pick** — take the highest-scored token. That's the model's prediction.

## 3. What a Transformer Layer Does

Each layer has two main parts: **Attention** and **MLP** (feed-forward network).

### Attention: "What should I focus on?"

Given a sequence of tokens, attention lets each token look at all previous tokens and decide how much to "pay attention" to each one.

Concretely:
1. Each token gets transformed into three vectors: **Query (Q)**, **Key (K)**, **Value (V)**
2. Q and K are multiplied together to get attention scores (which tokens are relevant to which)
3. Scores are used to create a weighted mix of V vectors
4. Result: each token now contains information from the tokens it attended to

The math: `Attention(Q, K, V) = softmax(Q × K^T / √d) × V`

This is all matrix multiplications — the single most performance-critical operation.

### MLP: "Process what I focused on"

After attention, each token's vector goes through a feed-forward network:

```
input → Linear(expand) → activation → Linear(shrink) → output
```

This expands the vector (e.g., 768 → 3072), applies a non-linearity, then shrinks it back. It's where the model stores and applies "knowledge."

### Residual Connections

After each sub-step (attention, MLP), the original input is added back:

```
output = input + attention(input)
output = output + mlp(output)
```

This "residual connection" is critical — without it, deep models can't train. It means information can skip layers if needed.

## 4. Prefill vs Decode: Two Phases of Generation

When you ask a model to generate text, there are two distinct phases:

### Prefill (process the prompt)

All prompt tokens are processed **at once** in parallel. The model runs the full forward pass on the entire prompt in one shot.

- Input: all N prompt tokens simultaneously
- Compute: N tokens × N tokens attention (everyone looks at everyone before them)
- Output: the hidden state + a prediction for the first generated token
- This is **compute-bound** — lots of math on a big batch

### Decode (generate tokens one at a time)

After prefill, tokens are generated **one at a time**, each fed back as input:

```
[prompt] → prefill → token₁
[prompt, token₁] → decode → token₂
[prompt, token₁, token₂] → decode → token₃
...
```

- Input: 1 new token at a time
- Compute: 1 token attending to all previous tokens
- This is **memory-bandwidth-bound** — small compute per step, but lots of weight loading

This is why TTFT (time to first token) and decode speed are measured separately — they stress different parts of the hardware.

## 5. The KV Cache: Don't Redo Work

Notice in decode, each new token needs to attend to ALL previous tokens. Naively, you'd recompute Q, K, V for every previous token on every step. That's wasteful.

The **KV cache** stores the K and V vectors from all previous tokens. On each new step, you only compute Q, K, V for the new token, then append its K and V to the cache.

```
Step 1: compute K₁, V₁, cache them
Step 2: compute K₂, V₂, cache them. Attend using [K₁,K₂] and [V₁,V₂]
Step 3: compute K₃, V₃, cache them. Attend using [K₁,K₂,K₃] and [V₁,V₂,V₃]
```

The cache grows with sequence length. For a 7B model generating 1024 tokens, the KV cache alone can be several GB.

**Cache variants:**
- **Standard KVCache** — unbounded, grows with every token
- **RotatingKVCache** — fixed-size sliding window, old entries get overwritten (used by models with sliding window attention like Mistral)
- **ArraysCache** — for non-transformer layers (SSM/linear attention) that store recurrent state instead of K/V pairs

## 6. Quantization: Shrink the Weights

A 7B parameter model at full precision (float32, 32 bits per number) = 28 GB. That's a lot of memory to load for every forward pass.

**Quantization** stores weights in fewer bits:

| Precision | Bits | 7B model size | Quality |
|-----------|------|---------------|---------|
| float32 | 32 | 28 GB | Full |
| float16 | 16 | 14 GB | Near-full |
| 8-bit | 8 | 7 GB | Slight loss |
| 4-bit | 4 | 3.5 GB | Noticeable loss |

The model weights are stored quantized (compressed), and **dequantized** (decompressed) on the fly during computation.

This matters for performance because:
- **Less memory** = model fits on your device
- **Less bandwidth** = weights load faster from memory to compute units
- Decode is memory-bandwidth-bound, so smaller weights → faster decode

**Quantized SDPA** is a special codepath where the attention computation works directly on quantized KV cache values, avoiding the dequantize step. This is faster but requires careful implementation.

**Mixed-precision quantization** (like OptiQ) quantizes different layers at different bit widths — e.g., attention layers at 8-bit, MLP layers at 4-bit — balancing quality and size.

## 7. Lazy Evaluation: MLX's Trick

MLX (Apple's ML framework) uses **lazy evaluation**. When you write:

```python
y = mx.matmul(a, b)
z = mx.add(y, c)
```

Nothing actually computes yet. MLX builds a computation graph. The math only runs when you call `mx.eval(z)`.

Why this matters for performance:
- MLX can **fuse operations** — instead of matmul→store→load→add, it can do matmul+add in one pass
- Bad `mx.eval()` placement = suboptimal fusion
  - **Too many evals** = too many GPU sync points, overhead from launching many small kernels
  - **Too few evals** = computation graph grows huge, uses lots of memory to track intermediate results

This is an implementation detail that directly affects benchmark numbers — same math, different eval placement, different speed.

## 8. Fused Kernels: Why Op Selection Matters

A **kernel** is a function that runs on the GPU. A **fused kernel** combines multiple operations into one GPU call.

Example — attention without fusion:
```
1. Q × K^T  → store result to memory
2. divide by √d → load, compute, store
3. softmax → load, compute, store
4. multiply by V → load, compute, store
```

Each step reads from and writes to memory. Memory access is slow.

Fused attention (`mx.fast.scaled_dot_product_attention`):
```
1. Q × K^T → divide → softmax → × V  (all in one kernel, data stays in fast on-chip memory)
```

Same math, ~2-4x faster, because data stays close to the compute units instead of bouncing through main memory.

When an mlx-lm model file uses the fused path vs manual implementation, it directly impacts the numbers you see in benchmarks.

## 9. Memory Bandwidth: The Real Bottleneck

Apple Silicon uses **unified memory** — CPU and GPU share the same RAM. The key spec is **memory bandwidth** (how fast data moves from memory to compute units).

| Chip | Memory Bandwidth |
|------|-----------------|
| M1 | 68 GB/s |
| M1 Pro/Max | 200-400 GB/s |
| M2 Ultra | 800 GB/s |
| M4 Pro | 273 GB/s |

During decode (one token at a time), the GPU must load ALL model weights from memory for each token. A 4-bit 7B model = ~3.5 GB of weights loaded per token.

At 200 GB/s bandwidth: 3.5 GB / 200 GB/s = 0.0175s per token → ~57 tokens/sec theoretical max.

This is why:
- Smaller models are faster (less to load)
- Quantization helps (smaller weights = less to load)
- Prefill is faster per-token than decode (batched tokens amortize the weight loading)
- Our benchmark showed Qwen 0.8B at ~245 tok/s vs 9B at ~80 tok/s — roughly proportional to model size

## 10. Putting It All Together: What mlx-lm Does

When you run `mlx_lm.load("some-model")` + generate:

1. **Download** weights from HuggingFace (quantized safetensors)
2. **Load** weights into unified memory as MLX arrays
3. **Build** the model by instantiating the Python module (`Model` class) with architecture-specific layers
4. **Prefill** — process the prompt through all layers in one pass, populate the KV cache
5. **Decode loop** — for each new token:
   - Run forward pass on the single new token
   - Attention reads from KV cache (all previous K/V) + new token's K/V
   - Append new K/V to cache
   - Project to vocabulary, pick next token
   - Repeat until done or EOS

The Python model file controls steps 3-5. The performance depends on:
- Which MLX ops are used (fused vs manual)
- How tensors are laid out in memory
- Where `mx.eval()` calls are placed
- What KV cache strategy is used
- Whether quantized compute paths are used

Two implementations of the same architecture can differ in all of these, which is why the implementation matters — not just the model and the hardware.

## Glossary

| Term | Meaning |
|------|---------|
| **TTFT** | Time to first token — measures prefill speed |
| **Tokens/sec** | Decode throughput — tokens generated per second |
| **GQA** | Grouped-query attention — K/V heads are shared across Q heads, reduces KV cache size |
| **MQA** | Multi-query attention — all Q heads share one K/V head |
| **MoE** | Mixture of experts — only a subset of parameters active per token (e.g., 26B total, 4B active) |
| **RoPE** | Rotary position embedding — encodes token position into attention |
| **SwiGLU** | Activation function used in modern LLMs (in the MLP) |
| **SDPA** | Scaled dot-product attention — the core attention computation |
| **EOS** | End of sequence token — signals the model to stop generating |
