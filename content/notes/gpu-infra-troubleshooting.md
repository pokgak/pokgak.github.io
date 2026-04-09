---
title: "GPU Infrastructure Troubleshooting"
date: 2026-02-26T00:00:00+0800
tags: [gpu, infrastructure, networking, nccl, infiniband, troubleshooting]
---

Runbooks and diagnostic procedures for GPU cluster performance issues.

## Node-Level: IOMMU, ACS, PCIe

### IOMMU

Sits between PCIe devices and system memory, translating device-virtual to physical addresses. Every DMA transaction goes through translation.

```
Normal:    GPU --[DMA]--> Physical Memory
With IOMMU: GPU --[DMA]--> IOMMU --[translate IOVA->PA]--> Physical Memory
```

**Impact:** 2x-10x degradation in AllReduce bandwidth (IOTLB thrashing, ACS routing penalty, GPUDirect RDMA overhead).

#### How to Check

**1. IOMMU groups count (most reliable)**
```bash
ls /sys/kernel/iommu_groups/ | wc -l
# 0 = disabled (good), > 0 = active (bad for GPU perf)
```

**2. IOMMU domain type**
```bash
cat /sys/kernel/iommu_groups/*/type 2>/dev/null | sort | uniq -c
# DMA-FQ or DMA = full translation (worst), identity = passthrough (less bad)
```

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

- PXE-booted nodes missing `intel_iommu=on iommu=pt`
- NCCL all-reduce busbw capped at ~98-101 GB/s (target: ~180 GB/s algbw / ~337 GB/s busbw for 16-GPU)
- After adding `intel_iommu=on iommu=pt iomem=relaxed pci=bfsort,realloc=off rd.driver.blacklist=nouveau`:
- busbw jumped ~103 GB/s -> ~484 GB/s
- `iommu=pt` (passthrough mode) was the key change enabling GPUDirect RDMA to bypass CPU

> **PXE-booted clusters:** kernel params set by provisioning server, not `/etc/default/grub`. Check boot history: `sudo journalctl -b -N -k | grep "Command line:"` across boots.

### ACS (Access Control Services)

Controls whether P2P traffic passes through PCIe switch directly or routes up to root complex.

```
Normal:   GPU0 --[PCIe switch]--> GPU1         (direct)
With ACS: GPU0 --[up to root complex]--> GPU1  (detour)
```

Often auto-enabled by kernel when IOMMU is active — IOMMU has double penalty: translation overhead + ACS forcing suboptimal routing.

#### How to Check

```bash
echo "ACS devices total: $(sudo lspci -vvv 2>/dev/null | grep -c 'ACSCtl:')"
echo "ACS with SrcValid+: $(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'SrcValid+')"
echo "ACS with ReqRedir+: $(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'ReqRedir+')"
echo "ACS all bits off: $(sudo lspci -vvv 2>/dev/null | grep 'ACSCtl:' | grep -c 'SrcValid- TransBlk- ReqRedir- CmpltRedir- UpstreamFwd- EgressCtrl- DirectTrans-')"
```

Key: `ReqRedir+` is the perf killer — forces all P2P through root complex.

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

Part of NVIDIA's Confidential Computing stack. Encrypts data on PCIe bus. Some cloud providers enable by default.

- **Intra-node:** Minimal impact (NVLink bypasses PCIe)
- **Inter-node:** Overhead on PCIe segments in `GPU -> NVSwitch -> PCIe -> NIC` path

#### Fix: Disable PPCIe

Uses [NVIDIA gpu-admin-tools](https://github.com/NVIDIA/gpu-admin-tools):

```bash
python3 ~/gpu-admin-tools/nvidia_gpu_tools.py --devices gpus --set-ppcie-mode=off --reset-after-ppcie-mode-switch
python3 ~/gpu-admin-tools/nvidia_gpu_tools.py --devices nvswitches --set-ppcie-mode=off --reset-after-ppcie-mode-switch
reboot
```

### Fleet Diagnostics

```bash
# Ansible
ansible compute -i inventory.ini -m shell -a \
  'echo "$(hostname): iommu_groups=$(ls /sys/kernel/iommu_groups/ 2>/dev/null | wc -l) acs_redir=$(sudo lspci -vvv 2>/dev/null | grep ACSCtl: | grep -c ReqRedir+)"'

# pssh
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

Systematic verification before launching workloads. Can be scripted into Slurm prolog.

### Quick Checklist

```bash
# 1. Driver and modules
nvidia-smi > /dev/null && echo "driver: ok" || echo "driver: MISSING"
lsmod | grep -q nvidia_peermem && echo "peermem: ok" || echo "peermem: MISSING"
lsmod | grep -q gdrdrv && echo "gdrdrv: ok" || echo "gdrdrv: MISSING (optional)"

# 2. Persistence mode
nvidia-smi -q -d PERFORMANCE | grep -i "Persistence" | head -1

# 3. Fabric Manager (HGX/NVSwitch)
systemctl is-active nvidia-fabricmanager

# 4. GPU count
echo "GPUs: $(nvidia-smi -L | wc -l)"

# 5. PCIe link speed (Gen5 x16 for H100/H200)
nvidia-smi -q -d PERFORMANCE | grep -E "Link (Gen|Width)"

# 6. NVLink topology
nvidia-smi nvlink -s

# 7. Recent XID errors
dmesg | grep -i "Xid" | tail -5 || echo "clean"

# 8. ECC errors and page retirement
nvidia-smi -q -d ECC | grep -E "Uncorrected|Corrected" | grep -v ": 0"
nvidia-smi -q -d PAGE_RETIREMENT | grep -E "Pending|Cause"

# 9. DCGM diagnostic
dcgmi diag -r 2
```

### DCGM Diagnostic Levels

GPUs must be idle.

| Level | Command | Duration | Tests |
|-------|---------|----------|-------|
| 1 (quick) | `dcgmi diag -r 1` | ~seconds | Deployment: driver, NVML, persistence mode, GPU count, permissions |
| 2 (medium) | `dcgmi diag -r 2` | ~2 min | Level 1 + PCIe bandwidth, targeted stress/power. Catches degraded links. |
| 3 (long) | `dcgmi diag -r 3` | ~15 min | Level 2 + full memory scan, diagnostic plugin. Catches intermittent memory errors. |

**Level 2 = sweet spot for pre-job checks.** Fast enough for Slurm prolog, thorough enough for most hardware issues.

Example Slurm prolog:
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

Key metrics to collect continuously (DCGM, `dcgm-exporter`, or custom scripts):

| Metric | Source | Why |
|--------|--------|-----|
| GPU temperature | `nvidia-smi -q -d TEMPERATURE` | Thermal throttling degrades perf silently |
| Memory temperature | DCGM `DCGM_FI_DEV_MEMORY_TEMP` | HBM throttles independently |
| Power draw | `nvidia-smi -q -d POWER` | Hitting power cap = clock throttling |
| Clock speeds | `nvidia-smi -q -d CLOCK` | Lower than max = throttling active |
| ECC error counts | `nvidia-smi -q -d ECC` | Rising corrected errors = failing memory |
| NVLink errors | `nvidia-smi nvlink -e` | Link degradation before failure |
| PCIe replay count | DCGM `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | Rising = signal integrity issue |
| XID error count | DCGM `DCGM_EXP_XID_ERRORS_COUNT` | Alert on any XID >= 48 |

---

## Fabric-Level: InfiniBand Diagnostics

### IB PHY Error Monitoring

**Metrics:**
- `rx_err_lane_*_phy` via ethtool (per-lane physical layer errors)
- Exposed via Grafana Alloy ethtool collector as `node_net_ethtool_received_err_lane_*_phy`
- Manual: `ethtool -S <ib_interface> | grep rx_err_lane`

**Heuristics** (IB uses FEC to correct errors; at high rates, FEC overwhelmed -> retransmissions -> latency):

| Tier | Threshold | Interpretation |
|------|-----------|----------------|
| Critical | >1M err/s | Likely causing retransmissions |
| High | 300K-1M err/s | Possible tail latency |
| Moderate | 100K-300K err/s | FEC handles it |
| Normal | <100K err/s | Baseline |

**Better signal:** `port_rcv_remote_physical_errors` from `perfquery` — counts cases where FEC failed to correct (actual retransmissions).

```bash
ethtool -S <ib_interface> | grep rx_err_lane
perfquery -x <lid> | grep RcvRemotePhysErrors
```

### ib_write_bw vs ibdiagnet

| | ib_write_bw | ibdiagnet |
|---|---|---|
| **What** | RDMA write throughput between 2 nodes | Fabric-wide topology + hardware counter analysis |
| **Plane** | Data plane | Management plane (SMP/GMP) |
| **Scope** | One HCA pair | Every port on every switch/HCA |
| **Detects** | Link throughput (GB/s) | BER, port errors, cabling, firmware mismatches, topology |
| **Limitation** | High-BER link still shows full line rate (retransmissions transparent on single stream) | Doesn't measure actual throughput |

**Key insight:** A link with BER 6e-08 still shows 396 Gb/s on `ib_write_bw` because hardware retransmits transparently for a single stream. Under collective load, every retransmission cascades. **Always run ibdiagnet even if point-to-point looks healthy.**

### ibdiagnet

Fabric-wide diagnostic. Discovers IB fabric topology via SM queries, reads hardware counters, compares against baselines.

```bash
ibdiagnet -i mlx5_0 -r --ft --ber_test --rail_validation -sc \
  --pm_pause_time 60 -P all=1 --extended_speeds all \
  --pm_per_lane --get_phy_info --get_cable_info --get_p_info \
  --cable_info_disconnected
```

| Flag | What |
|------|------|
| `-i mlx5_0` | Start discovery from this HCA |
| `-r` | Include routing info |
| `--ber_test` | BER testing — catches degraded links pre-failure |
| `--rail_validation` | Verify rail-optimized cabling matches expected topology |
| `-sc` | Subnet config checks |
| `--pm_pause_time 60` | Collect perf counters over 60s window |
| `-P all=1` | Reset all port counters first |
| `--extended_speeds all` | Validate all NDR links |
| `--pm_per_lane` | Per-lane stats — catches single-lane degradation |
| `--get_phy_info` | Signal quality, eye opening |
| `--get_cable_info` | Cable type, vendor, length, temperature |

#### What ibdiagnet catches that point-to-point misses

1. **BER on links** — high BER passes throughput tests (hardware retransmits transparently). Threshold: 1e-14. Bad: 6e-08. Fix: reseat/replace cable.
2. **Port counter errors** — cumulative counters; `--pm_pause_time 60` + `-P all=1` resets then measures delta
3. **Rail cabling mismatches** — `--rail_validation` compares actual wiring vs expected. Mismatches break NCCL topology-aware algorithms (PXN, rail-local routing).
4. **Firmware inconsistencies** — mixed versions cause subtle interop issues under load
5. **Uneven leaf switch downlinks** — asymmetric fabric capacity

**Output:** `/var/tmp/ibdiagnet2/` — `ibdiagnet2.log`, `ibdiagnet2.db_csv`, `ibdiagnet2.pm`

### mlxlink

Per-port diagnostic reading directly from HCA firmware. Catches signal integrity issues ibdiagnet may miss.

| | mlxlink | ibdiagnet |
|---|---|---|
| **Scope** | Single HCA port | Entire fabric |
| **Counters** | Cumulative since last reset | Delta over `--pm_pause_time` |
| **Sensitivity** | Pre-FEC physical errors (more sensitive) | Post-FEC symbol BER |
| **Diagnosis** | Provides `Recommendation` (e.g., "Bad signal integrity") | Pass/fail against thresholds |
| **Reset** | `mlxlink --pc` | `-P all=1` |

**Key insight:** ~600 pre-FEC errors/sec caught by mlxlink but may pass ibdiagnet's BER check (FEC corrects at physical layer). **Always run mlxlink alongside ibdiagnet.**

**When to use:**
- **ibdiagnet** — first pass, fabric-wide. Catches topology, rails, firmware, high post-FEC BER.
- **mlxlink** — targeted follow-up, or sweep all nodes for pre-FEC degradation
- **Both** — after datacenter fixes to verify repairs

#### Running mlxlink across cluster

```bash
ansible compute -i inventory.ini -m shell -a \
  "lspci -nn | grep ConnectX-7 | awk '{print \$1}' | while read bus_id; do
    echo \$bus_id; mlxlink -d \${bus_id} -c 2>/dev/null | grep 'Effective';
  done" --become
```

#### Interpreting Effective Physical Errors

Cumulative pre-FEC errors since last counter reset. What matters: **actively increasing**, not absolute number.

| BER | Severity | Action |
|-----|----------|--------|
| 0 or 15E-255 | Clean | None |
| 1E-17 to 1E-15 | Normal | Low-level noise, monitor |
| 1E-15 to 1E-13 | Elevated | Monitor, check if increasing |
| 1E-13 to 1E-10 | Bad | Verify stale vs active; schedule cable check |
| >= 1E-10 | Critical | Likely active; escalate for cable replacement |

**Verify active vs stale:**
```bash
mlxlink -d <bus_id> --pc        # clear counters
# wait, then:
mlxlink -d <bus_id> -c | grep "Effective Physical Errors"
```

Errors resume immediately = active issue. Stay at 0 = historical.

#### mlxlink flags

| Flag | Purpose |
|------|---------|
| `-c` | Cable/link info + effective BER |
| `-e` | Extended error counters |
| `-c -e` | Both |
| `--pc` | Clear port counters |
| `--port_type PCIE` | Check PCIe link |

When mlxlink shows `Bad signal integrity`, firmware has diagnosed a hardware problem — cable/transceiver needs replacement.

---

## Checklist: Cross-Switch Performance Degradation

When NCCL collective performance degrades at scale but point-to-point looks fine:

**1. Confirm problem is cross-switch**

```bash
# Same-SU baseline (should get full bandwidth)
mpirun --hostfile /tmp/hostfile-same-su ... all_reduce_perf -b 1G -e 8G -f 2 -g 1

# Cross-SU test (if degrades, spine is the problem)
mpirun --hostfile /tmp/hostfile-cross-su ... all_reduce_perf -b 1G -e 8G -f 2 -g 1
```

**2. Pairwise NCCL tests** — each suspect node paired with known-good node. Outliers with lower bandwidth need investigation.

**3. Per-HCA ib_write_bw**

```bash
# Server: ib_write_bw -d mlx5_0 --report_gbits -D 10
# Client: ib_write_bw -d mlx5_0 --report_gbits -D 10 <server_ip>
```

Repeat for all 8 IB HCAs (mlx5_0 through mlx5_11). All should hit ~396 Gb/s (NDR).

**4. mlxlink sweep** — catches pre-FEC signal degradation. Faster than ibdiagnet, per-node.

**5. ibdiagnet** — fabric-wide diagnostics. Check output for:
- [ ] BER above 1e-14
- [ ] Port counter errors incrementing
- [ ] Rail validation failures
- [ ] Firmware version mismatches
- [ ] Uneven downlink counts on leaf switches

**6. Check SHARP**

```bash
sharp_hello
# Fails with "Failed to connect to Aggregation Manager" = not enabled
```

SHARP does in-network reductions, can bypass spine congestion.

**7. NCCL algorithm tuning** (workaround)

```bash
NCCL_ALGO=Tree mpirun ... all_reduce_perf -b 1G -e 8G -f 2 -g 1
```

Tree often works better on congested fabrics (~24% improvement observed).

**8. Escalate with evidence**

```bash
sudo nvidia-bug-report.sh
journalctl -u nvidia-fabricmanager --since "24 hours ago" > fabmgr.log
dcgmi diag -r 3 2>&1 | tee dcgm-diag-r3.log
ls /var/tmp/ibdiagnet2/
```

Send: nvidia-bug-report, fabmgr logs, ibdiagnet output, same-SU vs cross-SU results, BER values, port errors, rail mismatches, DCGM diag.
