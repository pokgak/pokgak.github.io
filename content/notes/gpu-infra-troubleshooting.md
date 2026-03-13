---
title: "GPU Infrastructure Troubleshooting"
date: 2026-02-26T00:00:00+0800
tags: [gpu, infrastructure, networking, nccl, infiniband, troubleshooting]
---

Runbooks and diagnostic procedures for GPU cluster performance issues.

## Node-Level: IOMMU, ACS, PCIe

### IOMMU

IOMMU sits between PCIe devices and system memory, translating device-virtual addresses to physical addresses. Every DMA transaction goes through this translation.

```
Normal:    GPU --[DMA]--> Physical Memory
With IOMMU: GPU --[DMA]--> IOMMU --[translate IOVA->PA]--> Physical Memory
```

Impact: **2x-10x degradation** in AllReduce bandwidth due to IOTLB thrashing, ACS routing penalty, and GPUDirect RDMA overhead.

#### How to Check

**1. IOMMU groups count (most reliable)**
```bash
ls /sys/kernel/iommu_groups/ | wc -l
```
- `0` = disabled (good)
- `> 0` = active (bad for GPU perf)

**2. IOMMU domain type**
```bash
cat /sys/kernel/iommu_groups/*/type 2>/dev/null | sort | uniq -c
```
- `DMA-FQ` or `DMA` = full translation (worst)
- `identity` = passthrough (less bad)

**3. Kernel command line**
```bash
cat /proc/cmdline | tr ' ' '\n' | grep -i iommu
```

**4. Per-GPU IOMMU status**
```bash
for gpu in $(lspci -d 10de: -D | awk '{print $1}'); do
    group=$(readlink /sys/bus/pci/devices/$gpu/iommu_group 2>/dev/null | xargs basename 2>/dev/null)
    if [ -n "$group" ]; then
        dtype=$(cat /sys/kernel/iommu_groups/$group/type 2>/dev/null)
        echo "$gpu -> IOMMU group $group ($dtype) $(lspci -s $gpu)"
    fi
done
```

#### Fix: Disable IOMMU

**Option 1: Kernel boot parameter (preferred)**
```bash
# Intel:
GRUB_CMDLINE_LINUX="intel_iommu=off"
# AMD:
GRUB_CMDLINE_LINUX="amd_iommu=off"
sudo update-grub && sudo reboot
```

**Option 2: Passthrough mode (if IOMMU must stay on)**
```bash
# Intel:
GRUB_CMDLINE_LINUX="intel_iommu=on iommu=pt"
# AMD:
GRUB_CMDLINE_LINUX="amd_iommu=on iommu=pt"
```

**Option 3: BIOS** — Disable VT-d (Intel) or AMD-Vi (AMD). Most thorough but requires physical/IPMI access.

#### Real-world case: H200 cluster, PXE-booted

Nodes were PXE-booted. Initial image shipped without `intel_iommu=on iommu=pt` — NCCL all-reduce busbw was capped at ~98-101 GB/s on large messages (target: ~180 GB/s algbw / ~337 GB/s busbw for 16-GPU).

After the PXE boot image was updated with the following params:

```
intel_iommu=on iommu=pt iomem=relaxed pci=bfsort,realloc=off rd.driver.blacklist=nouveau
```

busbw jumped from ~103 GB/s → ~484 GB/s — exceeding the original target. `iommu=pt` (passthrough mode) was the key change enabling GPUDirect RDMA to bypass the CPU.

> **Note for PXE-booted clusters:** kernel params are set by the provisioning server, not `/etc/default/grub`. To check boot history, use `sudo journalctl -b -N -k | grep "Command line:"` across boots (`-b -1`, `-b -2`, etc.).

### ACS (Access Control Services)

ACS controls whether P2P traffic passes through a PCIe switch directly or must route up to the root complex first.

```
Normal:   GPU0 --[PCIe switch]--> GPU1         (direct)
With ACS: GPU0 --[up to root complex]--> GPU1  (detour)
```

ACS is often **auto-enabled by the kernel when IOMMU is active**. IOMMU has a double penalty: translation overhead + ACS forcing suboptimal routing.

#### How to Check

```bash
echo "ACS devices total: $(sudo lspci -vvv 2>/dev/null | grep -c 'ACSCtl:')"
echo "ACS with SrcValid+: $(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'SrcValid+')"
echo "ACS with ReqRedir+: $(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'ReqRedir+')"
echo "ACS all bits off: $(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'SrcValid- TransBlk- ReqRedir- CmpltRedir- UpstreamFwd- EgressCtrl- DirectTrans-')"
```

Key bits: `ReqRedir+` is the perf killer — forces all P2P through root complex.

**Quick fleet check:**
```bash
echo "$(hostname): acs_redir=$(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'ReqRedir+')"
```

#### Fix: Disable ACS

```bash
for BDF in $(lspci -d '*:*' | awk '{print $1}'); do
    sudo setpci -s $BDF ECAP_ACS+6.w=0000 2>/dev/null
done
```

### PPCIe (Protected PCIe)

Part of NVIDIA's Confidential Computing stack. Encrypts data on the PCIe bus between GPU/NVSwitch and host memory. Some cloud providers ship nodes with this enabled by default.

- **Intra-node**: Minimal impact (NVLink bypasses PCIe)
- **Inter-node**: Overhead on PCIe segments in the `GPU -> NVSwitch -> PCIe -> NIC` path

#### Fix: Disable PPCIe

Uses [NVIDIA gpu-admin-tools](https://github.com/NVIDIA/gpu-admin-tools):

```bash
python3 ~/gpu-admin-tools/nvidia_gpu_tools.py --devices gpus --set-ppcie-mode=off --reset-after-ppcie-mode-switch
python3 ~/gpu-admin-tools/nvidia_gpu_tools.py --devices nvswitches --set-ppcie-mode=off --reset-after-ppcie-mode-switch
reboot
```

### Fleet Diagnostics

```bash
# With ansible
ansible compute -i inventory.ini -m shell -a \
  'echo "$(hostname): iommu_groups=$(ls /sys/kernel/iommu_groups/ 2>/dev/null | wc -l) acs_redir=$(sudo lspci -vvv 2>/dev/null | grep ACSCtl: | grep -c ReqRedir+)"'

# With pssh
pssh -h hosts.txt -i \
  'echo "$(hostname): iommu_groups=$(ls /sys/kernel/iommu_groups/ 2>/dev/null | wc -l) acs_redir=$(sudo lspci -vvv 2>/dev/null | grep ACSCtl: | grep -c ReqRedir+)"'
```

### Post-fix Verification

```bash
dmesg | grep -i iommu
ls /sys/kernel/iommu_groups/
nvidia-smi topo -p2p r
nccl-tests/build/all_reduce_perf -b 8 -e 256M -f 2 -g 8
```

### Recommended Settings for H100/H200 Clusters

| Setting | Value | How |
|---------|-------|-----|
| IOMMU (BIOS) | Disabled | BIOS > VT-d/AMD-Vi > Disabled |
| IOMMU (kernel) | `intel_iommu=off` or `amd_iommu=off` | `/etc/default/grub` |
| PCIe ACS | Disabled on GPU bridges | `setpci` or BIOS |
| PPCIe mode | Disabled (off) | `nvidia_gpu_tools.py --set-ppcie-mode=off` on GPUs + NVSwitches |
| nvidia-peermem | Loaded | `modprobe nvidia-peermem` |
| Persistence mode | Enabled | `nvidia-smi -pm 1` |

---

## Node-Level: Pre-Job Health Checks

Systematic verification before launching workloads. Can be scripted into Slurm prolog or run manually after node maintenance.

### Quick Checklist

```bash
# 1. Driver and modules loaded
nvidia-smi > /dev/null && echo "driver: ok" || echo "driver: MISSING"
lsmod | grep -q nvidia_peermem && echo "peermem: ok" || echo "peermem: MISSING"
lsmod | grep -q gdrdrv && echo "gdrdrv: ok" || echo "gdrdrv: MISSING (optional)"

# 2. Persistence mode on
nvidia-smi -q -d PERFORMANCE | grep -i "Persistence" | head -1

# 3. Fabric Manager running (HGX/NVSwitch systems)
systemctl is-active nvidia-fabricmanager

# 4. GPU count matches expected
echo "GPUs: $(nvidia-smi -L | wc -l)"

# 5. PCIe link speed (should be Gen5 x16 for H100/H200)
nvidia-smi -q -d PERFORMANCE | grep -E "Link (Gen|Width)"

# 6. NVLink topology healthy
nvidia-smi nvlink -s

# 7. Recent XID errors (last boot)
dmesg | grep -i "Xid" | tail -5 || echo "clean"

# 8. ECC errors and page retirement
nvidia-smi -q -d ECC | grep -E "Uncorrected|Corrected" | grep -v ": 0"
nvidia-smi -q -d PAGE_RETIREMENT | grep -E "Pending|Cause"

# 9. DCGM quick diagnostic
dcgmi diag -r 2
```

### DCGM Diagnostic Levels

`dcgmi diag` runs progressively deeper GPU health checks. GPUs must be idle (no running workloads).

| Level | Command | Duration | Tests |
|-------|---------|----------|-------|
| 1 (quick) | `dcgmi diag -r 1` | ~seconds | Deployment checks: driver loaded, NVML working, persistence mode, GPU count, permissions |
| 2 (medium) | `dcgmi diag -r 2` | ~2 min | Level 1 + PCIe bandwidth, targeted stress, targeted power. Catches degraded PCIe links and GPUs that fail under load |
| 3 (long) | `dcgmi diag -r 3` | ~15 min | Level 2 + full GPU memory scan (memtest), diagnostic plugin. Catches intermittent memory errors |

**Level 2 is the sweet spot for pre-job checks** — fast enough to run in a Slurm prolog, thorough enough to catch most hardware issues before they waste job runtime. Level 3 is for post-maintenance validation or investigating suspected hardware issues.

Example Slurm prolog snippet:
```bash
#!/bin/bash
dcgmi diag -r 2 > /tmp/dcgm-prolog-$(hostname).log 2>&1
if [ $? -ne 0 ]; then
    scontrol update nodename=$(hostname) state=drain reason="dcgmi diag failed"
    exit 1
fi
```

### Fleet-wide pre-job check

```bash
ansible compute -i inventory.ini --become -m shell -a \
  'nvidia-smi > /dev/null && echo "driver: ok" || echo "driver: MISSING"; \
   echo "GPUs: $(nvidia-smi -L | wc -l)"; \
   echo "peermem: $(lsmod | grep -q nvidia_peermem && echo ok || echo MISSING)"; \
   echo "fabmgr: $(systemctl is-active nvidia-fabricmanager)"; \
   echo "XIDs: $(dmesg | grep -ci Xid)"'
```

---

## Node-Level: Proactive Monitoring

Key metrics to collect continuously (via DCGM, Prometheus `dcgm-exporter`, or custom scripts).

| Metric | Source | Why |
|--------|--------|-----|
| GPU temperature | `nvidia-smi -q -d TEMPERATURE` | Thermal throttling degrades perf silently |
| Memory temperature | DCGM `DCGM_FI_DEV_MEMORY_TEMP` | HBM throttles independently from GPU die |
| Power draw | `nvidia-smi -q -d POWER` | Hitting power cap = clock throttling |
| Clock speeds (SM, Mem) | `nvidia-smi -q -d CLOCK` | Lower than max = throttling active |
| ECC error counts | `nvidia-smi -q -d ECC` | Rising corrected errors = failing memory |
| NVLink error counters | `nvidia-smi nvlink -e` | Link degradation before failure |
| PCIe replay count | DCGM `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | Rising = signal integrity issue |
| XID error count | DCGM `DCGM_EXP_XID_ERRORS_COUNT` | Alert on any XID >= 48 |

---

## Fabric-Level: InfiniBand Diagnostics

### IB PHY Error Monitoring

#### Metrics

- **ethtool counters**: `rx_err_lane_*_phy` (per-lane physical layer errors on IB interfaces)
- Exposed via Grafana Alloy's **ethtool collector** as `node_net_ethtool_received_err_lane_*_phy`
- Query error rate with Prometheus `rate()` over these counters
- Manual CLI check: `ethtool -S <ib_interface> | grep rx_err_lane`

#### Heuristics

IB uses FEC (Forward Error Correction) to silently correct physical layer errors. At high rates, FEC gets overwhelmed and link-level retransmissions occur, adding latency to NCCL collectives.

| Tier | Threshold | Interpretation |
|------|-----------|----------------|
| Critical | >1M err/s | Likely causing retransmissions |
| High | 300K-1M err/s | Possible tail latency |
| Moderate | 100K-300K err/s | FEC handles it |
| Normal | <100K err/s | Baseline |

Thresholds are heuristic based on:
- Statistical outliers vs cluster median
- Correlation with observed issues (NCCL hangs, XID errors on high-error nodes)
- Natural gaps in the data distribution

#### Better signal: actual retransmissions

`port_rcv_remote_physical_errors` from `perfquery` counts cases where FEC **failed** to correct — these are actual retransmissions and a more direct indicator of link degradation than raw PHY error rates.

```bash
# Check IB PHY error counters
ethtool -S <ib_interface> | grep rx_err_lane

# Check retransmission counters (more direct signal)
perfquery -x <lid> | grep RcvRemotePhysErrors
```

### ib_write_bw vs ibdiagnet

These test fundamentally different things. Understanding the difference prevents being fooled by "all links look healthy" when collective performance is degraded.

| | ib_write_bw | ibdiagnet |
|---|---|---|
| **What it does** | RDMA write throughput between 2 nodes | Fabric-wide topology discovery + hardware counter analysis |
| **Plane** | Data plane — sends actual data | Management plane — reads switch/HCA registers via SMP/GMP |
| **Scope** | One HCA pair at a time | Every port on every switch and HCA in the fabric |
| **Detects** | Link throughput (GB/s) | BER, port errors, cabling mistakes, firmware mismatches, topology issues |
| **Limitation** | High-BER link still shows full line rate (retransmissions transparent on single stream) | Doesn't measure actual data throughput |

**Key insight:** A link with BER 6e-08 (6 orders of magnitude above threshold) still shows 396 Gb/s on `ib_write_bw` because the hardware retransmits corrupted packets transparently for a single stream. Under collective load with thousands of concurrent flows, every retransmission cascades into congestion. **Always run ibdiagnet even if point-to-point bandwidth looks healthy.**

### ibdiagnet

Fabric-wide diagnostic tool from Mellanox/NVIDIA. Discovers the entire IB fabric topology via Subnet Manager queries, reads hardware counters from every switch and HCA, and compares against known-good baselines.

#### Running ibdiagnet

```bash
ibdiagnet -i mlx5_0 -r --ft --ber_test --rail_validation -sc \
  --pm_pause_time 60 -P all=1 --extended_speeds all \
  --pm_per_lane --get_phy_info --get_cable_info --get_p_info \
  --cable_info_disconnected
```

| Flag | What it checks |
|------|---------------|
| `-i mlx5_0` | Start fabric discovery from this HCA port |
| `-r` | Include routing information |
| `--ber_test` | Bit Error Rate testing — catches degraded links before they fail |
| `--rail_validation` | Verify rail-optimized cabling matches expected topology |
| `-sc` | Subnet configuration checks |
| `--pm_pause_time 60` | Collect performance counters over 60s window to detect error accumulation |
| `-P all=1` | Reset all port counters first for clean delta measurement |
| `--extended_speeds all` | Validate all NDR-speed links |
| `--pm_per_lane` | Per-lane stats — catches single-lane degradation within a multi-lane link |
| `--get_phy_info` | Physical layer info (signal quality, eye opening) |
| `--get_cable_info` | Cable type, vendor, length, temperature |

#### What ibdiagnet Catches That Point-to-Point Tests Miss

**1. Bit Error Rate (BER) on links**

Links with high BER still pass throughput tests because the hardware retransmits transparently. ibdiagnet reads the BER counter directly from the HCA firmware.

- Threshold: **1e-14** (acceptable)
- Example bad value: **6e-08** (6 orders of magnitude above threshold)
- Fix: reseat or replace the cable

**2. Port counter errors**

Cumulative counters like `port_rcv_remote_physical_errors` that increment over time. The `--pm_pause_time 60` flag with `-P all=1` resets counters first, then measures the delta — catching actively degrading ports.

**3. Rail cabling mismatches**

In a rail-optimized fat-tree, GPU N on every node should connect to the same leaf switch (rail N). `--rail_validation` compares actual wiring against expected topology. Mismatches break NCCL's topology-aware algorithms (PXN, rail-local routing).

**4. Firmware inconsistencies**

Detects mixed firmware versions across the fabric. Mismatched firmware between HCAs or switches can cause subtle interop issues under load.

**5. Uneven leaf switch downlinks**

Reports actual vs expected host port counts per leaf, revealing asymmetric fabric capacity.

#### Output Location

ibdiagnet writes results to `/var/tmp/ibdiagnet2/` by default:
- `ibdiagnet2.log` — full diagnostic log
- `ibdiagnet2.db_csv` — topology database
- `ibdiagnet2.pm` — performance counter data

### mlxlink

Per-port diagnostic tool that reads directly from the HCA firmware. Catches signal integrity issues that ibdiagnet may miss.

#### mlxlink vs ibdiagnet

| | mlxlink | ibdiagnet |
|---|---|---|
| **Scope** | Single HCA port | Entire fabric |
| **Error counters** | Cumulative since last reset/reboot | Delta over `--pm_pause_time` window |
| **Sensitivity** | Shows pre-FEC physical errors (more sensitive) | Checks post-FEC symbol BER against threshold |
| **Diagnosis** | Provides `Recommendation` (e.g., "Bad signal integrity") | Reports pass/fail against thresholds |
| **Counter reset** | `mlxlink --pc` (clear port counters) | `-P all=1` (reset before measurement) |

**Key insight:** A port accumulating ~600 pre-FEC errors/second will be caught by mlxlink but may pass ibdiagnet's BER check — FEC corrects the errors at the physical layer, so the post-FEC symbol BER stays below ibdiagnet's 1e-14 threshold in the 60s window. **Always run mlxlink alongside ibdiagnet for signal quality checks.**

#### When to use which

- **ibdiagnet**: first pass, fabric-wide health check. Catches topology issues, rail mismatches, firmware mismatches, and ports with high post-FEC BER
- **mlxlink**: targeted follow-up on suspect nodes, or sweep all nodes to catch pre-FEC degradation that ibdiagnet misses
- **Both together**: after datacenter fixes, to verify repairs. ibdiagnet for fabric-level, mlxlink for per-port signal quality

#### Running mlxlink across a cluster

```bash
ansible compute -i inventory.ini -m shell -a \
  "lspci -nn | grep ConnectX-7 | awk '{print \$1}' | while read bus_id; do
    echo \$bus_id; mlxlink -d \${bus_id} -c 2>/dev/null | grep 'Effective';
  done" --become
```

#### Interpreting Effective Physical Errors

These are cumulative pre-FEC errors since last counter reset. What matters is whether they're **actively increasing**, not the absolute number.

| BER | Severity | Action |
|-----|----------|--------|
| 0 or 15E-255 | Clean | No action |
| 1E-17 to 1E-15 | Normal | Low-level noise, monitor |
| 1E-15 to 1E-13 | Elevated | Monitor, check if actively increasing |
| 1E-13 to 1E-10 | Bad | Verify if stale or active; schedule cable check |
| >= 1E-10 | Critical | Likely active; verify and escalate for cable replacement |

**To verify if errors are active vs stale:**
```bash
# Clear counters
mlxlink -d <bus_id> --pc

# Wait some time, then check
mlxlink -d <bus_id> -c | grep "Effective Physical Errors"
```

If errors resume immediately after clearing, the port has an active signal integrity issue. If they stay at 0, the errors were historical (e.g., from before a cable fix) and counters just hadn't been reset.

#### mlxlink troubleshooting flags

| Flag | Purpose |
|------|---------|
| `-c` | Cable/link info + effective BER |
| `-e` | Extended error counters |
| `-c -e` | Both — full picture |
| `--pc` | Clear port counters (reset to 0) |
| `--port_type PCIE` | Check PCIe link instead of IB |

#### Diagnostic output to look for

```
Troubleshooting Info
--------------------
Status Opcode   : 15
Group Opcode    : PHY FW
Recommendation  : Bad signal integrity
```

When mlxlink shows `Bad signal integrity`, the firmware itself has diagnosed a hardware problem — cable or transceiver needs replacement.

---

## Troubleshooting Checklist: Cross-Switch Performance Degradation

When NCCL collective performance degrades at scale but point-to-point looks fine:

**1. Confirm the problem is cross-switch**

Run the same NCCL test on nodes within a single switch unit vs across switch units. If same-SU gets full bandwidth but cross-SU degrades, the problem is in the spine/fabric.

```bash
# Same-SU baseline (should get full bandwidth)
mpirun --hostfile /tmp/hostfile-same-su ... all_reduce_perf -b 1G -e 8G -f 2 -g 1

# Cross-SU test (if this degrades, spine is the problem)
mpirun --hostfile /tmp/hostfile-cross-su ... all_reduce_perf -b 1G -e 8G -f 2 -g 1
```

**2. Run pairwise NCCL tests to find outlier nodes**

Test each suspect node paired with a known-good node. Outliers with significantly lower bandwidth need further investigation.

**3. Run ib_write_bw per-HCA to verify link-level health**

```bash
# Server side
ib_write_bw -d mlx5_0 --report_gbits -D 10

# Client side
ib_write_bw -d mlx5_0 --report_gbits -D 10 <server_ip>
```

Repeat for all 8 IB HCAs (mlx5_0 through mlx5_11). All should hit line rate (~396 Gb/s for NDR).

**4. Run mlxlink sweep across all nodes**

Catches pre-FEC signal degradation that ibdiagnet may miss. Run this before ibdiagnet — it's faster and per-node.

**5. Run ibdiagnet for fabric-wide diagnostics**

This catches topology, routing, and switch-level issues that per-node mlxlink can't see. Use the full command above.

Check the output for:
- [ ] BER above threshold (1e-14) on any link
- [ ] Port counter errors incrementing during the test window
- [ ] Rail validation failures (nodes on wrong rails)
- [ ] Firmware version mismatches across HCAs and switches
- [ ] Uneven downlink counts on leaf switches

**6. Check for SHARP availability**

```bash
sharp_hello
```

If it fails with "Failed to connect to Aggregation Manager", SHARP is not enabled. SHARP does in-network reductions on switches, which can bypass spine congestion for collective operations.

**7. Try NCCL algorithm tuning as a workaround**

```bash
NCCL_ALGO=Tree mpirun ... all_reduce_perf -b 1G -e 8G -f 2 -g 1
```

Tree algorithm often works better on congested fabrics (~24% improvement observed in cross-SU tests).

**8. Escalate to provider with evidence**

Collect artifacts before escalating:

```bash
# GPU/driver bug report
sudo nvidia-bug-report.sh

# Fabric Manager logs (HGX/NVSwitch systems)
journalctl -u nvidia-fabricmanager --since "24 hours ago" > fabmgr.log

# DCGM diagnostics
dcgmi diag -r 3 2>&1 | tee dcgm-diag-r3.log

# ibdiagnet output
ls /var/tmp/ibdiagnet2/
```

Send to provider:
- `nvidia-bug-report.log.gz` — driver state, GPU info, dmesg, XID history
- Fabric Manager logs (if NVSwitch system)
- ibdiagnet output files (`/var/tmp/ibdiagnet2/`)
- Same-SU vs cross-SU NCCL results showing the gap
- Specific BER values, port errors, rail mismatches
- DCGM diag results if GPU hardware is suspect
