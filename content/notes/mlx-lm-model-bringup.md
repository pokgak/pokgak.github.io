---
title: "mlx-lm Model Bringup Process"
date: 2026-04-07T00:00:00+0800
tags: [mlx, apple-silicon, llm, inference, model-support]
---

How new model architectures get added to [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm).

## Model Loading Flow

1. Download model from HuggingFace (weights + `config.json`)
2. Read `model_type` from `config.json` (e.g., `"llama"`, `"qwen3_5"`, `"gemma4"`)
3. `importlib.import_module(f"mlx_lm.models.{model_type}")` to find architecture
4. Module must export `Model` and `ModelArgs` classes
5. No matching module -> `ValueError: Model type X not supported`
6. `MODEL_REMAPPING` dict handles aliases

## Required Exports

**`ModelArgs`** (dataclass)
- Subclass of `BaseModelArgs` (provides `from_dict` for parsing `config.json`)
- All architecture hyperparameters: hidden size, layers, heads, vocab size, RoPE config

**`Model`** (nn.Module)
- `__call__(self, inputs, cache=None, input_embeddings=None) -> logits`
- `sanitize(self, weights)` — clean up weight names, drop unused keys
- `make_cache()` — return correct KV cache type per layer
- Optional: `shard()` for multi-device inference

**Internal pattern:**
```
Embedding -> [TransformerBlock x N] -> RMSNorm -> LM Head
```
Each block: `Input -> LayerNorm -> Attention -> Residual -> LayerNorm -> MLP -> Residual`

## Complexity Range

| Architecture | Lines | Why |
|-------------|-------|-----|
| Llama | ~274 | Standard dense transformer, baseline |
| Qwen3.5 | ~524 | Hybrid attention, MoE routing, vision, gated delta updates |
| DeepSeek V3 | ~600+ | MoE with shared experts, multi-latent attention |

Llama-like architectures (Mistral, Yi) can reuse components or be thin wrappers. Novel architectures need full forward pass from scratch.

## What Makes Bringup Non-Trivial

- **Weight mapping** — HF weight names don't always match MLX module structure. `sanitize()` handles renames, drops, reshapes. Wrong mapping = silent correctness bugs.
- **Attention variants** — GQA, MQA, sliding window, linear, sparse all need different implementations. `mx.fast.scaled_dot_product_attention` covers standard SDPA only.
- **RoPE variants** — standard, NTK-aware, YaRN, dynamic. `rope_utils.py` handles common ones.
- **KV cache types** — Standard vs RotatingKVCache (sliding window) vs ArraysCache (SSM). Hybrid models use different types per layer.
- **Quantization** — must work with MLX's quantization. Quantized SDPA has its own codepath requiring specific tensor layouts.

## Shared Infrastructure

- `base.py` — `BaseModelArgs`, causal mask, SDPA (standard + quantized)
- `cache.py` — `KVCache`, `RotatingKVCache`, `ArraysCache`
- `rope_utils.py` — RoPE initialization for common scaling schemes
- `activations.py` — SwiGLU etc.
- Models can import from each other (e.g., Qwen3.5 imports from `qwen3_next`)

## Example Bringup PRs

**Straightforward** (follows existing pattern):
- [#907 — Llama-3.1](https://github.com/ml-explore/mlx-examples/pull/907)
- [#871 — InternLM-2.5](https://github.com/ml-explore/mlx-examples/pull/871)
- [#758 — IBM Granite](https://github.com/ml-explore/mlx-examples/pull/758)

**Non-trivial** (new concepts):
- [#940 — Mamba](https://github.com/ml-explore/mlx-examples/pull/940) — SSM, custom state management
- [#1336 — Gemma3](https://github.com/ml-explore/mlx-examples/pull/1336) — sliding window + global attention hybrid
- [#1191 — DeepSeek V3](https://github.com/ml-explore/mlx-examples/pull/1191) — MoE, multi-latent attention, pipeline parallelism

**Follow-up fixes** (bringup isn't done at merge):
- [#1229 — DeepSeek V3 overflow correction](https://github.com/ml-explore/mlx-examples/pull/1229)
- [#1242 — DeepSeek sharding fix](https://github.com/ml-explore/mlx-examples/pull/1242)

## Bottom Line

- Known architecture (Llama/Mistral/Qwen-family) -> likely already supported or trivial to add
- New mechanism (novel attention, novel MoE, hybrid SSM) -> 300-600 lines of new MLX code + weight mapping
- ~117 architectures currently supported — check `mlx_lm/models/` before assuming unsupported
