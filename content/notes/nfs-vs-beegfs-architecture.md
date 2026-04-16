---
title: "NFS vs BeeGFS: Architecture Differences That Matter in Practice"
date: 2026-04-16T16:57:45+0800
tags: [infra, storage, nfs, beegfs, ml-training]
---

NFS and BeeGFS are both common shared filesystems in GPU clusters. Their architectural differences create dramatically different performance profiles depending on the workload.

## Architecture Overview

- **NFS** — client-server model. Single server exports a filesystem. Simple to operate, but the single server is both a scaling ceiling and a single point of failure.
- **BeeGFS** — parallel filesystem. Separate metadata and data services, data striped across multiple storage targets. Clients talk directly to whichever storage server holds their data. Higher aggregate throughput, more moving parts, different caching semantics.

The key difference that matters most in practice: **how they handle the kernel page cache**.

## Page Cache Behaviour

Both filesystems use the Linux kernel page cache, but they invalidate it under very different rules.

### `read()` path

**NFS:** All reads go through page cache. Pages persist until memory pressure evicts them.

**BeeGFS (native mode):** Small reads (below a configurable threshold, default 512KB) go through page cache. Large reads bypass it entirely via direct I/O.

For small files (configs, Python modules, metadata), both behave the same. For large sequential reads, BeeGFS skips the cache by default.

### `mmap()` path — the critical difference

This is where the two filesystems diverge sharply.

**NFS** checks the server's `change` attribute (a version counter) on `mmap()`. If the file hasn't changed since the last access, cached pages are kept. For read-only files, the `change` attribute never increments, so pages survive across open/close cycles indefinitely.

**BeeGFS** calls `invalidate_inode_pages2_range()` unconditionally on every `mmap()` — no version check, no conditional logic. Every time a file is memory-mapped, all cached pages for that file are evicted, regardless of whether the file changed.

Why BeeGFS is unconditional: it targets HPC multi-writer workloads where multiple nodes write the same file concurrently. Always-invalidate guarantees coherence without per-file change tracking. NFS achieves the same selectively via the `change` attribute.

### Multi-process mmap on the same node — where it really hurts

`invalidate_inode_pages2_range()` operates on the inode's `address_space`, **shared across all processes on the same node**. Process B's `mmap()` evicts all pages process A just loaded — same machine, same kernel, same unchanged file.

With N processes per node, the same file gets fetched N times instead of once. For a 61 GB model with TP=8:

- **NFS:** 61 GB fetched once, 7 remaining processes read from RAM. Total: **61 GB per node.**
- **BeeGFS:** 61 GB fetched 8 times. Total: **488 GB per node.** All 8 contend for the same bandwidth.

**8x I/O amplification per node** from a single `mmap()` implementation detail.

### Summary table

| Behaviour | NFS | BeeGFS (native) |
| --- | --- | --- |
| Small `read()` (<512KB) | page cache, retained | page cache, retained |
| Large `read()` (≥512KB) | page cache, retained | **direct I/O, no cache** |
| `mmap()` page faults | page cache | page cache |
| Pages survive reopen after close | **yes** (if file unchanged) | **no** (evicted on every `mmap()`) |
| Pages shared across processes (same node) | **yes** (if file unchanged) | **no** (each `mmap()` evicts for all) |
| Cold large-file throughput | single-server bound | **parallel across storage targets** |

## Real Benchmark Numbers

Single-node benchmarks from a production cluster. BeeGFS with 1 metadata server and 4 storage targets (OSTs) over RDMA, NFS over TCP to a single server, local NVMe as baseline.

### Large model loading (61 GB, safetensors/mmap)

| Filesystem | Cold | Warm |
| --- | --- | --- |
| Local NVMe | 18.6s @ 3.3 GB/s | 0.3s @ 200+ GB/s |
| NFS | 18.4s @ 3.3 GB/s | 0.3s @ 200+ GB/s |
| BeeGFS | 10.4s @ 5.9 GB/s | 8.5s @ 7.2 GB/s |

**BeeGFS cold is fastest** — parallel RDMA reads across multiple storage nodes outperform both single-server NFS and single-device NVMe for large sequential I/O.

**BeeGFS warm ≈ BeeGFS cold** — the unconditional `mmap()` invalidation means pages never survive between loads. There is no warm cache.

**NFS warm matches local NVMe** — pages stay in kernel page cache. A 61 GB model loads from RAM at 200+ GB/s.

### Python imports (large dependency tree, ~23k files)

| Filesystem | Cold | Warm |
| --- | --- | --- |
| Local NVMe | 11.0s | 4.4s |
| NFS | 11.2s | 6.7s |
| BeeGFS | 24.1s | 9.3s |

Cold is similar — dominated by actual file I/O. Warm diverges: NFS caches `open()` lookups locally, while BeeGFS requires a metadata RPC per `open()` when no other process has the file open. With 23k files imported sequentially, each one pays this cost.

## Workload Analysis

### ML Training (load model once, checkpoint periodically)

**Winner: BeeGFS.**

Training loads the model once at job start, then the hot path is compute-bound with periodic checkpoint writes. BeeGFS gives 1.8x faster cold loads via parallel RDMA, and the lack of warm cache doesn't matter because there's only one load per job. Checkpoint writes are write-once/read-once (on resume), which plays to BeeGFS's throughput strengths.

### Inference with Model Reloads

**Winner: NFS — 30x faster on warm loads.**

0.3s warm on NFS vs 8.5s on BeeGFS. On BeeGFS every reload is effectively cold. With TP=8, the 8x I/O amplification stacks on top.

### RL Training with Weight Broadcasting

**Winner: NFS, by a wide margin.** This is where the mmap invalidation hurts most.

Pattern: trainer writes updated weights to shared storage, multiple inference workers per node (TP=8) mmap the same files — every training step. This is the multi-process mmap problem repeated on every weight update:

| | NFS | BeeGFS |
| --- | --- | --- |
| First worker | ~18s (cold) | ~10s (cold) |
| Remaining 7 workers | ~0.3s each (page cache) | ~10s each (re-fetch) |
| Total node I/O | 1x model size (61 GB) | **8x model size (488 GB)** |

Not a one-time cost at job startup — it's per-step overhead across the entire training run.

### Dataset Loading (Arrow/mmap)

**NFS for repeated epochs.** HuggingFace datasets use Arrow format with mmap — same invalidation rules apply.

### Python Virtual Environments

**Local NVMe, then NFS.** BeeGFS's per-file `open()` RPCs across 23k files make imports noticeably slower.

## Recommendation Summary

| Workload | Best Choice | Reason |
| --- | --- | --- |
| Model load, once per job | BeeGFS | Faster cold via parallel RDMA |
| Model load, repeated | NFS | 30x faster warm — pages retained |
| Weight broadcast (multi-process) | NFS | Page cache shared across workers |
| Checkpoints (write-once, read-once) | BeeGFS | High throughput, warm cache not needed |
| Dataset reads (repeated epochs) | NFS | Pages survive between epochs |
| Python imports / virtualenvs | Local NVMe > NFS | BeeGFS metadata RPCs per open() |

BeeGFS wins on raw parallel cold throughput. NFS wins on anything that benefits from warm cache — which turns out to be most ML workloads. If your cluster runs both workload types, the answer is often "both."
