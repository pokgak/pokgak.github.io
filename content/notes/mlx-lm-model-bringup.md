---
title: "mlx-lm Model Bringup Process"
date: 2026-04-07T00:00:00+0800
tags: [mlx, apple-silicon, llm, inference, model-support]
---

How new model architectures get added to [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm), Apple's MLX inference library for LLMs on Apple Silicon.

## How Model Loading Works

When you call `mlx_lm.load("some-model")`, the library:

1. Downloads the model from HuggingFace (weights + `config.json`)
2. Reads `model_type` from `config.json` (e.g., `"llama"`, `"qwen3_5"`, `"gemma4"`)
3. Does `importlib.import_module(f"mlx_lm.models.{model_type}")` to find the architecture
4. Expects the module to export `Model` and `ModelArgs` classes

If there's no matching module, you get `ValueError: Model type X not supported`. This is what happens when a brand-new architecture (like Gemma 4) hasn't been implemented yet.

There's also a `MODEL_REMAPPING` dict for aliases, so some model types map to existing implementations.

## What a Model Module Must Implement

Each architecture lives in its own file under `mlx_lm/models/`. The file must export:

### `ModelArgs` (dataclass)
- Subclass of `BaseModelArgs` (which provides `from_dict` for parsing `config.json`)
- Declares all architecture hyperparameters: hidden size, number of layers, number of heads, vocab size, RoPE config, etc.

### `Model` (nn.Module)
- Standard interface: `__call__(self, inputs, cache=None, input_embeddings=None) -> logits`
- `sanitize(self, weights)` — clean up weight names, drop unused keys (e.g., precomputed rotary freqs)
- `make_cache()` — return the right KV cache type per layer
- Optional: `shard()` for multi-device distributed inference

### Internal Components (Attention, MLP, TransformerBlock)
These vary by architecture, but the pattern is always:

```
Embedding → [TransformerBlock × N] → RMSNorm → LM Head
```

Where each TransformerBlock is:
```
Input → LayerNorm → Attention → Residual → LayerNorm → MLP → Residual
```

## Complexity Range

Not all model files are equal:

| Architecture | Lines | Why |
|-------------|-------|-----|
| Llama | ~274 | Standard dense transformer, the baseline everyone builds on |
| Qwen3.5 | ~524 | Hybrid attention (full + linear/SSM), MoE routing, vision support, gated delta updates |
| DeepSeek V3 | ~600+ | MoE with shared experts, multi-latent attention |

Simple architectures that are Llama-like (Mistral, Yi, etc.) can reuse components or be thin wrappers. Genuinely new architectures (hybrid SSM+attention, novel MoE routing, new attention variants) require implementing the full forward pass from scratch in MLX ops.

## Example Bringup PRs

Looking at merged PRs in [ml-explore/mlx-examples](https://github.com/ml-explore/mlx-examples) gives a sense of the range:

**Straightforward bringups** (model follows an existing pattern):
- [#907 — Add support for Llama-3.1](https://github.com/ml-explore/mlx-examples/pull/907) — Llama family, mostly config changes
- [#871 — Add support for InternLM-2.5](https://github.com/ml-explore/mlx-examples/pull/871) — Llama-like architecture
- [#758 — Add support for IBM Granite](https://github.com/ml-explore/mlx-examples/pull/758) — standard dense transformer
- [#1157 — Add support for Cohere2](https://github.com/ml-explore/mlx-examples/pull/1157) — iteration on existing Cohere support
- [#1208 — Adding support for Kyutai Helium](https://github.com/ml-explore/mlx-examples/pull/1208)

**Non-trivial bringups** (new architecture concepts):
- [#940 — Adding support for Mamba](https://github.com/ml-explore/mlx-examples/pull/940) — SSM architecture, fundamentally different from transformers, needs custom state management instead of KV cache
- [#1336 — Add support for Gemma3](https://github.com/ml-explore/mlx-examples/pull/1336) — sliding window + global attention hybrid, logit soft-capping
- [#1191 — DeepSeek V3 with pipeline parallelism](https://github.com/ml-explore/mlx-examples/pull/1191) — MoE with shared experts, multi-latent attention, required pipeline parallelism for the model to fit
- [#685 — MiniCPM implementation](https://github.com/ml-explore/mlx-examples/pull/685)

**Follow-up fixes** (bringup isn't done at merge):
- [#1229 — Better overflow correction for DeepSeek V3](https://github.com/ml-explore/mlx-examples/pull/1229) — numerical stability issues found post-merge
- [#1242 — Fix DeepSeek sharding](https://github.com/ml-explore/mlx-examples/pull/1242) — distributed inference bugs

The follow-up PRs are worth noting: initial bringup often gets the forward pass working, but edge cases in quantization, sharding, and numerical precision surface later.

## What Makes Bringup Non-Trivial

1. **Weight mapping** — HuggingFace weight names don't always match 1:1 with the MLX module structure. The `sanitize()` method handles renames, drops, and reshapes. Getting this wrong means silent correctness bugs.

2. **Attention variants** — GQA, MQA, sliding window, linear attention, sparse attention all need different implementations. MLX provides `mx.fast.scaled_dot_product_attention` for standard SDPA but anything novel needs manual implementation.

3. **RoPE variants** — Different models use different positional encoding schemes (standard, NTK-aware, YaRN, dynamic). The `rope_utils.py` helper handles common ones but new variants may need additions.

4. **KV cache types** — Standard `KVCache` vs `RotatingKVCache` (for sliding window) vs `ArraysCache` (for SSM/linear attention state). Hybrid models like Qwen3.5 use different cache types for different layers.

5. **Quantization compatibility** — The model must work with MLX's quantization. Quantized SDPA has its own codepath (`quantized_scaled_dot_product_attention`) that requires specific tensor layouts.

## Shared Infrastructure

Model files don't start from zero. `mlx_lm/models/` provides:

- `base.py` — `BaseModelArgs`, causal mask creation, SDPA (both standard and quantized)
- `cache.py` — `KVCache`, `RotatingKVCache`, `ArraysCache`
- `rope_utils.py` — RoPE initialization for common scaling schemes
- `activations.py` — SwiGLU and other activation functions

Models can also import from each other. Qwen3.5 imports its attention and MLP from `qwen3_next`, and many models are thin adaptations of the Llama implementation.

## Practical Takeaway

If a model uses a known architecture (Llama-family, Mistral-family, Qwen-family), it's likely already supported or trivial to add. If it introduces a genuinely new mechanism (new attention pattern, novel MoE routing, hybrid SSM), expect 300-600 lines of new MLX code plus careful weight mapping work.

Check `mlx_lm/models/` for the ~117 currently supported architectures before assuming something isn't supported — many model families share implementations under remapped names.
