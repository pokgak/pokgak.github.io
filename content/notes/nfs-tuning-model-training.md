---
title: "NFS Tuning for Model Training Workloads"
date: 2026-04-15T11:23:23+0800
tags: [infra, ml-training, nfs, storage]
---

NFS is common in GPU clusters for shared storage — `/home`, checkpoints, training data. At scale (100+ nodes), the defaults fall apart. Here's what matters.

## The Workload Profile

Large model training has two distinct I/O phases:

**Steady-state (between checkpoints)**
- Mostly reads: training data, tokenized datasets
- Light writes: logs and metrics from rank 0
- Read throughput per node is modest; aggregate across many nodes is high
- Step time is compute-bound; NFS is not the bottleneck

**Checkpoint saves (periodic, e.g. every 500 steps)**
- All nodes write simultaneously — a fan-in write burst to a single server
- Step time can spike 5–10× during a checkpoint save
- GPU compute sits idle waiting on I/O — MFU drops from ~43% to ~6%
- Server iowait spikes, then drops back to near-zero between checkpoints

This asymmetry — mostly reads with periodic synchronized write bursts — should drive all your tuning decisions.

## Challenges

- **Fan-in writes**: 100+ nodes checkpointing at the same step means the server gets hit simultaneously. Without coalescing, each node's write becomes a separate fsync under `sync` semantics — hundreds of sequential disk flushes.
- **Single TCP connection per mount**: default NFS uses one connection per client. At high concurrency each node serializes its own RPCs even if the server has headroom.
- **Reconnect overhead**: idle connections expire between steps. For training data reads, reconnect latency shows up as microstalls before each step.
- **Readdir round-trips**: loading training datasets involves many directory listings. Without prefetching file attributes, each entry requires a follow-up GETATTR call.
- **Disk space**: checkpoints accumulate fast. An 82% full server is a ticking clock; NFS writes will start failing when it fills.

## Mount Options Worth Tuning

**`nconnect=N`** — open N parallel TCP connections per mount. This is the single highest-leverage client-side option. Critical for checkpoint writes where a single connection serializes all writes from one node. But be careful scaling this up: with 100+ nodes each opening 16 connections, the server can end up handling thousands of simultaneous connections, driving interrupt load high enough to cause connection issues. Start at 4–8 and increase only if you've confirmed the server can handle the aggregate connection count.

**`rsize`/`wsize`** — transfer size per RPC. Match to your actual access pattern. Large values (512K–1M) reduce RPC count for sequential bulk reads and writes — good for checkpoint saves and large dataset reads. But for workloads that mostly read small random files (e.g. 8K–16K per file), large rsize/wsize wastes bandwidth and increases latency — you pay to transfer a large block but only need a small one. When in doubt, measure; don't default to 1M.

**`noatime`** — skip access-time updates on reads. Eliminates spurious write RPCs during training data reads.

**`hard` mount** — for checkpoint storage, always use `hard`. A soft mount will return EIO if the server is temporarily overwhelmed by the burst; hard mounts block and retry, preserving checkpoint integrity.

**`timeo` / `retrans`** — tune retry behavior. High `timeo` (e.g. 600 × 0.1s = 60s) avoids premature timeouts during checkpoint bursts.

**`noidlexprt`** — keeps server-side connection state alive even when idle. Avoids reconnect overhead between training steps on data mounts.

**`forcerdirplus`** — fetches file attributes alongside directory entries. Reduces round trips for readdir-heavy access patterns (loading many small files from a directory).

**`spread_reads` / `spread_writes`** (Linux NFS client, for multi-homed servers) — distributes I/O across multiple server IPs/ports. Useful when the server has multiple network interfaces.

## Server Export Options Worth Tuning

**`wdelay`** — the most important option for checkpoint workloads. When multiple clients write simultaneously, the server detects the concurrent in-flight writes and coalesces them into a single disk flush instead of one fsync per client. Without this, `sync` semantics under a 100-node checkpoint burst means hundreds of sequential disk flushes.

**`sync`** — flushed writes before ACK. Data-safe but slower. Combined with `wdelay`, you get safety without the per-client fsync overhead.

**`no_subtree_check`** — removes per-RPC overhead where the server validates that the requested file is within the exported subtree. At thousands of RPC/s across many nodes, this adds up. Safe when exporting a full filesystem.

**`no_root_squash`** — if training processes run as root inside containers, squashing root to nobody will cause permission errors. Set carefully.

**NFS thread count** (`/proc/fs/nfsd/threads`) — increase from the default (often 8 or 16) to 64–256 on servers handling many clients. Monitor the `th` field in `nfsstat -s` or `/proc/net/rpc/nfsd` — if threads are consistently maxed out, increase.

## How to Monitor

**Client-side**
```bash
# RPC retransmissions — should be 0; any retransmits = server pressure or network loss
cat /proc/net/rpc/nfs
# Fields: calls retrans authrefrsh ... (retrans is column 3)

# Per-mount stats
mount | grep nfs
nfsstat -c
```

**Server-side**
```bash
# NFS RPC stats — check thread utilization, error counters
cat /proc/net/rpc/nfsd
nfsstat -s

# Disk iowait — should spike during checkpoints, not during steady state
iostat -x 2

# Disk space — checkpoints accumulate
df -h
```

**Prometheus / node_exporter metrics** (if available)
- `node_nfsd_disk_bytes_read_total` / `node_nfsd_disk_bytes_written_total` — server throughput
- `node_nfsd_server_rpcs_total` — aggregate RPC rate
- `node_disk_io_time_seconds_total` on the server — iowait proxy
- Plot these alongside step time to see checkpoint I/O spikes directly

Key things to watch:
- RPC error rate: should be 0
- Client retransmissions: should be 0
- Server iowait: periodic spikes OK; sustained high iowait means the server is bottlenecked
- NFS thread queue depth: if threads are waiting, add threads or reduce clients per server

## How to Verify Improvements

- Compare step time distribution before and after: checkpoint-step spikes should narrow
- Compare checkpoint wall time specifically: time from step N start to step N+1 start during a save
- Watch server iowait during checkpoints: wdelay coalescing shows up as shorter, sharper spikes vs. sustained high iowait
- Client retransmissions should stay 0 after tuning; any non-zero value means the server is still overloaded
- MFU (model FLOPs utilization) rolling average should improve slightly as checkpoint overhead shrinks relative to compute steps

## Rough Ordering of Impact

1. `wdelay` on server export — addresses the core fan-in problem
2. `nconnect=8+` on client — removes per-node TCP bottleneck
3. `hard` mount for checkpoints — correctness, not performance
4. `rsize`/`wsize=1M` — straightforward throughput for bulk I/O
5. `noatime` — eliminates spurious writes, minor but free
6. NFS thread count — only matters once threads are saturated
