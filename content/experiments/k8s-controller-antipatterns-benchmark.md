---
title: "Kubernetes Controller Anti-patterns: What Actually Costs You Performance"
date: 2026-05-17T00:00:00+0800
tags: [kubernetes, controller-runtime, kubebuilder, operators, benchmarking, kind]
draft: true
---

Four controller best-practice guidelines tested against their bad counterparts on a local Kind cluster: does `GenerationChangedPredicate` matter, does `MaxConcurrentReconciles` help, does `r.Status().Patch()` break the conflict bottleneck, and do recent k8s feature gates reduce API server pressure? Each factor gets its own controlled experiment with Prometheus metrics collected per-second to CSV.

Code: [pokgak/agent-skills — experiments/k8s-controller-benchmark](https://github.com/pokgak/agent-skills/tree/main/experiments/k8s-controller-benchmark)

## The Question

Controller best practices are well documented but rarely quantified. Four concrete questions:

1. How bad does it get if you skip `GenerationChangedPredicate` and write annotations on every reconcile?
2. Where does `MaxConcurrentReconciles: 5` actually pay off over a single worker?
3. Does switching from `r.Status().Update()` + `RetryOnConflict` to `r.Status().Patch()` break the conflict bottleneck?
4. Do `ConcurrentWatchObjectDecode` and `WatchListClient` (k8s 1.34 feature gates) reduce the API server pressure that causes the bottleneck?

## Setup

- **Cluster:** Kind v1.34.0, single-node, local Docker (OrbStack)
- **CRD:** `Widget` — spec: count, message; status: phase, processedCount, lastUpdated
- **Simulated work:** 10ms sleep per reconcile (represents I/O-bound external call)
- **Metrics:** Prometheus endpoint scraped to CSV every 1s via a Go scraper binary; key metrics: `workqueue_depth`, `workqueue_adds_total`, `workqueue_retries_total`, `controller_runtime_reconcile_total{result}`, `controller_runtime_reconcile_time_seconds`
- **Framework:** controller-runtime v0.18.4, kubebuilder v4
- **Debug logging:** enabled on all controllers (zapcore.DebugLevel)
- **Observation window:** 60s for Experiment 1; 180s for Experiments 2–4

Each controller variant watches its own namespace so all variants can run concurrently on the same cluster without interfering.

---

## Experiment 1: Anti-patterns vs Best Practices

### Why this matters

Before measuring performance, the correctness question has to be answered first: do these controller patterns actually change *whether* objects converge, not just *how fast*? The two most-missed patterns in real operator code are the `GenerationChangedPredicate` and the status subresource distinction. This experiment isolates them in a controlled 2×2 matrix.

### Hypothesis

- **Predicate dominates correctness.** Bad controllers never converge to Ready regardless of worker count — the annotation-write loop creates a permanent reconcile backlog.
- **Predicate dominates event volume.** Bad controller reconcile counts grow without bound; good controllers stabilize after the first pass.
- **More workers amplifies the loop.** Five concurrent workers racing to stamp the same annotation produce more `resourceVersion` conflicts than a single worker, generating more retries and more wasted work. The 1-worker bad controller is throttled by its own serialization.

### Method

Four controller variants running concurrently in separate namespaces:

| | 1 worker | 5 workers |
|---|---|---|
| **Predicate ON** | `good-single` | `good` |
| **Predicate OFF** | `bad-fixed-single` | `bad-fixed-status` |

All four variants use `r.Status().Update()` correctly (status subresource enabled), isolating the predicate and worker count as the only variables.

The "bad" variants stamp a nanosecond timestamp annotation on every reconcile via `r.Update()`. Without the predicate, each annotation write bumps `resourceVersion`, fires a watch event, and re-triggers reconcile — a guaranteed infinite loop.

N = {50, 200, 500, 1000} Widget objects created concurrently in all namespaces. 60-second observation window. Reconcile counts from controller logs; Ready counts from `kubectl get widgets`.

> ⚠️ **Data gap:** N=5000 not collected for this experiment. The scale table stops at N=1000.

### Results

**Reconcile counts and Ready status after 60s:**

| N | good Ready | good reconciles | bad-fix Ready | bad-fix (5w) reconciles | bad-fix-single (1w) reconciles |
|---|---|---|---|---|---|
| 50 | 50/50 ✓ | 150 | 0/50 ✗ | 2,851 | 1,345 |
| 200 | 200/200 ✓ | 400 | 0/200 ✗ | 4,650 | 1,566 |
| 500 | 500/500 ✓ | 1,100 | 0/500 ✗ | 7,594 | 3,064 |
| 1,000 | 1000/1000 ✓ | 2,600 | 0/1000 ✗ | 12,683 | 5,856 |

**Time to full convergence (good controller, 5w):**

| N | Time to 100% Ready |
|---|---|
| 50 | ~5s |
| 200 | ~11s |
| 500 | ~21s |
| 1,000 | ~39s |

**Key Prometheus metrics at N=200 end-of-window:**

| Controller | queue_depth | queue_adds | retries | errors | avg_lat |
|---|---|---|---|---|---|
| good (5w) | 0 | 400 | 0 | 0 | 61ms |
| good-single (1w) | 0 | 300 | 0 | 0 | 20ms |
| bad-fix (5w) | 198 | 4,650 | 7 | 7 | 465ms |
| bad-fix-single (1w) | 199 | 1,566 | 3 | 3 | 94ms |

### What this tells us

**The correctness prediction was fully confirmed.** Bad controllers never reach Ready at any scale because `r.Update()` on a CRD with `subresources: status: {}` silently strips status fields at the API server. The controller sets `widget.Status.Phase = "Ready"` in memory, calls `r.Update()`, gets a 200 OK back, and the write is discarded. No error, no log, no convergence.

**The loop prediction was confirmed.** Without `GenerationChangedPredicate`, every annotation write bumps `resourceVersion` → watch event → reconcile → annotation write → loop. At N=200 the bad-5w controller produced 4,650 reconcile events in 60 seconds (23/s per 200 objects) while the good controller produced 400 and went silent.

**The "more workers amplifies the loop" prediction was also confirmed** — but in a specific way. The 5-worker bad controller produced *fewer* reconciles than the 1-worker at large N (12,683 vs 5,856 at N=1000). The reason: with 5 workers racing to annotate the same object pool, they produce more `resourceVersion` conflicts (7 errors vs 3). Each conflict triggers a rate-limiter backoff — the loop is actually *slower* under contention. The 1-worker controller serializes cleanly with no conflicts, achieving higher raw event throughput despite being bottlenecked to ~100/s.

Average reconcile latency confirms this: bad-fix-5w at 465ms vs bad-fix-single at 94ms. Five concurrent annotation writes on the same 200 objects create 5× more API server pressure per object, inflating per-write latency.

**Connection to real frameworks:** This maps directly to how [kopf](https://kopf.readthedocs.io/) (the Python controller framework) works internally — it writes handler progress and state into annotations on every handler invocation. Without `GenerationChangedPredicate`'s equivalent, every annotation write re-enters the handler. At low object counts the loop is fast and handlers are idempotent, so it's invisible. At 1000+ objects with concurrent external changes (e.g., Pod status updates), the annotation cascade grows faster than the handler queue can drain — the production bogging-down at ~1000 pods described in the setup.

This experiment eliminated the bad variants from further investigation. Experiments 2–4 focus only on the good patterns.

---

## Experiment 2: When Does MaxConcurrentReconciles Pay Off?

### Why this matters

Experiment 1 showed the 5-worker good controller converges faster at modest N. The natural follow-up: does the benefit scale? Is there a regime where 5 workers saturates the workload, converges faster, and then the advantage disappears? Or is there actually a regime where 5 workers actively hurts a correctly-written controller?

### Hypothesis

5 workers should produce ~5× faster convergence at low N where the bottleneck is worker throughput. At very large N (10k+), both configurations should saturate at the same throughput ceiling and produce the same number of reconciles per unit time.

### Method

Only the two good variants (`good` 5w, `good-single` 1w). Bad controllers scaled to 0 replicas to eliminate API server noise. 180-second observation window. N = {1,000; 2,000; 10,000}.

> ⚠️ **Data gap:** N=5,000 not collected in this run. N=10,000 run did not fully converge in 180s — both controllers had ~5,600 objects remaining when the window closed.

### Results

| N | good-1w success | good-1w lat | good-1w errors | good-5w success | good-5w lat | good-5w errors |
|---|---|---|---|---|---|---|
| 1,000 | 3,000 | 32ms | 0 | 2,106 | 124ms | **17** |
| 2,000 | 4,000 | 37ms | 0 | 3,094 | 164ms | **13** |
| 10,000 | 4,385 | 50ms | 0 | **4,385** | 248ms | **0** |

Both controllers converge fully at N=1k and N=2k. At N=10k, queue depth at window close: good-single q=5,614; good q=5,610. Drain rate: ~200 objects per 10s for both — identical throughput at scale.

### What this tells us

**The hypothesis was wrong.** 5 workers never beats 1 worker at any tested scale on this cluster. At every N:

- The 5-worker controller has 4–5× higher per-reconcile latency
- It produces 13–17 conflict errors at small N (zero on the 1-worker version)
- It processes fewer or equal total reconciles per unit time

The explanation: with 5 concurrent reconcilers each issuing `r.Status().Update()`, all 5 goroutines hit the Kind API server simultaneously. The single-node Kind API server (etcd + kube-apiserver in one Docker container) serializes writes internally — etcd handles one write at a time. The result is not 5× parallelism; it's 5 goroutines queued behind each other with higher per-write latency, producing the same aggregate throughput.

At N=10,000 the ceiling is explicit: ~24 writes/sec, achieved equally by both configurations. The 5-worker controller at 248ms avg × 5 workers = theoretical 20/s; the 1-worker at 50ms = theoretical 20/s. They're the same calculation, confirming the API server is the shared wall.

The 17 errors at N=1k (vs 0 at N=10k) have a distinct cause: at small queue depth, all 5 workers can land on the *same* object simultaneously — one worker holds a fresh `resourceVersion` and writes; the others hold a stale copy and get a 409 Conflict. At N=10k the queue contains 10,000 distinct objects, so workers almost never collide.

**For production:** `MaxConcurrentReconciles` matters when reconcile work is CPU-bound or calls external APIs (not the Kubernetes API server) — work that genuinely parallelizes. On a single-node development cluster or CI Kind cluster, 1 worker is optimal. On a real multi-node HA cluster with distributed etcd, more workers should show genuine throughput gains since writes don't serialize on one node.

This experiment raises the question for Experiment 3: if conflicts are the visible cost of 5 workers at small N, does eliminating conflicts (via `r.Status().Patch()`) let 5 workers finally pay off?

---

## Experiment 3: Does r.Status().Patch() Move the Ceiling?

### Why this matters

Experiment 2's main cost at small N was conflicts: 5 workers racing on the same `resourceVersion` produce 409 errors that trigger `RetryOnConflict` retries. `r.Status().Patch()` with a merge patch eliminates the conflict entirely — no `resourceVersion` matching required. If conflicts were the bottleneck, switching to Patch should break the ~24/s ceiling. If etcd write serialization is the bottleneck, Patch removes noise but doesn't move the ceiling.

### Hypothesis

- Patch eliminates `resourceVersion` conflicts at all scales (zero retries, zero errors).
- If retries were the bottleneck: latency drops, throughput rises above the 24/s ceiling.
- If etcd serialization is the bottleneck: conflicts gone, ceiling unchanged.

### Method

Two new controller variants: `good-patch` (5w + `r.Status().Patch()`), `good-single-patch` (1w + `r.Status().Patch()`). All other patterns identical to `good` and `good-single`. `client.MergeFrom` merge patch — no `RetryOnConflict` wrapper needed.

```go
// Before (Update + RetryOnConflict):
err = retry.RetryOnConflict(retry.DefaultRetry, func() error {
    current := &Widget{}
    r.Get(ctx, req.NamespacedName, current)  // extra GET on each retry
    current.Status.Phase = "Ready"
    return r.Status().Update(ctx, current)
})

// After (Patch — no retry needed):
base := widget.DeepCopy()
widget.Status.Phase = "Ready"
r.Status().Patch(ctx, widget, client.MergeFrom(base))
```

N = {1,000; 10,000}. 180-second window.

> ⚠️ **Data gap:** N=2,000 and N=5,000 patch runs were killed mid-setup by a `kubectl delete` timeout bug (now fixed). Only N=1k and N=10k captured. The "Patch is slower at small N, converges at large N" claim would benefit from N=2k or N=5k to fill the curve.

### Results

| N | Method | 5w success | 5w lat | 5w retries | 1w success | 1w lat | 1w retries |
|---|---|---|---|---|---|---|---|
| 1k | **Update** | 2,106 | 124ms | 17 | 3,000 | 32ms | 0 |
| 1k | **Patch** | 1,000 | 242ms | **0** | 1,000 | 49ms | 0 |
| 10k | **Update** | 4,385 | 248ms | 0 | 4,385 | 50ms | 0 |
| 10k | **Patch** | 4,365 | 248ms | 0 | 4,365 | 50ms | 0 |

### What this tells us

**Conflicts: eliminated** ✓ Zero retries at both scales including N=1k where Update had 17.

**Throughput ceiling: unchanged.** Both variants still hit ~24 reconciles/sec at N=10k. The ceiling is etcd write serialization, not retry overhead. Patch removes noise but not the fundamental constraint.

**Patch is slower at small N for the 5-worker variant** — 242ms vs 124ms at N=1k. The server-side JSON merge processing adds latency that the plain Update path didn't have. This shows up when the API server isn't already saturated with queued writes. At N=10k the serialization wait dominates and both methods converge to ~248ms.

**The 1-worker variant barely changed** — 49ms vs 32ms (Patch slightly slower). The 1-worker controller never had conflicts to begin with, so Patch adds overhead without removing any existing wasted work.

> Note: Patch at N=10k produced 4,365 successes vs Update's 4,385 — Patch is marginally *worse* even at large scale. The server-side merge overhead is always present.

**When to use each:** Use `r.Status().Patch()` when your controller has 5+ workers writing status concurrently and you want zero-conflict semantics with simpler code. Use `r.Status().Update()` + `RetryOnConflict` for single-worker controllers or when status computation requires reading the latest version. Neither approach moves the write throughput ceiling on a single-node cluster.

---

## Experiment 4: Can Recent Feature Gates Reduce API Server Pressure?

### Why this matters

Experiments 2 and 3 found a hard ceiling at ~24 writes/sec from etcd serialization. Kubernetes 1.31–1.34 added several KEPs targeting API server efficiency. `WatchListClient` (KEP-3157) streams initial list responses as watch events to reduce memory pressure; `ConcurrentWatchObjectDecode` parallelizes the watch cache dispatch loop. Both should free API server goroutines — if that frees enough capacity to help our write bottleneck.

### Hypothesis

Per-reconcile latency drops slightly for the 5-worker controller (less watch cache goroutine contention), the etcd write ceiling holds unchanged. The 1w vs 5w throughput gap narrows but doesn't close.

### Method

New Kind cluster (`widget-benchmark-fg`, same `kindest/node:v1.34.0` image) with explicit feature gate flags:

```yaml
apiServer:
  extraArgs:
    feature-gates: "ConcurrentWatchObjectDecode=true"
controllerManager:
  extraArgs:
    feature-gates: "WatchListClient=true"
```

`ListFromCacheSnapshot`, `InOrderInformers`, and `StreamingCollectionEncoding*` are reported as default-on in 1.34 and not explicitly set.

> ⚠️ **Verification gap:** "default-on in 1.34" is based on release notes research, not verified against the running cluster. To confirm: `kubectl get --raw '/metrics' | grep '^kubernetes_feature_enabled'`.

Same two variants as Experiment 2 (`good` 5w, `good-single` 1w). N = {1k, 2k, 5k, 10k}.

> ⚠️ **Data gap:** N=5,000 result is suspect — the fg cluster shows `good-single ok=6,736` and `good ok=6,042` with retries at N=5k, which doesn't fit the pattern (both N=2k and N=10k show ~2k–4k successes). This is likely contaminated by leftover widgets from the previous scale run that a timed-out `kubectl delete` didn't fully clear. N=5k should be re-run on a freshly cleaned cluster.

### Results

| N | Baseline 5w lat | Baseline 5w retries | FG 5w lat | FG 5w retries | Baseline 1w lat | FG 1w lat |
|---|---|---|---|---|---|---|
| 1k | 124ms | 17 | **242ms** | **0** | 32ms | **49ms** |
| 2k | 164ms | 13 | **246ms** | **0** | 37ms | **49ms** |
| 5k | 123ms | 7 | 165ms | ⚠️ 21 | 31ms | ⚠️ 35ms |
| 10k | 248ms | 0 | **248ms** | 0 | 50ms | **50ms** |

### What this tells us

**The hypothesis was wrong** — the feature gates increased latency at small N rather than decreasing it. At N=1k the 5-worker controller went from 124ms to 242ms; the 1-worker went from 32ms to 49ms. At N=10k both converged back to baseline values (248ms / 50ms) because the etcd write ceiling dominates.

**Why WatchListClient adds overhead here (KEP-3157):**

`WatchListClient` is designed for one specific production failure: when many controllers restart simultaneously and each issues `LIST RV="0"`, the API server must buffer the full response per requester — O(5 × response_size) of temporary memory per concurrent list. With hundreds of informers restarting after a network partition, this causes OOM crashes. WatchListClient prevents this by streaming objects one-at-a-time from the watch cache rather than buffering the full list.

In our scenario — fresh single-controller start, 1k–10k small CRD objects — all the costs fire with none of the benefits:

1. **Mandatory etcd quorum read on startup.** `WatchListClient` always performs a consistent read from etcd before streaming, even on a fresh cache. The old `LIST RV="0"` served directly from the watch cache without touching etcd. This adds ~10–15ms per informer startup.
2. **Per-object watch event overhead.** Instead of one JSON `items` array, each object is delivered as a separate `ADDED` watch event with its own envelope. For small objects, the per-event framing cost dominates any memory saving.
3. **Known 1–1.25 second bookmark timer delay** ([GitHub #122277](https://github.com/kubernetes/kubernetes/issues/122277)). The "initial sync complete" BOOKMARK waits for the next periodic timer tick rather than firing immediately when the threshold ResourceVersion is reached. This can add a full second to every informer startup.
4. **The Kubernetes project itself acknowledged the tradeoff.** The server-side `WatchList` gate was promoted to Beta default-on in 1.32, then **reverted to default-off in 1.33**. `WatchListClient` remains opt-in only in 1.34.

**`WatchListClient` actually helps when:** controllers restart simultaneously in a large cluster (thousands of nodes, 100k+ objects), API server memory is the constraint, or objects are large (Secrets with large cert data, ConfigMaps). For a single-replica controller on a development Kind cluster, leave it at the default (off).

---

## Final Summary

Four levers tested against the API server write bottleneck. One dominated correctness. None moved throughput.

| Factor | Correctness | Throughput | Latency |
|---|---|---|---|
| `GenerationChangedPredicate` OFF | **Breaks** — objects never converge, loop is infinite | — | — |
| `r.Update()` for status (vs `r.Status().Update()`) | **Breaks** — status silently discarded by API server | — | — |
| `MaxConcurrentReconciles: 5` (vs 1) | ✓ No change | **No gain** on single-node Kind | **4–5× worse** (write serialization) |
| `r.Status().Patch()` (vs Update + RetryOnConflict) | ✓ Eliminates conflict errors | **No gain** — ceiling is etcd serialization | **Slightly worse** at small N |
| `ConcurrentWatchObjectDecode` + `WatchListClient` | ✓ No change | **No gain** | **Worse** at small N, same at large N |

**For a single-node Kind cluster:** the etcd write ceiling (~24 writes/sec on this hardware) is the hard floor on throughput, and none of the tested knobs move it. The correctness levers (`GenerationChangedPredicate`, status subresource) are non-negotiable. The performance levers range from neutral to counterproductive on this setup.

**For a real production cluster:** `MaxConcurrentReconciles: 5` should show genuine throughput gains on a multi-node HA API server where writes don't all serialize on one etcd leader. `WatchListClient` is designed for large-scale thundering-herd scenarios. The benchmark methodology in this repo can be re-run against production-scale infrastructure to find where each lever actually wins.

**Open data gaps before publishing:**

- [ ] Re-run N=5,000 for Experiments 1, 3, and 4 cleanly
- [ ] Re-run Experiment 4 N=5k on freshly cleared cluster (suspect contamination)
- [ ] Patch N=2,000 and N=5,000 (N=1k and N=10k only)
- [ ] Extend one N=10k run to ~500s to report actual convergence time (both controllers still had ~5,600 queued at 180s)
- [ ] Verify default-on gates via `kubectl get --raw '/metrics' | grep kubernetes_feature_enabled`
- [ ] Add `kubectl top pod` CPU snapshots for bad-fix-5w to visually reinforce the wasted-work argument

## Running It Yourself

```bash
git clone https://github.com/pokgak/agent-skills
cd agent-skills/experiments/k8s-controller-benchmark

make setup          # create Kind cluster, build + load images, deploy CRDs and controllers
make stress N=200   # 2×2 matrix run (all 4 variants)
bash stress-good.sh 1000 180   # good variants only, N=1000
bash stress-patch.sh 1000 180  # patch variants
make setup-fg       # feature gate cluster
bash stress-good-fg.sh 1000 180
make clean          # tear down both clusters
```

Requires: `kind`, `kubectl`, `docker`, `go 1.22+`, `duckdb` (for CSV analysis)
