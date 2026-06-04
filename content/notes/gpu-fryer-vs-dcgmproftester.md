---
title: "gpu-fryer vs dcgmproftester: GPU Stress Testing"
date: 2026-06-04T13:52:41+0800
tags: [infra, gpu, ml-training, observability]
---

Comparing two GPU stress testing tools: HuggingFace's gpu-fryer and NVIDIA's dcgmproftester (as used in Dell's dcgmprofrunner). What they test, how they differ, and why the distinction matters for cluster health.

---

**What is dcgmprofrunner and how does it relate to dcgmproftester?**

They're two different things. `dcgmproftester` is NVIDIA's binary — it ships with DCGM (Data Center GPU Manager) and is the actual GPU stress tool. `dcgmprofrunner.sh` is Dell's bash wrapper script around it, adding Dell-specific operations: fan control via iDRAC, IPMI thermal logging, air pressure calculations, and SupportAssist TSR log collection for submission back to Dell engineering.

The stress test engine is `dcgmproftester`. dcgmprofrunner is an operational wrapper for Dell hardware acceptance and warranty processes.

---

**What does each tool actually do at the compute level?**

Both run half-precision GEMM on Tensor Cores, but with different goals:

- **gpu-fryer**: 8192×8192 cuBLAS LT matrix multiply, continuous loop. Goal is to measure and maximize sustained TFLOPS throughput. Written in Rust.
- **dcgmproftester -t 1004**: half-precision matmul targeting the `TensorEngineActive` DCGM metric. Goal is to drive tensor engine utilization to a target percentage and validate that DCGM reports it correctly. Its design goal is metric generation and validation, not raw throughput measurement.

---

**Why does that distinction matter?**

dcgmproftester was designed to answer "is DCGM's telemetry pipeline accurately reporting tensor engine activity?" — not "is this GPU performing well?" You can have a GPU reporting correct utilization metrics while being thermally throttled or running at 80% of expected throughput, and dcgmproftester won't flag it.

gpu-fryer was built to answer "is this GPU healthy for ML workloads?" — which is the question that matters for production clusters.

---

**What hardware paths does gpu-fryer exercise that dcgmproftester doesn't?**

**Full HBM address space coverage.** gpu-fryer allocates 90% of VRAM and writes results into a ring buffer of output matrices — ~576 slices on an H100 80GB. Each GEMM writes to the next slice in the ring, cycling through all ~72GB. This is an explicit design goal: saturate memory bandwidth alongside compute.

dcgmproftester's goal is generating metric load, not HBM saturation — it has no equivalent ring buffer allocation. Whether its actual working set saturates memory bandwidth is not verifiable without its source, but the intent is different.

This matters because degraded HBM stacks show up as lower bandwidth, not lower compute throughput. A tool that doesn't explicitly target HBM saturation may not catch a flaky HBM module.

**Forced HBM reads every iteration.** The A and B input matrices are 8192×8192 (128MB each in BF16) — larger than the H100's 50MB L2 cache. Every GEMM pulls A and B from HBM, not cache. This simultaneously stresses Tensor Core compute and HBM read bandwidth.

**Granular throttle classification.** gpu-fryer distinguishes three throttle reasons via NVML:
- `HW_SLOWDOWN` — hitting power/current limits, VRM or PSU issue
- `SW_THERMAL_SLOWDOWN` — driver preemptively throttling, cooling degradation
- `HW_THERMAL_SLOWDOWN` — hardware emergency, dangerously hot

It counts occurrences of each over the full run and includes them in pass/fail. dcgmproftester has no built-in throttle detection — dcgmprofrunner compensates by running `nvidia-smi` in parallel, but that only captures state at 1-second intervals without automatic aggregation into a result.

**Multiple precision paths.** gpu-fryer defaults to BF16 if all GPUs support it, otherwise FP32. FP8 and running multiple precisions simultaneously are opt-in via flags. FP8 on Hopper uses a different SM instruction path than BF16. If a specific precision unit is defective, only the matching test catches it. dcgmproftester -t 1004 is fixed to half-precision only.

---

**What about cross-GPU comparison — why does that matter for training?**

gpu-fryer finds the best-performing GPU's average TFLOPS and flags any GPU more than 10% below it. This directly catches the failure mode that kills distributed training: one GPU in a node running at 80% while the others run at 100%.

All-reduce synchronization means the entire job runs at the speed of the slowest GPU. A single degraded GPU causes a cluster-wide throughput loss equal to its degradation. In a 64-node H100 job, one GPU with a loose thermal pad quietly costs you 20% of your MFU.

dcgmproftester reports each GPU's GFLOPS independently. No comparison, no relative flag. You need to manually inspect per-GPU output files to spot the outlier.

---

**How does gpu-fryer measure performance more robustly?**

It uses Welford's online algorithm to track running mean and variance of TFLOPS:

```
delta  = flops - mean
mean  += delta / n
delta2 = flops - mean
m2    += delta * delta2
```

This gives statistically meaningful min/max/stddev across the entire run, detecting transient dips even if the GPU recovers. The first 5 ticks are skipped to exclude warm-up cache effects.

dcgmproftester reports instantaneous GFLOPS per interval. A 2-second thermal dip may not appear in the final output at all.

---

**When would you use dcgmproftester/dcgmprofrunner then?**

Dell hardware acceptance testing and warranty claims. The tool's job is to produce a standardized evidence package (CSV + TSR debug logs) for Dell's engineering team to interpret. It's a vendor qualification instrument, not an operational health tool.

For ongoing cluster health monitoring and detecting degraded GPUs in production, gpu-fryer is the right tool — it's self-contained, hardware-agnostic, Docker-friendly, and gives you an immediate relative pass/fail.
