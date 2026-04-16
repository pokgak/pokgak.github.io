---
title: "NFS vs BeeGFS: Architecture Differences That Matter in Practice"
date: 2026-04-16T16:57:45+0800
tags: [infra, storage, nfs, beegfs, ml-training]
---

NFS and BeeGFS are both common shared filesystems in GPU clusters, but their architectural differences create dramatically different performance profiles depending on the workload. This isn't about which is "better" — it's about understanding where each one wins and why.

## Architecture Overview

**NFS** is a client-server model. One server exports a filesystem, clients mount it over the network. All metadata and data flows through a single server. Simple to operate, but the single server is both a scaling ceiling and a single point of failure.

**BeeGFS** is a parallel filesystem. Metadata and data are served by separate services, and data is striped across multiple storage targets. Clients talk directly to whichever storage server holds the data they need. This gives higher aggregate throughput but introduces more moving parts and different caching semantics.

The key architectural difference that matters most in practice: **how they handle the kernel page cache**.

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

This is a deliberate design choice. BeeGFS targets HPC multi-writer workloads where multiple nodes can write the same file concurrently. Always-invalidate guarantees coherence without per-file server-side change tracking. NFS achieves the same guarantee selectively via the `change` attribute, which lets read-only files stay cached.

### Multi-process impact on the same node

The unconditional invalidation in BeeGFS operates on the inode's `address_space`, which is shared across all processes on the same node. If process A populates the page cache by mmapping a file, then process B mmaps the same file, B's `mmap()` evicts all pages A just loaded — even though they're on the same machine reading the same unchanged file.

On NFS, process B would find A's pages still in cache (file unchanged → no invalidation) and read at memory speed.

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

Benchmarks from a production cluster: 64 compute nodes, BeeGFS across 4 storage targets with RDMA, NFS over TCP to a single server, local NVMe as baseline.

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

Cold is similar everywhere — dominated by actual file I/O. Warm diverges because:

- **NFS:** `open()` is local once the path is resolved. No per-file metadata RPC after the initial lookup is cached.
- **BeeGFS:** Every `open()` requires a metadata RPC to the server when no other process has the file open. With 23k files imported sequentially, each one pays this RPC cost.

The metadata RPC overhead interacts badly with Python's import lock — one slow file read holds the per-module lock, causing hundreds of threads to pile up on `futex` waits.

## Workload Analysis

### ML Training (load model once, checkpoint periodically)

**Winner: BeeGFS.**

Training loads the model once at job start, then the hot path is compute-bound with periodic checkpoint writes. BeeGFS gives 1.8x faster cold loads via parallel RDMA, and the lack of warm cache doesn't matter because there's only one load per job. Checkpoint writes are write-once/read-once (on resume), which plays to BeeGFS's throughput strengths.

### Inference with Model Reloads

**Winner: NFS, dramatically.**

Inference workloads that reload models frequently (e.g., swapping between models, restarting workers) benefit enormously from NFS's page cache retention. A model that takes 18s cold loads in 0.3s warm on NFS. On BeeGFS, every reload is a cold load.

### RL Training with Weight Broadcasting

**Winner: NFS.**

In reinforcement learning, a common pattern is: the trainer writes updated weights to shared storage, then multiple inference workers on each node load the same files. With tensor parallelism (e.g., TP=8), that's 8 processes per node reading the same model.

On NFS, the first worker pays the cold read cost, and the remaining 7 hit the page cache at RAM speed. Total I/O per node: 1x the model size.

On BeeGFS, each worker's `mmap()` evicts the pages the previous worker just loaded. Total I/O per node: 8x the model size, all contending for the same storage bandwidth.

| | NFS | BeeGFS |
| --- | --- | --- |
| First worker | ~18s (cold) | ~10s (cold) |
| Remaining 7 workers | ~0.3s each (page cache) | ~10s each (re-fetch) |
| Total node I/O | 1x model size | 8x model size |

### Dataset Loading (Arrow/mmap)

**Advantage: NFS for repeated epochs.**

HuggingFace datasets use Arrow format with mmap. Same invalidation rules apply — BeeGFS re-fetches every epoch, NFS retains pages if the dataset hasn't changed.

### Python Virtual Environments

**Winner: Local NVMe, then NFS.**

Heavy Python imports generate thousands of metadata lookups. BeeGFS's per-file open() RPCs make this noticeably slower. Best practice: keep virtualenvs on local NVMe (`/scratch`). If shared is required, NFS is significantly faster for this pattern.

## Workload Recommendation Summary

| Workload | Best Choice | Reason |
| --- | --- | --- |
| Model load, once per job | BeeGFS | Faster cold via parallel RDMA |
| Model load, repeated | NFS | 30x faster warm — pages retained |
| Weight broadcast (multi-process) | NFS | Page cache shared across workers |
| Checkpoints (write-once, read-once) | BeeGFS | High throughput, warm cache not needed |
| Dataset reads (repeated epochs) | NFS | Pages survive between epochs |
| Python imports / virtualenvs | Local NVMe > NFS | BeeGFS metadata RPCs amplify lock contention |

## The Takeaway

The choice isn't NFS vs BeeGFS — it's understanding which I/O paths in your workload use `mmap()` vs `read()`, how often files are re-opened, and whether multiple processes on the same node read the same data.

BeeGFS wins on raw parallel throughput for cold reads. NFS wins on anything that benefits from warm cache, which turns out to be a lot of ML workloads — especially inference and RL training patterns where the same large files are read repeatedly or by multiple processes.

If your cluster runs both workload types, the practical answer is often "both" — BeeGFS for checkpoints and cold-start training data, NFS (or local NVMe) for model serving, virtual environments, and any path that benefits from page cache retention.
