---
title: "Tuning etcd for sandbox workloads"
date: 2026-06-21T10:00:00+0800
tags: [kubernetes, etcd, scaling, infrastructure]
---

**etcd is the part of Kubernetes that falls over first under churn.** A sandbox workload — short-lived pods running untrusted code, created and destroyed by the thousand — generates a relentless stream of writes and lists against etcd. On small, self-hosted control planes that was enough to drag P99 op latency into the *tens of seconds*. This note is what it took to keep etcd healthy: bound what's stored in it, tune it, keep controllers from hammering it with reads, and give it fast disk.

## The setup

Self-hosted Kubernetes clusters whose control-plane nodes also carry system workload (gateway, sandbox manager, secrets operator, monitoring). The workload is the whole story: **short-lived sandbox pods** on a [gVisor](https://gvisor.dev/) runtime — bursty create/delete, seconds-to-minutes lifetimes. That high pod churn is the source of nearly every failure below.

## The core problem: pod churn → etcd pressure

Every pod lifecycle event writes to etcd, and sandbox pods churn constantly. Two distinct failure modes fell out of this:

1. **Event spam bloats etcd.** Every pod lifecycle emits Kubernetes Events. In one incident a single namespace accumulated **13.4K events at 5 qps**, bloating etcd to **~500 MB**.
2. **Write/list latency on etcd spikes** under the churn — control-plane P99 op latency climbed to *tens of seconds*.

### Fix 1 — rate-limit events, and cut their TTL (the biggest lever)

The `EventRateLimit` admission plugin caps how fast events can be written. Final limits after tuning:

```
# apiserver admission config
namespace: qps=1   burst=10
server:    qps=200 burst=400
cache_size: 4096
```

Sizing math worth keeping: **`max events/ns = qps × ttl`**. Server side, ~100 concurrent namespaces × 1 qps = 100 qps against a 200 cap → 2× headroom. Observed real traffic was ~0.1/s average, ~0.9/s burst per namespace, so a 1-qps ceiling comfortably covers legitimate load while strangling runaway namespaces.

But the rate limit alone wasn't enough, and here's the non-obvious part: **the per-namespace rate limit caps the write *rate*, not the cluster-wide *total*.** At a 1-hour event TTL, each busy namespace parks near its ceiling — `1 qps × 3600 s = 3600 events/ns` — so with ~8 active sandbox namespaces the cluster carried **15–18K live events at all times**. That standing collection is exactly what made etcd range LISTs expensive (see the latency section below).

**TTL is the lever that actually bounds the steady-state count.** Cutting the event TTL from 1h to 5m drops the per-namespace ceiling from 3600 to 300 (~12×):

```
--event-ttl=5m   # was 1h
```

⚠️ **The tradeoff to call out, because it's a real one:** a 5-minute event TTL means `kubectl get events` and `kubectl describe pod` only show the last ~5 minutes. You lose the event history you'd normally lean on to debug a pod that failed 10–20 minutes ago — `FailedScheduling`, image-pull errors, `OOMKilled`, probe failures all age out fast.

This is only acceptable here because **container logs ship off-cluster to Loki and persist there.** The durable record lives in logs; Events are treated as ephemeral, low-value churn. **If you don't ship logs off-cluster, do not cut the TTL this aggressively — 15–30m is a safer middle ground.**

Two rollout gotchas:

- Applying `--event-ttl` means re-rendering the apiserver config and doing a rolling control-plane restart, one node at a time so quorum is preserved.
- **TTL is stamped at event *creation*, not read.** Pre-existing 1h-TTL events linger up to an hour after the change — the count declines gradually, it does not drop on restart. Don't watch the dashboard for an instant cliff; you won't see one.

### Fix 2 — etcd tuning

```
# continuous compaction so revision history doesn't accumulate
compaction-mode=revision
compaction-retention=1000ns
quota-backend-bytes=8GiB

# tighter raft timings for small control-plane VMs
heartbeat-interval=250ms
election-timeout=2500ms
snapshot-count=5000
```

Also enable two feature gates that cut watch/list load on the apiserver:

```
feature-gates: WatchListClient=true,MutatingAdmissionPolicy=true
```

### Fix 3 — serve controller LISTs from the watch cache (`resourceVersion=0`)

Rate-limiting events shrinks the collection; this fix attacks the LISTs themselves. By default, a `LIST` with no `resourceVersion` set is a **quorum (consistent) read** — the apiserver reads straight from etcd, which means a fresh range scan over the whole collection every time. Our own controllers reconciled by periodically LISTing sandbox objects cluster-wide, so every reconcile pass was a direct etcd range scan — exactly the `list`/`listWithCount` ops that dominated the latency tail.

Setting `resourceVersion=0` changes where the read is served from. The apiserver answers it out of its in-memory **watch cache** and never touches etcd:

```go
// client-go: serve from the apiserver watch cache instead of etcd
list, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{
    ResourceVersion: "0",
})
```

- **Tradeoff:** RV=0 returns data that's *at least as fresh as the cache*, which can lag etcd by a small window. For a reconcile loop that runs continuously this is fine — the next pass corrects any staleness — but don't use it where you need read-after-write consistency.
- This is the client-side half of the same idea as the `WatchListClient=true` gate in Fix 2: keep list traffic on the apiserver's cache and off etcd's range scanner.

### Fix 4 — get etcd off the boot disk

etcd is fsync-sensitive and the boot disk is shared with everything else on the node. All workers moved the k3s `data-dir` and kubelet `root-dir` onto a RAID0 (xfs) NVMe volume mounted at `/scratch`.

**Gotcha worth its own line:** the migration orphaned the kubelet drop-in config, so playbook re-runs would silently revert the node back to the boot disk. The fix was pinning `data_dir=/scratch` in the config inventory so the desired state and the live state actually match. Classic reminder that declarative config only converges if it describes the thing that's really there.

## The latency mystery — and a debugging lesson

The open question for a while was whether the P99 etcd-latency drop was a *fix* landing or just *load draining*. Resolving it is the through-line that justifies the `event-ttl=5m` change above.

- P99 hit **50s+ on `list`/`listWithCount`**, and that dragged *every* op up with it — create, get, delete too. That's the signature of **head-of-line blocking**: a few very expensive range reads stall everything queued behind them.
- It was **not disk** (WAL fsync ~3ms, backend commit ~25ms) and **not memory** (~3GB of 32GB, no OOM, no apiserver restarts). It was **CPU / range-scan bound** on the small control-plane VMs.
- It **tracked the live events count** — latency spikes lined up with events peaking at ~15–18K. Consistent LIST / listWithCount range scans over that collection (plus ~900 pods) are what blew up. Events followed a **daily sawtooth (5K → 18K → 5K)**, so the latency *recurred*; it wasn't a one-off. → Bound the events count (via TTL) and you bound the LIST cost. That's the fix.

And the debugging lesson, because I nearly drew the wrong conclusion:

> **The "sharp cliff to ~0" in the latency graph was mostly a timezone misread.** Grafana renders in browser-local time (here UTC-7), so the on-screen window was ~7h off from the UTC metric data — the "04:00 cliff" wasn't where I thought it was. **Always reconcile timezones (`date +%z`) before correlating a dashboard window with a PromQL query.** The genuine dips turned out to be the events sawtooth declining (load), not a tuning change landing.

## Takeaways

- **etcd is the first thing to fall over under pod churn.** On a high-churn sandbox cluster the load is writes + range LISTs; expensive LISTs head-of-line-block everything else and drag P99 into the tens of seconds.
- **Bound what's *stored* in etcd, not just the write rate.** Rate-limiting events caps the *rate*; TTL caps the standing *total* (`max events/ns = qps × ttl`) — and it's the standing collection that makes range scans expensive. A short event TTL is the cheapest big win *if* you keep durable history elsewhere (logs in Loki); otherwise keep 15–30m.
- **Keep controllers off etcd for reads.** A `LIST` with no `resourceVersion` is a quorum read straight from etcd; `resourceVersion=0` serves it from the apiserver watch cache. For a continuously-reconciling controller the slight staleness is free.
- **Give etcd fast, dedicated disk** — off the shared boot disk — and make sure your config-management tool describes the disk you actually moved to, or it'll revert you.
- **Reconcile timezones before trusting a dashboard correlation.** A 7-hour offset will happily sell you a fake "fix landed here" story.
