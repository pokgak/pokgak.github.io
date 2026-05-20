---
title: "Supercomputing Skills to Learn"
date: 2026-05-20T15:37:26+0800
tags: [infrastructure, distributed-systems, ml, learning]
---

Skills and knowledge areas worth investing in for GPU supercomputing and large-scale ML infrastructure work.

## Core Systems

- **Linux internals** — process management, memory, filesystems, kernel tuning for high-throughput workloads
- **Networking** — TCP/IP, RDMA, InfiniBand, NVLink; understanding how interconnects affect distributed training bandwidth
- **Infrastructure as Code** — Terraform, Ansible, or similar for repeatable cluster provisioning

## Cluster Orchestration

- **Kubernetes** — workload scheduling, resource management, custom operators; topology-aware placement for GPU pods
- **Slurm** — how HPC schedulers work, job queues, multi-tenant fairness policies
- **Cluster provisioning** — imaging nodes, capacity planning, lifecycle management at scale

## GPU and Distributed Training

- **CUDA** — GPU memory model, kernel execution, profiling; understanding where bottlenecks come from
- **NCCL** — collective communication primitives (AllReduce, AllGather); how they map to ring/tree topologies
- **Distributed training** — data parallelism, tensor parallelism, pipeline parallelism; how frameworks implement them
- **PyTorch distributed** — `torch.distributed`, FSDP, DeepSpeed; practical experience running multi-node jobs

## Storage

- **Parallel filesystems** — Lustre, GPFS, or NFS at scale; tuning for checkpoint writes and dataset reads
- **Object storage** — S3-compatible systems for dataset and artifact management
- **Retention and tiering** — how to manage large volumes of checkpoints without blowing up storage costs

## Observability

- **GPU metrics** — DCGM, nvidia-smi, understanding utilization vs. memory-bound bottlenecks
- **Distributed tracing** — correlating slowdowns across nodes in a training run
- **Alerting and SLOs** — defining and acting on reliability targets for training infrastructure

## Language Depth

- **Python** — async I/O, C extensions, profiling; writing performance-sensitive control-plane code
- **Rust** — memory safety, async with Tokio, FFI to C; useful for low-latency infrastructure tooling

## What to Prioritize

Start with Kubernetes and distributed training fundamentals — they're the intersection of most of the above. Then go deeper on CUDA/NCCL once you have enough context to understand why the low-level primitives matter.
