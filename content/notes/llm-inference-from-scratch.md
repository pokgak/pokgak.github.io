---
title: "LLM Inference From Scratch: Basics to MLX Serving"
date: 2026-04-07T00:00:00+0800
tags: [llm, inference, mlx, apple-silicon, fundamentals]
---

Building up from basic concepts to understanding what happens when you run a model with mlx-lm on Apple Silicon.

## 1. Tensors

- Everything in an LLM is a tensor (multi-dimensional array of numbers)
- 1D = list, 2D = matrix, 3D = stack of matrices
- Model weights, inputs, outputs — all tensors. Entire computation is tensor math.

## 2. The Forward Pass

Running a model = executing a sequence of tensor math operations:

```
"Hello world" -> tokenize -> [15496, 995] -> embed -> tensor(2, 768) ->
  [transformer layers x N] -> tensor(2, 768) -> project to vocab ->
  tensor(2, 50257) -> pick highest -> next token ID
```

Steps:
1. **Tokenize** — text to token IDs (integers)
2. **Embed** — look up each ID in a table to get a vector (e.g., 768 floats)
3. **Transformer layers** — run tensor through N layers (24, 32, 80...). This is where the "intelligence" lives.
4. **Project** — multiply by vocabulary matrix to get score for every possible next token
5. **Pick** — take highest-scored token

## 3. Transformer Layer

Two main parts: **Attention** and **MLP**.

### Attention: "gather information from context"

- Each token starts isolated after embedding — doesn't know what's around it
- Attention lets tokens look at all previous tokens and score relevance
- Token becomes a weighted blend of the tokens it found most relevant
- Implementation: Q/K/V (Query/Key/Value) projections, all matrix multiplications
  - Q = "what am I looking for?", K = "what do I contain?", V = "what info do I carry?"
  - Q·K produces relevance scores, scores weight V

### MLP: "process what I gathered"

- Each token independently goes through a small neural network
- Expands vector (768 -> 3072), applies non-linear function, shrinks back
- Where the model stores and applies factual knowledge

### Residual connections

- After each sub-step: `output = input + attention(input)`, `output = output + mlp(output)`
- Information can skip steps if needed — critical for stacking 32+ layers deep

## 4. Prefill vs Decode

### Prefill (process the prompt)

- All prompt tokens processed **at once** in parallel
- N tokens x N tokens attention
- **Compute-bound** — lots of math on a big batch

### Decode (generate tokens one at a time)

- Tokens generated **one at a time**, each fed back as input
- 1 token attending to all previous tokens
- **Memory-bandwidth-bound** — small compute per step, lots of weight loading
- Why TTFT and decode speed are measured separately

## 5. KV Cache

- During decode, each new token attends to ALL previous tokens
- Without cache: recompute K, V for every previous token every step (wasteful)
- KV cache stores K/V vectors from all previous tokens, only compute for new token
- Cache grows with sequence length — several GB for long sequences

Cache variants:
- **Standard KVCache** — unbounded, grows with every token
- **RotatingKVCache** — fixed-size sliding window (e.g., Mistral)
- **ArraysCache** — for SSM/linear attention layers that store recurrent state

## 6. Quantization

Stores weights in fewer bits to reduce memory and bandwidth:

| Precision | Bits | 7B model size | Quality |
|-----------|------|---------------|---------|
| float32 | 32 | 28 GB | Full |
| float16 | 16 | 14 GB | Near-full |
| 8-bit | 8 | 7 GB | Slight loss |
| 4-bit | 4 | 3.5 GB | Noticeable loss |

- Weights stored quantized, dequantized on the fly during compute
- Less memory = model fits on device. Less bandwidth = weights load faster.
- Decode is memory-bandwidth-bound, so smaller weights -> faster decode
- **Quantized SDPA** — attention works directly on quantized KV cache, avoids dequantize step
- **Mixed-precision quantization** (OptiQ) — different layers at different bit widths

## 7. Lazy Evaluation (MLX)

- MLX builds computation graph, math only runs at `mx.eval()`
- Enables operation fusion (matmul+add in one pass instead of matmul->store->load->add)
- Bad eval placement = suboptimal fusion
  - Too many evals = too many GPU sync points
  - Too few evals = huge computation graph, high memory usage

## 8. Fused Kernels

- Kernel = function that runs on GPU. Fused kernel = multiple ops combined into one GPU call.
- Unfused attention: 4 separate read/write cycles to memory
- Fused (`mx.fast.scaled_dot_product_attention`): all in one kernel, data stays in fast on-chip memory
- Same math, ~2-4x faster

## 9. Memory Bandwidth: The Real Bottleneck

Apple Silicon uses unified memory. Key spec = memory bandwidth.

| Chip | Bandwidth |
|------|-----------|
| M1 | 68 GB/s |
| M1 Pro/Max | 200-400 GB/s |
| M2 Ultra | 800 GB/s |
| M3 Ultra | 819 GB/s |
| M4 Pro | 273 GB/s |
| M5 Pro | 307 GB/s |

During decode, GPU loads ALL model weights per token:
- M3 Ultra: 3.5 GB / 819 GB/s = ~234 tok/s theoretical max (4-bit 7B)
- M5 Pro: 3.5 GB / 307 GB/s = ~88 tok/s theoretical max

Smaller models = faster. Quantization helps. Prefill amortizes weight loading. Higher bandwidth = proportionally faster decode.

## 10. What mlx-lm Does

1. **Download** weights from HuggingFace (quantized safetensors)
2. **Load** into unified memory as MLX arrays
3. **Build** model by instantiating Python module with architecture-specific layers
4. **Prefill** — process prompt through all layers, populate KV cache
5. **Decode loop** — for each new token: forward pass -> read KV cache -> append to cache -> project to vocab -> pick next token

Performance depends on: MLX ops used (fused vs manual), tensor memory layout, `mx.eval()` placement, KV cache strategy, quantized compute paths.

## Glossary

| Term | Meaning |
|------|---------|
| **TTFT** | Time to first token (prefill speed) |
| **Tokens/sec** | Decode throughput |
| **GQA** | Grouped-query attention — shared K/V heads, reduces KV cache |
| **MQA** | Multi-query attention — all Q heads share one K/V head |
| **MoE** | Mixture of experts — subset of params active per token |
| **RoPE** | Rotary position embedding |
| **SwiGLU** | Activation function in modern LLM MLPs |
| **SDPA** | Scaled dot-product attention |
| **EOS** | End of sequence token |
